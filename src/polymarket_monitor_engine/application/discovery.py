from __future__ import annotations

import structlog

from polymarket_monitor_engine.domain.models import Market, Tag
from polymarket_monitor_engine.domain.selection import select_primary_markets, select_top_markets
from polymarket_monitor_engine.ports.catalog import CatalogPort

logger = structlog.get_logger(__name__)


class MarketDiscovery:
    def __init__(
        self,
        catalog: CatalogPort,
        top_k_per_category: int,
        hot_sort: list[str],
        min_liquidity: float | None,
        keyword_allow: list[str],
        keyword_block: list[str],
        rolling_enabled: bool,
        primary_selection_priority: list[str],
        max_markets_per_topic: int,
    ) -> None:
        self._catalog = catalog
        self._top_k = top_k_per_category
        self._hot_sort = hot_sort
        self._min_liquidity = min_liquidity
        self._keyword_allow = keyword_allow
        self._keyword_block = keyword_block
        self._rolling_enabled = rolling_enabled
        self._primary_priority = primary_selection_priority
        self._max_markets_per_topic = max_markets_per_topic

    async def refresh(self, categories: list[str]) -> dict[str, list[Market]]:
        tags = await self._catalog.list_tags()
        tag_map = resolve_tag_ids(tags, categories)
        results: dict[str, list[Market]] = {}

        for category in categories:
            tag_id = tag_map.get(category)
            if tag_id is None:
                logger.warning("tag_not_found", category=category)
                results[category] = []
                continue
            markets = await self._catalog.list_markets(tag_id, active=True, closed=False)
            active_markets = [m for m in markets if m.active and not m.closed and not m.resolved]
            for market in active_markets:
                market.category = category

            if self._rolling_enabled:
                active_markets = select_primary_markets(
                    active_markets,
                    self._primary_priority,
                    max_per_topic=self._max_markets_per_topic,
                )

            selected = select_top_markets(
                active_markets,
                top_k=self._top_k,
                hot_sort=self._hot_sort,
                min_liquidity=self._min_liquidity,
                keyword_allow=self._keyword_allow,
                keyword_block=self._keyword_block,
            )
            results[category] = selected
            logger.info("category_refresh", category=category, count=len(selected))

        return results


def resolve_tag_ids(tags: list[Tag], categories: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for category in categories:
        category_lower = category.lower()
        exact: Tag | None = None
        fuzzy: Tag | None = None
        for tag in tags:
            slug = (tag.slug or "").lower()
            name = (tag.name or "").lower()
            if slug == category_lower or name == category_lower:
                exact = tag
                break
            if category_lower in slug or category_lower in name:
                fuzzy = tag
        chosen = exact or fuzzy
        if chosen:
            mapping[category] = chosen.tag_id
    return mapping
