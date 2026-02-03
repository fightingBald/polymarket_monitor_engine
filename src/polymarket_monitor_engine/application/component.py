from __future__ import annotations

import asyncio
from typing import Any

import structlog

from polymarket_monitor_engine.application.dashboard import TerminalDashboard
from polymarket_monitor_engine.application.discovery import MarketDiscovery
from polymarket_monitor_engine.application.monitor import SignalDetector
from polymarket_monitor_engine.application.orderbook import OrderBookRegistry, OrderBookUpdateResult
from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.models import Market
from polymarket_monitor_engine.domain.schemas.event_payloads import (
    CandidateSelectedPayload,
    HealthPayload,
    MarketLifecyclePayload,
    MonitoringStatusPayload,
    SignalType,
    SubscriptionChangedPayload,
    WebVolumeSpikePayload,
)
from polymarket_monitor_engine.domain.selection import normalize_topic
from polymarket_monitor_engine.ports.clock import ClockPort
from polymarket_monitor_engine.ports.feed import (
    BestBidAskMessage,
    BookMessage,
    FeedPort,
    MarketLifecycleMessage,
    PriceChangeMessage,
    TradeMessage,
)
from polymarket_monitor_engine.ports.sink import EventSinkPort
from polymarket_monitor_engine.util.ids import new_event_id

logger = structlog.get_logger(__name__)


