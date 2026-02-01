from __future__ import annotations

import structlog

from polymarket_monitor_engine.domain.events import DomainEvent

logger = structlog.get_logger(__name__)


class StdoutSink:
    async def publish(self, event: DomainEvent) -> None:
        logger.info("domain_event", payload=event.model_dump())
