from __future__ import annotations

from dataclasses import dataclass

import structlog

from polymarket_monitor_engine.domain.models import Market, Tag
from polymarket_monitor_engine.domain.selection import select_primary_markets, select_top_markets
from polymarket_monitor_engine.ports.catalog import CatalogPort
from polymarket_monitor_engine.ports.clock import ClockPort

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class DiscoveryResult:
    markets_by_category: dict[str, list[Market]]
    unsubscribable: list[Market]


class MarketDiscovery:
    def __init__(
        self,
        catalog: CatalogPort,
        clock: ClockPort,
        top_k_per_category: int,
        hot_sort: list[str],
        min_liquidity: float | None,
        focus_keywords: list[str],
        keyword_allow: list[str],
        keyword_block: list[str],
        rolling_enabled: bool,
        primary_selection_priority: list[str],
        max_markets_per_topic: int,
        top_enabled: bool,
        top_limit: int,
        top_order: str | None,
        top_ascending: bool,
        top_featured_only: bool,
        top_category_name: str,
        drop_expired_markets: bool = True,
    ) -> None:
        self._catalog = catalog
        self._clock = clock
        self._top_k = top_k_per_category
        self._hot_sort = hot_sort
        self._min_liquidity = min_liquidity
        self._focus_keywords = [kw.strip().lower() for kw in focus_keywords if str(kw).strip()]
        self._keyword_allow = keyword_allow
        self._keyword_block = keyword_block
        self._rolling_enabled = rolling_enabled
        self._primary_priority = primary_selection_priority
        self._max_markets_per_topic = max_markets_per_topic
        self._top_enabled = top_enabled
        self._top_limit = top_limit
        self._top_order = top_order
        self._top_ascending = top_ascending
        self._top_featured_only = top_featured_only
        self._top_category_name = top_category_name
        self._drop_expired_markets = bool(drop_expired_markets)

    async def refresh(self, categories: list[str]) -> DiscoveryResult:
        now_ms = self._clock.now_ms()
        tags = await self._catalog.list_tags()
        tag_map = resolve_tag_ids(tags, categories)
        results: dict[str, list[Market]] = {}
        unsubscribable: list[Market] = []

        for category in categories:
            tag_id = tag_map.get(category)
            if tag_id is None:
                logger.warning("tag_not_found", category=category)
                results[category] = []
                continue
            markets = await self._catalog.list_markets(tag_id, active=True, closed=False)
            eligible_markets = [m for m in markets if m.active and not m.closed and not m.resolved]
            eligible_markets = self._filter_expired(eligible_markets, category, now_ms)
            eligible_markets = self._apply_focus_filter(eligible_markets, category=category)
            active_markets: list[Market] = []
            category_unsubscribable: list[Market] = []
            for market in eligible_markets:
                market.category = category
                if market.enable_orderbook is False:
                    category_unsubscribable.append(market)
                else:
                    active_markets.append(market)
            unsubscribable.extend(category_unsubscribable)

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

        if self._top_enabled:
            top_markets = await self._catalog.list_top_markets(
                limit=self._top_limit,
                order=self._top_order,
                ascending=self._top_ascending,
                featured_only=self._top_featured_only,
                closed=False,
            )
            top_markets = self._filter_expired(top_markets, self._top_category_name, now_ms)
            top_markets = self._apply_focus_filter(
                [m for m in top_markets if m.active and not m.closed and not m.resolved],
                category=self._top_category_name,
            )
            top_unsubscribable = [m for m in top_markets if m.enable_orderbook is False]
            for market in top_unsubscribable:
                market.category = self._top_category_name
            unsubscribable.extend(top_unsubscribable)

            active_markets = [m for m in top_markets if m.enable_orderbook is not False]
            active_markets = select_top_markets(
                active_markets,
                top_k=self._top_limit,
                hot_sort=[],
                min_liquidity=self._min_liquidity,
                keyword_allow=self._keyword_allow,
                keyword_block=self._keyword_block,
            )

            known_ids = {m.market_id for markets in results.values() for m in markets}
            top_selected: list[Market] = []
            for market in active_markets:
                if market.market_id in known_ids:
                    continue
                market.category = self._top_category_name
                top_selected.append(market)
            results[self._top_category_name] = top_selected
            logger.info("top_refresh", category=self._top_category_name, count=len(top_selected))

        return DiscoveryResult(markets_by_category=results, unsubscribable=unsubscribable)

    def _apply_focus_filter(self, markets: list[Market], category: str) -> list[Market]:
        if not self._focus_keywords:
            return markets
        before = len(markets)
        filtered = [market for market in markets if self._matches_focus_keyword(market.question)]
        logger.info(
            "focus_filter",
            category=category,
            before=before,
            after=len(filtered),
            keywords=self._focus_keywords,
        )
        return filtered

    def _filter_expired(
        self,
        markets: list[Market],
        category: str,
        now_ms: int,
    ) -> list[Market]:
        if not self._drop_expired_markets:
            return markets
        before = len(markets)
        filtered = [market for market in markets if market.end_ts is None or market.end_ts > now_ms]
        expired = before - len(filtered)
        if expired > 0:
            logger.info(
                "market_expired_filtered",
                category=category,
                before=before,
                after=len(filtered),
                expired=expired,
                now_ms=now_ms,
            )
        return filtered

    def _matches_focus_keyword(self, question: str) -> bool:
        if not question:
            return False
        text = question.lower()
        return any(keyword in text for keyword in self._focus_keywords)


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
