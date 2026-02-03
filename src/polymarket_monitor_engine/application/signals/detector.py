from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from threading import Lock

import structlog

from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.models import BookSnapshot, TradeTick
from polymarket_monitor_engine.domain.schemas.event_payloads import (
    BigTradePayload,
    BigWallPayload,
    MajorChangePayload,
    SignalPayload,
    SignalType,
    VolumeSpikePayload,
)
from polymarket_monitor_engine.ports.clock import ClockPort
from polymarket_monitor_engine.ports.sink import EventSinkPort
from polymarket_monitor_engine.util.ids import new_event_id

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class TradeWindow:
    entries: deque[tuple[int, float]]
    total: float = 0.0

    def add(self, ts_ms: int, notional: float) -> None:
        self.entries.append((ts_ms, notional))
        self.total += notional

    def trim(self, cutoff_ms: int) -> None:
        while self.entries and self.entries[0][0] < cutoff_ms:
            _, notional = self.entries.popleft()
            self.total -= notional


@dataclass(slots=True)
class TradeSignalBucket:
    market_id: str
    token_id: str
    side: str | None
    category: str
    title: str | None
    topic_key: str | None
    end_ts: int | None
    total_notional: float = 0.0
    total_size: float = 0.0
    last_price: float = 0.0
    last_size: float = 0.0
    max_vol_1m: float | None = None
    has_big_trade: bool = False
    has_volume_spike: bool = False
    task: asyncio.Task[None] | None = None


