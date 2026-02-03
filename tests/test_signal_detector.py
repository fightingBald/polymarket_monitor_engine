from __future__ import annotations

import pytest

from polymarket_monitor_engine.application.monitor import SignalDetector
from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.events import EventType
from polymarket_monitor_engine.domain.models import BookSnapshot, TradeTick
from polymarket_monitor_engine.domain.schemas.event_payloads import (
    BigTradePayload,
    BigWallPayload,
    MajorChangePayload,
    SignalType,
    VolumeSpikePayload,
)


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
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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
    assert isinstance(event.payload, BigTradePayload)
    assert event.payload.signal == SignalType.BIG_TRADE


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
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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

    assert any(
        isinstance(event.payload, VolumeSpikePayload) for event in sink.events if event.payload
    )


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
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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

    assert any(isinstance(event.payload, BigWallPayload) for event in sink.events if event.payload)


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
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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

    major_events = [event for event in sink.events if event.event_type == EventType.TRADE_SIGNAL]
    assert major_events
    assert isinstance(major_events[0].payload, MajorChangePayload)


@pytest.mark.asyncio
async def test_major_change_from_book_uses_mid_price() -> None:
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
        major_change_source="book",
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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

    book1 = BookSnapshot(
        token_id="token-1",
        bids=[{"price": 1.0, "size": 5.0}],
        asks=[{"price": 1.2, "size": 5.0}],
        ts_ms=clock.now_ms(),
    )
    await detector.handle_book(book1)
    clock.advance(10_000)
    book2 = BookSnapshot(
        token_id="token-1",
        bids=[{"price": 1.3, "size": 5.0}],
        asks=[{"price": 1.5, "size": 5.0}],
        ts_ms=clock.now_ms(),
    )
    await detector.handle_book(book2)

    major_events = [event for event in sink.events if isinstance(event.payload, MajorChangePayload)]
    assert major_events
    event = major_events[0]
    assert event.payload.source == "book"
    assert event.payload.notional == 0.0
    assert event.payload.price == pytest.approx(1.4)
    assert event.payload.prev_price == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_major_change_low_price_uses_absolute_threshold() -> None:
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
        major_change_pct=5.0,
        major_change_window_sec=120,
        major_change_min_notional=0.0,
        major_change_source="trade",
        major_change_low_price_max=0.05,
        major_change_low_price_abs=0.01,
        major_change_spread_gate_k=0.0,
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

    trade1 = TradeTick(token_id="token-1", price=0.01, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade1)
    clock.advance(10_000)
    trade2 = TradeTick(token_id="token-1", price=0.015, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade2)

    assert not any(isinstance(event.payload, MajorChangePayload) for event in sink.events)


@pytest.mark.asyncio
async def test_major_change_low_price_ignores_pct_threshold() -> None:
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
        major_change_pct=200.0,
        major_change_window_sec=120,
        major_change_min_notional=0.0,
        major_change_source="trade",
        major_change_low_price_max=0.05,
        major_change_low_price_abs=0.01,
        major_change_spread_gate_k=0.0,
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

    trade1 = TradeTick(token_id="token-1", price=0.01, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade1)
    clock.advance(10_000)
    trade2 = TradeTick(token_id="token-1", price=0.025, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade2)

    assert any(isinstance(event.payload, MajorChangePayload) for event in sink.events)


@pytest.mark.asyncio
async def test_major_change_spread_gate_blocks_small_moves() -> None:
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
        major_change_pct=5.0,
        major_change_window_sec=120,
        major_change_min_notional=0.0,
        major_change_source="trade",
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=1.0,
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
        bids=[{"price": 0.4, "size": 10.0}],
        asks=[{"price": 0.5, "size": 10.0}],
        ts_ms=clock.now_ms(),
    )
    await detector.handle_book(book)

    trade1 = TradeTick(token_id="token-1", price=0.45, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade1)
    clock.advance(10_000)
    trade2 = TradeTick(token_id="token-1", price=0.52, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade2)
    clock.advance(10_000)
    trade3 = TradeTick(token_id="token-1", price=0.64, size=10.0, ts_ms=clock.now_ms())
    await detector.handle_trade(trade3)

    major_events = [event for event in sink.events if isinstance(event.payload, MajorChangePayload)]
    assert len(major_events) == 1
    assert major_events[0].payload is not None
    assert major_events[0].payload.price == pytest.approx(0.64)


@pytest.mark.asyncio
async def test_merge_big_trade_and_volume_spike_same_trade() -> None:
    from conftest import CaptureSink, FakeClock

    clock = FakeClock()
    sink = CaptureSink()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=100.0,
        big_volume_1m_usd=100.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
        major_change_low_price_max=0.0,
        major_change_low_price_abs=0.0,
        major_change_spread_gate_k=0.0,
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
    assert isinstance(event.payload, BigTradePayload)
    assert event.payload.vol_1m == pytest.approx(120.0)
