from __future__ import annotations

import pytest

from polymarket_monitor_engine.application.monitor import SignalDetector
from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.events import EventType
from polymarket_monitor_engine.domain.models import BookSnapshot, TradeTick


@pytest.mark.asyncio
async def test_big_trade_emits_signal() -> None:
    from conftest import CaptureSink, FakeClock

    clock = FakeClock()
    sink = CaptureSink()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=100.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    detector.update_registry(
        {
            "token-1": TokenMeta(
                token_id="token-1",
                market_id="m1",
                category="finance",
                title="Test",
                side="YES",
                topic_key="test",
            )
        }
    )

    trade = TradeTick(token_id="token-1", price=2.0, size=60.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade)

    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.metrics["signal"] == "big_trade"


@pytest.mark.asyncio
async def test_volume_spike_emits_signal() -> None:
    from conftest import CaptureSink, FakeClock

    clock = FakeClock()
    sink = CaptureSink()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=1000.0,
        big_volume_1m_usd=100.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    detector.update_registry(
        {
            "token-1": TokenMeta(
                token_id="token-1",
                market_id="m1",
                category="finance",
                title="Test",
                side="YES",
                topic_key="test",
            )
        }
    )

    trade = TradeTick(token_id="token-1", price=2.0, size=30.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade)
    clock.advance(10_000)
    trade2 = TradeTick(token_id="token-1", price=2.0, size=30.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade2)

    assert any(event.metrics["signal"] == "volume_spike_1m" for event in sink.events)


@pytest.mark.asyncio
async def test_cooldown_suppresses_duplicate_signals() -> None:
    from conftest import CaptureSink, FakeClock

    clock = FakeClock()
    sink = CaptureSink()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=100.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=None,
        cooldown_sec=60,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    detector.update_registry(
        {
            "token-1": TokenMeta(
                token_id="token-1",
                market_id="m1",
                category="finance",
                title="Test",
                side="YES",
                topic_key="test",
            )
        }
    )

    trade = TradeTick(token_id="token-1", price=2.0, size=60.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade)
    await detector.handle_trade(trade)

    assert len(sink.events) == 1


@pytest.mark.asyncio
async def test_big_wall_emits_signal() -> None:
    from conftest import CaptureSink, FakeClock

    clock = FakeClock()
    sink = CaptureSink()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=1000.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=50.0,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    detector.update_registry(
        {
            "token-1": TokenMeta(
                token_id="token-1",
                market_id="m1",
                category="finance",
                title="Test",
                side="YES",
                topic_key="test",
            )
        }
    )

    book = BookSnapshot(
        token_id="token-1",
        bids=[{"price": 1.0, "size": 60.0}],
        asks=[],
        ts_ms=clock.now_ms(),
    )
    await detector.handle_book(book)

    assert any(event.metrics.get("signal") == "big_wall" for event in sink.events)


@pytest.mark.asyncio
async def test_major_change_emits_price_signal() -> None:
    from conftest import CaptureSink, FakeClock

    clock = FakeClock()
    sink = CaptureSink()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=1000.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=10.0,
        major_change_window_sec=120,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    detector.update_registry(
        {
            "token-1": TokenMeta(
                token_id="token-1",
                market_id="m1",
                category="finance",
                title="Test",
                side="YES",
                topic_key="test",
            )
        }
    )

    trade1 = TradeTick(token_id="token-1", price=1.0, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade1)
    clock.advance(10_000)
    trade2 = TradeTick(token_id="token-1", price=1.2, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade2)

    assert any(event.event_type == EventType.PRICE_SIGNAL for event in sink.events)
