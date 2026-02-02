from __future__ import annotations

import pytest

from polymarket_monitor_engine.adapters import redis_sink
from polymarket_monitor_engine.domain.events import DomainEvent, EventType


class FakeRedis:
    def __init__(self) -> None:
        self.published = []
        self.closed = False

    async def publish(self, channel: str, payload: bytes) -> None:
        self.published.append((channel, payload))

    async def close(self) -> None:
        self.closed = True


def _event() -> DomainEvent:
    return DomainEvent(event_id="evt-1", ts_ms=1, event_type=EventType.HEALTH_EVENT)


@pytest.mark.asyncio
async def test_redis_sink_publishes(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(redis_sink.redis, "from_url", lambda *args, **kwargs: fake)

    sink = redis_sink.RedisPubSubSink(url="redis://localhost:6379/0", channel="chan")
    await sink.publish(_event())
    await sink.close()

    assert fake.published
    assert fake.published[0][0] == "chan"
    assert fake.closed is True
