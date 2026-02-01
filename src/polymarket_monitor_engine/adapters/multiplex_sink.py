from __future__ import annotations

from typing import Iterable

import structlog

from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.ports.sink import EventSinkPort

logger = structlog.get_logger(__name__)


class MultiplexEventSink:
    def __init__(
        self,
        sinks: dict[str, EventSinkPort],
        mode: str = "best_effort",
        required_sinks: Iterable[str] | None = None,
        routes: dict[str, list[str]] | None = None,
        transform: str = "full",
    ) -> None:
        self._sinks = sinks
        self._mode = mode
        self._required = set(required_sinks or [])
        self._routes = routes or {}
        self._transform = transform

    async def publish(self, event: DomainEvent) -> None:
        target_names = self._resolve_targets(event.event_type)
        payload = self._transform_event(event)
        errors: dict[str, Exception] = {}

        for name in target_names:
            sink = self._sinks.get(name)
            if sink is None:
                continue
            try:
                await sink.publish(payload)
            except Exception as exc:  # noqa: BLE001
                errors[name] = exc
                logger.warning("sink_publish_failed", sink=name, error=str(exc))

        if not errors:
            return
        if self._mode == "required_sinks" or self._required:
            missing = sorted(set(errors) & self._required)
            if missing:
                raise RuntimeError(f"Required sinks failed: {missing}")

    def _resolve_targets(self, event_type: EventType) -> list[str]:
        routed = self._routes.get(event_type.value) or self._routes.get(event_type.name)
        if routed:
            return routed
        return list(self._sinks.keys())

    def _transform_event(self, event: DomainEvent) -> DomainEvent:
        if self._transform == "compact":
            data = event.model_dump()
            data.pop("raw", None)
            return DomainEvent.model_validate(data)
        return event
