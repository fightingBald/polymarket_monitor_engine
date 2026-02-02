from __future__ import annotations

import asyncio
from typing import Any

import structlog

from polymarket_monitor_engine.application.discovery import MarketDiscovery
from polymarket_monitor_engine.application.monitor import SignalDetector
from polymarket_monitor_engine.application.parsers import parse_book, parse_trade
from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.models import Market
from polymarket_monitor_engine.domain.selection import normalize_topic
from polymarket_monitor_engine.ports.clock import ClockPort
from polymarket_monitor_engine.ports.feed import FeedPort
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
    ) -> None:
        self._categories = categories
        self._refresh_interval_sec = refresh_interval_sec
        self._discovery = discovery
        self._feed = feed
        self._sink = sink
        self._clock = clock
        self._detector = detector
        self._token_meta: dict[str, TokenMeta] = {}
        self._markets_by_id: dict[str, Market] = {}
        self._token_ids: list[str] = []

    async def run(self) -> None:
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self._refresh_loop())
                tg.create_task(self._consume_loop())
        finally:
            await self._feed.close()

    async def _refresh_loop(self) -> None:
        while True:
            try:
                start_ms = self._clock.now_ms()
                markets_by_category = await self._discovery.refresh(self._categories)
                await self._handle_refresh(markets_by_category)
                duration_ms = self._clock.now_ms() - start_ms
                await self._emit_health("refresh_ok", {"duration_ms": duration_ms})
            except Exception as exc:  # noqa: BLE001
                await self._emit_health("refresh_error", {"error": str(exc)})
                logger.warning("refresh_failed", error=str(exc))
            await self._clock.sleep(self._refresh_interval_sec)

    async def _consume_loop(self) -> None:
        async for message in self._feed.messages():
            if message.kind == "trade":
                trade = parse_trade(message.payload)
                if trade:
                    await self._detector.handle_trade(trade)
            elif message.kind == "book":
                book = parse_book(message.payload)
                if book:
                    await self._detector.handle_book(book)
            elif message.kind == "market_lifecycle":
                await self._emit_feed_lifecycle(message.payload)
            elif message.kind in {"price_change", "best_bid_ask"}:
                logger.debug("feed_price_update", kind=message.kind)
            else:
                logger.debug("feed_message_ignored", payload=message.payload)

    async def _handle_refresh(self, markets_by_category: dict[str, list[Market]]) -> None:
        new_markets: dict[str, Market] = {}
        for markets in markets_by_category.values():
            for market in markets:
                new_markets[market.market_id] = market

        await self._emit_market_lifecycle(new_markets)

        token_meta = self._build_token_meta(markets_by_category)
        self._detector.update_registry(token_meta)

        token_ids = sorted(token_meta.keys())
        if token_ids != self._token_ids:
            await self._feed.subscribe(token_ids)
            await self._emit_subscription_changed(token_ids)
            self._token_ids = token_ids

        for category, markets in markets_by_category.items():
            await self._emit_candidates(category, markets)

        self._token_meta = token_meta
        self._markets_by_id = new_markets

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
            metrics={"market_count": len(markets)},
            raw=payload,
        )
        await self._sink.publish(event)

    async def _emit_subscription_changed(self, token_ids: list[str]) -> None:
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            event_type=EventType.SUBSCRIPTION_CHANGED,
            metrics={"token_count": len(token_ids)},
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
            metrics={"status": status, "end_ts": market.end_ts or 0},
        )
        await self._sink.publish(event)

    async def _emit_health(self, status: str, metrics: dict[str, Any]) -> None:
        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            event_type=EventType.HEALTH_EVENT,
            metrics={"status": status, **metrics},
        )
        await self._sink.publish(event)

    async def _emit_feed_lifecycle(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.get("event_type") or payload.get("type") or "").lower()
        status = "new" if event_type == "new_market" else "resolved"
        market_id = (
            str(
                payload.get("market")
                or payload.get("conditionId")
                or payload.get("condition_id")
                or payload.get("market_id")
                or payload.get("marketId")
                or ""
            )
            or None
        )
        token_id = payload.get("asset_id") or payload.get("assetId") or payload.get("token_id")
        if token_id is None:
            assets_ids = payload.get("assets_ids") or payload.get("asset_ids")
            if isinstance(assets_ids, list) and assets_ids:
                token_id = assets_ids[0]
        token_id = str(token_id) if token_id else None
        meta = self._token_meta.get(token_id) if token_id else None
        market = self._markets_by_id.get(market_id) if market_id else None

        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=self._clock.now_ms(),
            category=(meta.category if meta else (market.category if market else None)),
            event_type=EventType.MARKET_LIFECYCLE,
            market_id=market_id or (meta.market_id if meta else None),
            token_id=token_id,
            title=(
                meta.title
                if meta
                else (
                    market.question if market else payload.get("question") or payload.get("title")
                )
            ),
            topic_key=(meta.topic_key if meta else (market.topic_key if market else None)),
            metrics={"status": status},
            raw=payload,
        )
        await self._sink.publish(event)


def _normalize_side(value: str | None) -> str | None:
    if value is None:
        return None
    upper = value.upper()
    if "YES" in upper:
        return "YES"
    if "NO" in upper:
        return "NO"
    return upper
