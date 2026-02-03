from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import structlog

from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.models import BookSnapshot, TradeTick
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

    async def handle_trade(self, trade: TradeTick) -> None:
        meta = self._token_meta.get(trade.token_id)
        if meta is None:
            return
        notional = trade.price * trade.size
        now_ms = self._clock.now_ms()
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
        if is_big_trade and is_volume_spike:
            logger.info(
                "signal_merge",
                signal_type="big_trade",
                merged_from="volume_spike_1m",
                token_id=meta.token_id,
            )
            await self._emit_signal(
                meta=meta,
                signal_type="big_trade",
                metrics={
                    "notional": notional,
                    "price": trade.price,
                    "size": trade.size,
                    "vol_1m": window.total,
                },
            )
            return

        if is_big_trade:
            await self._emit_signal(
                meta=meta,
                signal_type="big_trade",
                metrics={
                    "notional": notional,
                    "price": trade.price,
                    "size": trade.size,
                },
            )

        if is_volume_spike:
            await self._emit_signal(
                meta=meta,
                signal_type="volume_spike_1m",
                metrics={
                    "vol_1m": window.total,
                    "price": trade.price,
                    "size": trade.size,
                },
            )

    async def handle_book(self, book: BookSnapshot) -> None:
        meta = self._token_meta.get(book.token_id)
        if meta is None:
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
            signal_type="big_wall",
            metrics={
                "max_bid": max_bid,
                "max_ask": max_ask,
                "threshold": self._big_wall_size,
            },
            event_type=EventType.BOOK_SIGNAL,
        )

    async def _emit_signal(
        self,
        meta: TokenMeta,
        signal_type: str,
        metrics: dict[str, float | int | str],
        event_type: EventType = EventType.TRADE_SIGNAL,
    ) -> None:
        now_ms = self._clock.now_ms()
        cooldown_key = (meta.token_id, signal_type)
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
            metrics={"signal": signal_type, **metrics},
        )
        logger.info("signal_emit", event_type=event_type, signal_type=signal_type)
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
            signal_type="major_change",
            metrics={
                "pct_change": round(pct_change, 4),
                "pct_change_signed": round(pct_change_signed, 4),
                "direction": "up" if pct_change_signed > 0 else "down",
                "price": price,
                "prev_price": prev_price,
                "window_sec": self._major_change_window_ms // 1000,
                "notional": notional or 0.0,
                "source": source,
            },
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
