from __future__ import annotations

from typing import Protocol

from polymarket_monitor_engine.domain.models import Market, Tag


class CatalogPort(Protocol):
    async def list_tags(self) -> list[Tag]:
        ...

    async def list_markets(self, tag_id: str, active: bool = True, closed: bool = False) -> list[Market]:
        ...
