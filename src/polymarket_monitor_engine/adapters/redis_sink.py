from __future__ import annotations

import orjson
import redis.asyncio as redis
import structlog

from polymarket_monitor_engine.domain.events import DomainEvent

logger = structlog.get_logger(__name__)


class RedisPubSubSink:
    def __init__(self, url: str, channel: str) -> None:
        self._redis = redis.from_url(url, decode_responses=False)
        self._channel = channel

    async def publish(self, event: DomainEvent) -> None:
        payload = orjson.dumps(event.model_dump())
        await self._redis.publish(self._channel, payload)
        logger.info("redis_publish", channel=self._channel, event_id=event.event_id)

    async def close(self) -> None:
        await self._redis.close()
