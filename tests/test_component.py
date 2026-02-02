from __future__ import annotations

import pytest

from polymarket_monitor_engine.application.component import PolymarketComponent
from polymarket_monitor_engine.application.monitor import SignalDetector
from polymarket_monitor_engine.domain.events import EventType
from polymarket_monitor_engine.domain.models import Market


class FakeFeed:
    def __init__(self) -> None:
        self.subscriptions: list[list[str]] = []
        self.resubscriptions: list[list[str]] = []

    async def subscribe(self, token_ids: list[str]) -> None:
        self.subscriptions.append(token_ids)

    async def resubscribe(self, token_ids: list[str]) -> None:
        self.resubscriptions.append(token_ids)

    async def messages(self):
        if False:  # pragma: no cover
            yield None

    async def close(self) -> None:
        return None


class CaptureSink:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:
        self.events.append(event)


class FakeClock:
    def __init__(self, start_ms: int = 1_700_000_000_000) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self._now += int(seconds * 1000)


@pytest.mark.asyncio
async def test_handle_refresh_emits_subscription_and_candidates() -> None:
    feed = FakeFeed()
    sink = CaptureSink()
    clock = FakeClock()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=1000.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )

    component = PolymarketComponent(
        categories=["finance"],
        refresh_interval_sec=60,
        discovery=None,
        feed=feed,
        sink=sink,
        clock=clock,
        detector=detector,
        resync_on_gap=False,
        resync_min_interval_sec=30,
        polling_volume_threshold_usd=1000.0,
        polling_cooldown_sec=0,
    )

    markets_by_category = {
        "finance": [
            Market(
                market_id="m1",
                question="Q1",
                liquidity=10,
                volume_24h=20,
                token_ids=["t1", "t2"],
            )
        ]
    }

    await component._handle_refresh(markets_by_category)

    assert feed.subscriptions == [["t1", "t2"]]
    types = [event.event_type for event in sink.events]
    assert EventType.SUBSCRIPTION_CHANGED in types
    assert EventType.CANDIDATE_SELECTED in types


@pytest.mark.asyncio
async def test_emit_feed_lifecycle_maps_payload() -> None:
    feed = FakeFeed()
    sink = CaptureSink()
    clock = FakeClock()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=1000.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    component = PolymarketComponent(
        categories=["finance"],
        refresh_interval_sec=60,
        discovery=None,
        feed=feed,
        sink=sink,
        clock=clock,
        detector=detector,
        resync_on_gap=False,
        resync_min_interval_sec=30,
        polling_volume_threshold_usd=1000.0,
        polling_cooldown_sec=0,
    )

    payload = {
        "event_type": "new_market",
        "market_id": "m1",
        "asset_id": "t1",
        "question": "Hello",
    }

    await component._emit_feed_lifecycle(payload)

    assert sink.events
    event = sink.events[0]
    assert event.event_type == EventType.MARKET_LIFECYCLE
    assert event.metrics["status"] == "new"


@pytest.mark.asyncio
async def test_emit_unsubscribable_signals_emits_web_volume_spike() -> None:
    feed = FakeFeed()
    sink = CaptureSink()
    clock = FakeClock()
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=1000.0,
        big_volume_1m_usd=1000.0,
        big_wall_size=None,
        cooldown_sec=0,
        major_change_pct=0.0,
        major_change_window_sec=60,
        major_change_min_notional=0.0,
        major_change_source="trade",
    )
    component = PolymarketComponent(
        categories=["finance"],
        refresh_interval_sec=60,
        discovery=None,
        feed=feed,
        sink=sink,
        clock=clock,
        detector=detector,
        resync_on_gap=False,
        resync_min_interval_sec=30,
        polling_volume_threshold_usd=50.0,
        polling_cooldown_sec=0,
    )

    market = Market(
        market_id="m1",
        question="Grey Market",
        liquidity=10,
        volume_24h=100,
        enable_orderbook=False,
    )
    await component._emit_unsubscribable_signals([market], window_sec=60)
    market.volume_24h = 200
    await component._emit_unsubscribable_signals([market], window_sec=60)

    assert any(event.metrics.get("signal") == "web_volume_spike" for event in sink.events)