class PolymarketComponent:
    def __init__(
        self,
        categories: list[str],
        refresh_interval_sec: int,
        discovery: MarketDiscovery,
        feed: FeedPort,
        sink: EventSinkPort,
        clock: ClockPort,
        detector: SignalDetector,
        resync_on_gap: bool,
        resync_min_interval_sec: int,
        polling_volume_threshold_usd: float,
        polling_cooldown_sec: int,
        dashboard: TerminalDashboard | None = None,
    ) -> None:
        self._categories = categories
        self._refresh_interval_sec = refresh_interval_sec
        self._discovery = discovery
        self._feed = feed
        self._sink = sink
        self._clock = clock
        self._detector = detector
        self._orderbooks = OrderBookRegistry()
        self._resync_on_gap = resync_on_gap
        self._resync_min_interval_ms = resync_min_interval_sec * 1000
        self._last_resync_ms = 0
        self._token_meta: dict[str, TokenMeta] = {}
        self._markets_by_id: dict[str, Market] = {}
        self._token_ids: list[str] = []
        self._dashboard = dashboard
        self._polling_volume_threshold_usd = polling_volume_threshold_usd
        self._polling_cooldown_ms = polling_cooldown_sec * 1000
        self._unsub_prev_volume: dict[str, float] = {}
        self._unsub_cooldowns: dict[str, int] = {}
        self._last_refresh_start_ms: int | None = None
        self._startup_notified = False
        self._lifecycle_ready = False

    async def run(self) -> None:
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._refresh_loop())
                tg.create_task(self._consume_loop())
                if self._dashboard is not None:
                    tg.create_task(self._dashboard.run())
        finally:
            if self._dashboard is not None:
                await self._dashboard.stop()
            await self._feed.close()

    async def _refresh_loop(self) -> None:
        while True:
            try:
                start_ms = self._clock.now_ms()
                discovery_result = await self._discovery.refresh(self._categories)
                await self._handle_refresh(
                    discovery_result.markets_by_category,
                    discovery_result.unsubscribable,
                )
                window_sec = self._refresh_interval_sec
                if self._last_refresh_start_ms is not None:
                    gap_ms = max(0, start_ms - self._last_refresh_start_ms)
                    window_sec = max(1, int(gap_ms / 1000))
                self._last_refresh_start_ms = start_ms
                await self._emit_unsubscribable_signals(
                    discovery_result.unsubscribable,
                    window_sec=window_sec,
                )
                if not self._startup_notified and self._token_ids:
                    await self._emit_monitoring_status(
                        discovery_result.markets_by_category,
                        discovery_result.unsubscribable,
                    )
                    self._startup_notified = True
                if self._dashboard is not None:
                    await self._dashboard.update_unsubscribable(
                        discovery_result.unsubscribable,
                        reason="无 orderbook",
                    )
                duration_ms = self._clock.now_ms() - start_ms
                await self._emit_health("refresh_ok", {"duration_ms": duration_ms})
                if self._dashboard is not None:
                    await self._dashboard.record_refresh(duration_ms)
            except Exception as exc:  # noqa: BLE001
                await self._emit_health("refresh_error", {"error": str(exc)})
                logger.warning("refresh_failed", error=str(exc))
            await self._clock.sleep(self._refresh_interval_sec)

    async def _consume_loop(self) -> None:
        async for message in self._feed.messages():
            if isinstance(message, TradeMessage):
                trade = message.trade
                if self._dashboard is not None:
                    await self._dashboard.update_trade(trade)
                await self._detector.handle_trade(trade)
                continue
            if isinstance(message, BookMessage):
                result = self._orderbooks.apply_snapshot(message.book, message.seq)
                await self._handle_resync(result)
                if not result.resync_needed:
                    if self._dashboard is not None:
                        await self._dashboard.update_book(message.book)
                    await self._detector.handle_book(message.book)
                continue
            if isinstance(message, PriceChangeMessage):
                result = self._orderbooks.apply_price_change(message)
                await self._handle_resync(result)
                if result.snapshot is not None and not result.resync_needed:
                    if self._dashboard is not None:
                        await self._dashboard.update_book(result.snapshot)
                    await self._detector.handle_book(result.snapshot)
                continue
            if isinstance(message, MarketLifecycleMessage):
                await self._emit_feed_lifecycle(message)
                continue
            if isinstance(message, BestBidAskMessage):
                logger.debug("feed_price_update", kind=message.kind.value)
                continue
            logger.debug("feed_message_ignored", payload=getattr(message, "raw", None))

    async def _handle_refresh(
        self,
        markets_by_category: dict[str, list[Market]],
        unsubscribable: list[Market] | None = None,
    ) -> None:
        initial = not self._lifecycle_ready
        new_markets: dict[str, Market] = {}
        for markets in markets_by_category.values():
            for market in markets:
                new_markets[market.market_id] = market
        for market in unsubscribable or []:
            if market.market_id:
                new_markets[market.market_id] = market

        if not initial:
            await self._emit_market_lifecycle(new_markets)

        token_meta = self._build_token_meta(markets_by_category)
        self._detector.update_registry(token_meta)
        if self._dashboard is not None:
            await self._dashboard.update_registry(token_meta)

        token_ids = sorted(token_meta.keys())
        if token_ids != self._token_ids:
            await self._feed.subscribe(token_ids)
            await self._emit_subscription_changed(token_ids)
            self._token_ids = token_ids

        for category, markets in markets_by_category.items():
            await self._emit_candidates(category, markets)

        self._token_meta = token_meta
        self._markets_by_id = new_markets
        self._lifecycle_ready = True

    def _build_token_meta(
        self,
        markets_by_category: dict[str, list[Market]],
    ) -> dict[str, TokenMeta]:
        mapping: dict[str, TokenMeta] = {}
        for category, markets in markets_by_category.items():
            for market in markets:
                topic_key = market.topic_key or normalize_topic(market.question)
                outcomes = market.outcomes or []
                token_outcomes = [outcome for outcome in outcomes if outcome.token_id]
                if token_outcomes:
                    for outcome in token_outcomes:
                        token_id = outcome.token_id
                        mapping[token_id] = TokenMeta(
                            token_id=token_id,
                            market_id=market.market_id,
                            category=category,
                            title=market.question,
                            side=_normalize_side(outcome.side),
                            topic_key=topic_key,
                            end_ts=market.end_ts,
                        )
                else:
                    for token_id in market.token_ids:
                        mapping[token_id] = TokenMeta(
                            token_id=token_id,
                            market_id=market.market_id,
                            category=category,
                            title=market.question,
                            side=None,
                            topic_key=topic_key,
                            end_ts=market.end_ts,
                        )
        return mapping

    async def _emit_candidates(self, category: str, markets: list[Market]) -> None:
        payload = {
            "markets": [
                {
                    "market_id": m.market_id,
                    "question": m.question,
                    "liquidity": m.liquidity,
                    "volume_24h": m.volume_24h,
                    "end_ts": m.end_ts,
                    "token_ids": m.token_ids,
                }
                for m in markets
            ]
        }
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            category=category,
            event_type=EventType.CANDIDATE_SELECTED,
            payload=CandidateSelectedPayload(market_count=len(markets)),
            raw=payload,
        )
        await self._sink.publish(event)

    async def _emit_subscription_changed(self, token_ids: list[str]) -> None:
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            event_type=EventType.SUBSCRIPTION_CHANGED,
            payload=SubscriptionChangedPayload(token_count=len(token_ids)),
            raw={"token_ids": token_ids},
        )
        await self._sink.publish(event)

    async def _emit_market_lifecycle(self, new_markets: dict[str, Market]) -> None:
        old_ids = set(self._markets_by_id.keys())
        new_ids = set(new_markets.keys())
        removed = old_ids - new_ids
        added = new_ids - old_ids

        for market_id in removed:
            old = self._markets_by_id[market_id]
            await self._emit_lifecycle(old, "removed")
        for market_id in added:
            await self._emit_lifecycle(new_markets[market_id], "new")

    async def _emit_lifecycle(self, market: Market, status: str) -> None:
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            category=market.category,
            event_type=EventType.MARKET_LIFECYCLE,
            market_id=market.market_id,
            title=market.question,
            topic_key=market.topic_key,
            payload=MarketLifecyclePayload(status=status, end_ts=market.end_ts or 0),
        )
        await self._sink.publish(event)

    async def _emit_health(self, status: str, metrics: dict[str, Any]) -> None:
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            event_type=EventType.HEALTH_EVENT,
            payload=HealthPayload(
                status=status,
                duration_ms=metrics.get("duration_ms"),
                error=metrics.get("error"),
            ),
        )
        await self._sink.publish(event)

    async def _emit_monitoring_status(
        self,
        markets_by_category: dict[str, list[Market]],
        unsubscribable: list[Market],
    ) -> None:
        subscribed_markets = _unique_markets(markets_by_category)
        subscribed_events = _unique_event_ids(subscribed_markets)
        unsub_events = _unique_event_ids(unsubscribable)
        market_list = [
            {
                "market_id": market.market_id,
                "title": market.question,
                "category": market.category,
                "event_id": market.event_id,
                "status": "subscribed",
            }
            for market in subscribed_markets
        ]
        market_list.extend(
            {
                "market_id": market.market_id,
                "title": market.question,
                "category": market.category,
                "event_id": market.event_id,
                "status": "grey",
            }
            for market in unsubscribable
        )
        token_count = len(self._token_meta)
        payload = MonitoringStatusPayload(
            status="connected",
            event_count=len(subscribed_events),
            market_count=len(subscribed_markets),
            token_count=token_count,
            unsubscribable_count=len(unsubscribable),
            unsubscribable_event_count=len(unsub_events),
        )
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            event_type=EventType.MONITORING_STATUS,
            payload=payload,
            raw={
                "subscribed_markets": [
                    {
                        "market_id": market.market_id,
                        "title": market.question,
                        "category": market.category,
                        "end_ts": market.end_ts,
                        "event_id": market.event_id,
                    }
                    for market in subscribed_markets
                ],
                "unsubscribable_markets": [
                    {
                        "market_id": market.market_id,
                        "title": market.question,
                        "category": market.category,
                        "end_ts": market.end_ts,
                        "event_id": market.event_id,
                    }
                    for market in unsubscribable
                ],
            },
        )
        logger.info(
            "monitoring_status_emit",
            market_count=len(subscribed_markets),
            token_count=token_count,
        )
        logger.info(
            "market_list",
            count=len(market_list),
            markets=market_list,
        )
        await self._sink.publish(event)

    async def _emit_unsubscribable_signals(
        self,
        markets: list[Market],
        window_sec: int,
    ) -> None:
        if self._polling_volume_threshold_usd <= 0:
            return
        threshold = self._polling_volume_threshold_usd * max(window_sec, 1) / 60.0
        now_ms = self._clock.now_ms()
        for market in markets:
            if not market.market_id:
                continue
            if market.end_ts and now_ms >= market.end_ts:
                logger.info(
                    "signal_suppressed",
                    reason="market_expired",
                    market_id=market.market_id,
                    end_ts=market.end_ts,
                    now_ms=now_ms,
                )
                continue
            volume = market.volume_24h
            if volume is None:
                continue
            prev = self._unsub_prev_volume.get(market.market_id)
            self._unsub_prev_volume[market.market_id] = volume
            if prev is None:
                continue
            delta = max(0.0, volume - prev)
            if delta < threshold:
                continue
            last_ts = self._unsub_cooldowns.get(market.market_id, 0)
            if now_ms - last_ts < self._polling_cooldown_ms:
                continue
            self._unsub_cooldowns[market.market_id] = now_ms
            event = DomainEvent(
                event_id=new_event_id(),
                ts_ms=now_ms,
                category=market.category,
                event_type=EventType.TRADE_SIGNAL,
                market_id=market.market_id,
                token_id=None,
                side=None,
                title=market.question,
                topic_key=market.topic_key,
                payload=WebVolumeSpikePayload(
                    signal=SignalType.WEB_VOLUME_SPIKE,
                    delta_volume=round(delta, 4),
                    volume_24h=volume,
                    window_sec=window_sec,
                ),
                metrics={"source": "gamma", "orderbook": "false"},
            )
            logger.info(
                "web_volume_spike_emit",
                market_id=market.market_id,
                delta_volume=delta,
                window_sec=window_sec,
            )
            await self._sink.publish(event)

    async def _emit_feed_lifecycle(self, message: MarketLifecycleMessage) -> None:
        status = message.status
        market_id = message.market_id
        token_id = message.token_id
        meta = self._token_meta.get(token_id) if token_id else None
        market = self._markets_by_id.get(market_id) if market_id else None
        if meta is None and market is None:
            logger.debug(
                "market_lifecycle_ignored",
                reason="untracked",
                event_type=status,
                market_id=market_id,
                token_id=token_id,
            )
            return

        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            category=(meta.category if meta else (market.category if market else None)),
            event_type=EventType.MARKET_LIFECYCLE,
            market_id=market_id or (meta.market_id if meta else None),
            token_id=token_id,
            title=(meta.title if meta else (market.question if market else message.title)),
            topic_key=(meta.topic_key if meta else (market.topic_key if market else None)),
            payload=MarketLifecyclePayload(status=status),
            raw=message.raw,
        )
        await self._sink.publish(event)

    async def _handle_resync(self, result: OrderBookUpdateResult | None) -> None:
        if not result or not result.resync_needed or not self._resync_on_gap:
            return
        if not self._token_ids:
            return
        now_ms = self._clock.now_ms()
        if now_ms - self._last_resync_ms < self._resync_min_interval_ms:
            logger.warning(
                "orderbook_resync_throttled",
                token_id=result.token_id,
                expected_seq=result.expected_seq,
                received_seq=result.received_seq,
            )
            return
        self._last_resync_ms = now_ms
        logger.warning(
            "orderbook_resync",
            token_id=result.token_id,
            expected_seq=result.expected_seq,
            received_seq=result.received_seq,
        )
        await self._feed.resubscribe(self._token_ids)


def _normalize_side(value: str | None) -> str | None:
    if value is None:
        return None
    upper = value.upper()
    if "YES" in upper:
        return "YES"
    if "NO" in upper:
        return "NO"
    return upper


def _unique_markets(markets_by_category: dict[str, list[Market]]) -> list[Market]:
    seen: set[str] = set()
    ordered: list[Market] = []
    for category, markets in markets_by_category.items():
        for market in markets:
            if not market.market_id or market.market_id in seen:
                continue
            if not market.category:
                market.category = category
            ordered.append(market)
            seen.add(market.market_id)
    return ordered


def _unique_event_ids(markets: list[Market]) -> set[str]:
    seen: set[str] = set()
    for market in markets:
        key = market.event_id or market.topic_key or market.market_id
        if key:
            seen.add(key)
    return seen
