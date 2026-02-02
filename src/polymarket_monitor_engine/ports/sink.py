from __future__ import annotations

from typing import Protocol

from polymarket_monitor_engine.domain.events import DomainEvent


class EventSinkPort(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...
