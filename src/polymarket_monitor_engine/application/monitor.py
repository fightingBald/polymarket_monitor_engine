from __future__ import annotations

from polymarket_monitor_engine.application.signals.detector import SignalEngine
from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.models import BookSnapshot, TradeTick
from polymarket_monitor_engine.ports.clock import ClockPort
from polymarket_monitor_engine.ports.sink import EventSinkPort


class SignalDetector:
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
        self._engine = SignalEngine(
            clock=clock,
            sink=sink,
            big_trade_usd=big_trade_usd,
            big_volume_1m_usd=big_volume_1m_usd,
            big_wall_size=big_wall_size,
            cooldown_sec=cooldown_sec,
            major_change_pct=major_change_pct,
            major_change_window_sec=major_change_window_sec,
            major_change_min_notional=major_change_min_notional,
            major_change_source=major_change_source,
            major_change_low_price_max=major_change_low_price_max,
            major_change_low_price_abs=major_change_low_price_abs,
            major_change_spread_gate_k=major_change_spread_gate_k,
            high_confidence_threshold=high_confidence_threshold,
            reverse_allow_threshold=reverse_allow_threshold,
            merge_window_sec=merge_window_sec,
            drop_expired_markets=drop_expired_markets,
        )

    def update_registry(self, token_meta: dict[str, TokenMeta]) -> None:
        self._engine.update_registry(token_meta)

    async def handle_trade(self, trade: TradeTick) -> None:
        await self._engine.handle_trade(trade)

    async def handle_book(self, book: BookSnapshot) -> None:
        await self._engine.handle_book(book)
