from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque

import structlog

from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.models import BookSnapshot, TradeTick
from polymarket_monitor_engine.ports.clock import ClockPort
from polymarket_monitor_engine.ports.sink import EventSinkPort
from polymarket_monitor_engine.util.ids import new_event_id
from polymarket_monitor_engine.application.types import TokenMeta

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class TradeWindow:
    entries: Deque[tuple[int, float]]
    total: float = 0.0

    def add(self, ts_ms: int, notional: float) -> None:
        self.entries.append((ts_ms, notional))
        self.total += notional

    def trim(self, cutoff_ms: int) -> None:
        while self.entries and self.entries[0][0] < cutoff_ms:
            _, notional = self.entries.popleft()
            self.total -= notional


class SignalDetector:
    def __init__(
        self,
        clock: ClockPort,
        sink: EventSinkPort,
        big_trade_usd: float,
        big_volume_1m_usd: float,
        big_wall_size: float | None,
        cooldown_sec: int,
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

    def update_registry(self, token_meta: dict[str, TokenMeta]) -> None:
        self._token_meta = token_meta
        self._windows = {token: window for token, window in self._windows.items() if token in token_meta}
        self._cooldowns = {
            key: ts for key, ts in self._cooldowns.items() if key[0] in token_meta
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

        if notional >= self._big_trade_usd:
            await self._emit_signal(
                meta=meta,
                signal_type="big_trade",
                metrics={
                    "notional": notional,
                    "price": trade.price,
                    "size": trade.size,
                },
            )

        if window.total >= self._big_volume_1m_usd:
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
        if self._big_wall_size is None:
            return
        meta = self._token_meta.get(book.token_id)
        if meta is None:
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
