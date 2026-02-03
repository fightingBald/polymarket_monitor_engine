from __future__ import annotations

import pytest

from polymarket_monitor_engine.adapters.multiplex_sink import MultiplexEventSink
from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.schemas.event_payloads import (
    BigTradePayload,
    CandidateSelectedPayload,
    SignalType,
)


class CaptureSink:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class FailingSink:
    async def publish(self, event: DomainEvent) -> None:
        raise RuntimeError("boom")


def _sample_event(event_type: EventType = EventType.TRADE_SIGNAL) -> DomainEvent:
    payload = None
    if event_type == EventType.TRADE_SIGNAL:
        payload = BigTradePayload(
            signal=SignalType.BIG_TRADE,
            notional=1.0,
            price=1.0,
            size=1.0,
        )
    elif event_type == EventType.CANDIDATE_SELECTED:
        payload = CandidateSelectedPayload(market_count=1)
    return DomainEvent(
        event_id="evt-1",
        ts_ms=1,
        event_type=event_type,
        payload=payload,
        raw={"payload": True},
    )


@pytest.mark.asyncio
async def test_routes_only_send_to_target() -> None:
    sink_a = CaptureSink()
    sink_b = CaptureSink()
    mux = MultiplexEventSink(
        sinks={"a": sink_a, "b": sink_b},
        routes={EventType.TRADE_SIGNAL.value: ["a"]},
    )
    await mux.publish(_sample_event())
    assert len(sink_a.events) == 1
    assert len(sink_b.events) == 0


@pytest.mark.asyncio
async def test_required_sinks_raise() -> None:
    mux = MultiplexEventSink(
        sinks={"required": FailingSink()},
        required_sinks=["required"],
    )
    with pytest.raises(RuntimeError):
        await mux.publish(_sample_event())


@pytest.mark.asyncio
async def test_compact_transform_drops_raw() -> None:
    sink = CaptureSink()
    mux = MultiplexEventSink(sinks={"s": sink}, transform="compact")
    await mux.publish(_sample_event(EventType.CANDIDATE_SELECTED))
    assert sink.events[0].raw is None