class SignalEngine:
    def __init__(
        self,
        clock: ClockPort,
        sink: EventSinkPort,
        big_trade_usd: float,
        big_volume_1m_usd: float,
        big_wall_size: float | None,
        cooldown_sec: int,
        major_change_pct: float,
        major_change_window_sec: int,
        major_change_min_notional: float,
        major_change_source: str,
        major_change_low_price_max: float,
        major_change_low_price_abs: float,
        major_change_spread_gate_k: float,
        high_confidence_threshold: float = 0.0,
        reverse_allow_threshold: float = 0.0,
        merge_window_sec: float = 0.0,
        drop_expired_markets: bool = True,
    ) -> None:
        self._clock = clock
        self._sink = sink
        self._big_trade_usd = big_trade_usd
        self._big_volume_1m_usd = big_volume_1m_usd
        self._big_wall_size = big_wall_size
        self._cooldown_ms = cooldown_sec * 1000
        self._windows: dict[str, TradeWindow] = {}
        self._cooldowns: dict[tuple[str, str], int] = {}
        self._token_meta: dict[str, TokenMeta] = {}
        self._last_price: dict[str, tuple[float, int]] = {}
        self._major_change_pct = major_change_pct
        self._major_change_window_ms = major_change_window_sec * 1000
        self._major_change_min_notional = major_change_min_notional
        self._major_change_source = major_change_source.lower()
        self._major_change_low_price_max = max(0.0, float(major_change_low_price_max))
        self._major_change_low_price_abs = max(0.0, float(major_change_low_price_abs))
        self._major_change_spread_gate_k = max(0.0, float(major_change_spread_gate_k))
        self._best_quote: dict[str, tuple[float, float]] = {}
        self._high_confidence_threshold = min(1.0, max(0.0, float(high_confidence_threshold)))
        self._reverse_allow_threshold = min(1.0, max(0.0, float(reverse_allow_threshold)))
        self._merge_window_sec = max(0.0, float(merge_window_sec))
        self._drop_expired_markets = bool(drop_expired_markets)
        self._trade_buckets: dict[tuple[str, str], TradeSignalBucket] = {}
        self._bucket_lock = Lock()

    def update_registry(self, token_meta: dict[str, TokenMeta]) -> None:
        self._token_meta = token_meta
        self._windows = {
            token: window for token, window in self._windows.items() if token in token_meta
        }
        self._cooldowns = {key: ts for key, ts in self._cooldowns.items() if key[0] in token_meta}
        self._last_price = {
            token: data for token, data in self._last_price.items() if token in token_meta
        }
        self._best_quote = {
            token: quote for token, quote in self._best_quote.items() if token in token_meta
        }
        if self._trade_buckets:
            active_markets = {meta.market_id for meta in token_meta.values()}
            with self._bucket_lock:
                for key, bucket in list(self._trade_buckets.items()):
                    if key[0] in active_markets:
                        continue
                    if bucket.task is not None:
                        bucket.task.cancel()
                    self._trade_buckets.pop(key, None)

    async def handle_trade(self, trade: TradeTick) -> None:
        meta = self._token_meta.get(trade.token_id)
        if meta is None:
            return
        now_ms = self._clock.now_ms()
        if self._is_market_expired(meta, now_ms):
            logger.info(
                "signal_suppressed",
                reason="market_expired",
                market_id=meta.market_id,
                token_id=meta.token_id,
                end_ts=meta.end_ts,
                now_ms=now_ms,
            )
            return
        notional = trade.price * trade.size
        window = self._windows.setdefault(trade.token_id, TradeWindow(entries=deque()))
        window.add(trade.ts_ms, notional)
        window.trim(now_ms - 60_000)

        if self._major_change_source in {"trade", "any"}:
            await self._maybe_emit_major_change(
                meta=meta,
                price=trade.price,
                ts_ms=trade.ts_ms,
                notional=notional,
                source="trade",
            )

        is_big_trade = notional >= self._big_trade_usd
        is_volume_spike = window.total >= self._big_volume_1m_usd
        if (is_big_trade or is_volume_spike) and self._is_high_confidence_market(trade.price):
            if not self._is_reverse_allow_price(trade.price):
                logger.info(
                    "signal_suppressed",
                    reason="high_confidence",
                    market_id=meta.market_id,
                    token_id=meta.token_id,
                    side=meta.side,
                    price=trade.price,
                    threshold=self._high_confidence_threshold,
                )
                return
            logger.debug(
                "signal_allowed",
                reason="reverse_allow",
                market_id=meta.market_id,
                token_id=meta.token_id,
                side=meta.side,
                price=trade.price,
                threshold=self._reverse_allow_threshold,
            )

        if self._merge_window_sec > 0 and (is_big_trade or is_volume_spike):
            await self._enqueue_trade_bucket(
                meta=meta,
                trade=trade,
                notional=notional,
                vol_1m=window.total,
                is_big_trade=is_big_trade,
                is_volume_spike=is_volume_spike,
            )
            return
        if is_big_trade and is_volume_spike:
            logger.info(
                "signal_merge",
                signal_type="big_trade",
                merged_from="volume_spike_1m",
                token_id=meta.token_id,
            )
            await self._emit_signal(
                meta=meta,
                payload=BigTradePayload(
                    signal=SignalType.BIG_TRADE,
                    notional=notional,
                    price=trade.price,
                    size=trade.size,
                    vol_1m=window.total,
                ),
            )
            return

        if is_big_trade:
            await self._emit_signal(
                meta=meta,
                payload=BigTradePayload(
                    signal=SignalType.BIG_TRADE,
                    notional=notional,
                    price=trade.price,
                    size=trade.size,
                ),
            )

        if is_volume_spike:
            await self._emit_signal(
                meta=meta,
                payload=VolumeSpikePayload(
                    signal=SignalType.VOLUME_SPIKE_1M,
                    vol_1m=window.total,
                    price=trade.price,
                    size=trade.size,
                ),
            )

    async def handle_book(self, book: BookSnapshot) -> None:
        meta = self._token_meta.get(book.token_id)
        if meta is None:
            return
        if self._is_market_expired(meta, self._clock.now_ms()):
            logger.info(
                "signal_suppressed",
                reason="market_expired",
                market_id=meta.market_id,
                token_id=meta.token_id,
                end_ts=meta.end_ts,
            )
            return

        best_bid = max((level.price for level in book.bids), default=None)
        best_ask = min((level.price for level in book.asks), default=None)
        if best_bid is not None and best_ask is not None:
            self._best_quote[book.token_id] = (best_bid, best_ask)
        else:
            self._best_quote.pop(book.token_id, None)

        if (
            self._major_change_source in {"book", "any"}
            and best_bid is not None
            and best_ask is not None
        ):
            mid = (best_bid + best_ask) / 2.0
            await self._maybe_emit_major_change(
                meta=meta,
                price=mid,
                ts_ms=book.ts_ms,
                notional=None,
                source="book",
                best_bid=best_bid,
                best_ask=best_ask,
            )

        if self._big_wall_size is None:
            return

        max_bid = max((level.size for level in book.bids), default=0.0)
        max_ask = max((level.size for level in book.asks), default=0.0)
        if max(max_bid, max_ask) < self._big_wall_size:
            return
        await self._emit_signal(
            meta=meta,
            payload=BigWallPayload(
                signal=SignalType.BIG_WALL,
                max_bid=max_bid,
                max_ask=max_ask,
                threshold=float(self._big_wall_size),
            ),
            event_type=EventType.BOOK_SIGNAL,
        )

    async def _enqueue_trade_bucket(
        self,
        meta: TokenMeta,
        trade: TradeTick,
        notional: float,
        vol_1m: float,
        is_big_trade: bool,
        is_volume_spike: bool,
    ) -> None:
        key = self._bucket_key(meta)
        with self._bucket_lock:
            bucket = self._trade_buckets.get(key)
            if bucket is None:
                bucket = TradeSignalBucket(
                    market_id=meta.market_id,
                    token_id=meta.token_id,
                    side=meta.side,
                    category=meta.category,
                    title=meta.title,
                    topic_key=meta.topic_key,
                    end_ts=meta.end_ts,
                )
                self._trade_buckets[key] = bucket
                bucket.task = asyncio.create_task(self._flush_trade_bucket(key))
            bucket.token_id = meta.token_id
            bucket.side = meta.side
            bucket.category = meta.category
            bucket.title = meta.title
            bucket.topic_key = meta.topic_key
            bucket.end_ts = meta.end_ts
            bucket.last_price = trade.price
            bucket.last_size = trade.size
            if is_big_trade:
                bucket.has_big_trade = True
                bucket.total_notional += notional
                bucket.total_size += trade.size
            if is_volume_spike:
                bucket.has_volume_spike = True
                bucket.max_vol_1m = (
                    vol_1m if bucket.max_vol_1m is None else max(bucket.max_vol_1m, vol_1m)
                )

    async def _flush_trade_bucket(self, key: tuple[str, str]) -> None:
        await asyncio.sleep(self._merge_window_sec)
        with self._bucket_lock:
            bucket = self._trade_buckets.pop(key, None)
        if bucket is None:
            return
        meta = self._token_meta.get(bucket.token_id)
        if meta is None:
            return
        now_ms = self._clock.now_ms()
        if self._is_market_expired(meta, now_ms):
            logger.info(
                "signal_suppressed",
                reason="market_expired",
                market_id=meta.market_id,
                token_id=meta.token_id,
                end_ts=meta.end_ts,
                now_ms=now_ms,
            )
            return
        if bucket.has_big_trade:
            if bucket.total_size > 0:
                avg_price = bucket.total_notional / bucket.total_size
            else:
                avg_price = bucket.last_price
            payload: SignalPayload = BigTradePayload(
                signal=SignalType.BIG_TRADE,
                notional=bucket.total_notional,
                price=avg_price,
                size=bucket.total_size or bucket.last_size,
                vol_1m=bucket.max_vol_1m,
            )
        else:
            payload = VolumeSpikePayload(
                signal=SignalType.VOLUME_SPIKE_1M,
                vol_1m=bucket.max_vol_1m or 0.0,
                price=bucket.last_price,
                size=bucket.last_size,
            )
        logger.info(
            "signal_merge",
            reason="trade_window_flush",
            signal_type=payload.signal.value,
            market_id=meta.market_id,
            token_id=meta.token_id,
            side=meta.side,
            window_sec=self._merge_window_sec,
        )
        await self._emit_signal(meta=meta, payload=payload)

    @staticmethod
    def _bucket_key(meta: TokenMeta) -> tuple[str, str]:
        return (meta.market_id, (meta.side or "n/a").upper())

    def _is_market_expired(self, meta: TokenMeta, now_ms: int) -> bool:
        if not self._drop_expired_markets:
            return False
        if meta.end_ts is None:
            return False
        return now_ms >= meta.end_ts

    def _is_high_confidence_market(self, price: float) -> bool:
        if self._high_confidence_threshold <= 0:
            return False
        if price < 0 or price > 1:
            return False
        confidence = max(price, 1.0 - price)
        return confidence >= self._high_confidence_threshold

    def _is_reverse_allow_price(self, price: float) -> bool:
        if self._reverse_allow_threshold <= 0:
            return False
        if price < 0 or price > 1:
            return False
        return price <= self._reverse_allow_threshold

    async def _emit_signal(
        self,
        meta: TokenMeta,
        payload: SignalPayload,
        metrics: dict[str, float | int | str] | None = None,
        event_type: EventType = EventType.TRADE_SIGNAL,
    ) -> None:
        now_ms = self._clock.now_ms()
        cooldown_key = (meta.token_id, payload.signal.value)
        last_ts = self._cooldowns.get(cooldown_key, 0)
        if now_ms - last_ts < self._cooldown_ms:
            return
        self._cooldowns[cooldown_key] = now_ms

        event = DomainEvent(
            event_id=new_event_id(),
            ts_ms=now_ms,
            category=meta.category,
            event_type=event_type,
            market_id=meta.market_id,
            token_id=meta.token_id,
            side=meta.side,
            title=meta.title,
            topic_key=meta.topic_key,
            payload=payload,
            metrics=metrics or {},
        )
        logger.info(
            "signal_emit",
            event_type=event_type,
            signal_type=payload.signal.value,
        )
        await self._sink.publish(event)

    async def _maybe_emit_major_change(
        self,
        meta: TokenMeta,
        price: float,
        ts_ms: int,
        notional: float | None,
        source: str,
        best_bid: float | None = None,
        best_ask: float | None = None,
    ) -> None:
        if self._major_change_pct <= 0:
            return
        previous = self._last_price.get(meta.token_id)
        self._last_price[meta.token_id] = (price, ts_ms)
        if previous is None:
            return
        prev_price, prev_ts = previous
        if prev_price <= 0:
            return
        if ts_ms - prev_ts > self._major_change_window_ms:
            return
        delta = price - prev_price
        abs_delta = abs(delta)
        if self._major_change_spread_gate_k > 0:
            spread = self._resolve_spread(meta.token_id, best_bid, best_ask)
            if (
                spread is not None
                and spread > 0
                and abs_delta <= self._major_change_spread_gate_k * spread
            ):
                logger.debug(
                    "signal_suppressed",
                    reason="spread_gate",
                    token_id=meta.token_id,
                    spread=spread,
                    delta=abs_delta,
                )
                return
        pct_change_signed = delta / prev_price * 100
        pct_change = abs(pct_change_signed)
        if self._use_low_price_abs(prev_price, price):
            if abs_delta < self._major_change_low_price_abs:
                logger.debug(
                    "signal_suppressed",
                    reason="low_price_abs",
                    token_id=meta.token_id,
                    delta=abs_delta,
                )
                return
        else:
            if pct_change < self._major_change_pct:
                return
        if self._major_change_min_notional > 0 and (
            notional is None or notional < self._major_change_min_notional
        ):
            return
        await self._emit_signal(
            meta=meta,
            payload=MajorChangePayload(
                signal=SignalType.MAJOR_CHANGE,
                pct_change=round(pct_change, 4),
                pct_change_signed=round(pct_change_signed, 4),
                direction="up" if pct_change_signed > 0 else "down",
                price=price,
                prev_price=prev_price,
                window_sec=self._major_change_window_ms // 1000,
                notional=notional or 0.0,
                source=source,
            ),
            event_type=EventType.TRADE_SIGNAL,
        )

    def _use_low_price_abs(self, prev_price: float, price: float) -> bool:
        if self._major_change_low_price_abs <= 0:
            return False
        if self._major_change_low_price_max <= 0:
            return False
        return min(prev_price, price) <= self._major_change_low_price_max

    def _resolve_spread(
        self,
        token_id: str,
        best_bid: float | None,
        best_ask: float | None,
    ) -> float | None:
        if best_bid is not None and best_ask is not None:
            return max(0.0, best_ask - best_bid)
        quote = self._best_quote.get(token_id)
        if quote is None:
            return None
        return max(0.0, quote[1] - quote[0])
