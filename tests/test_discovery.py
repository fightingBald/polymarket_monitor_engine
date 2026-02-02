from __future__ import annotations

import pytest

from polymarket_monitor_engine.application.discovery import MarketDiscovery, resolve_tag_ids
from polymarket_monitor_engine.domain.models import Market, Tag


class FakeCatalog:
    def __init__(
        self,
        tags: list[Tag],
        markets_by_tag: dict[str, list[Market]],
        top_markets: list[Market] | None = None,
    ) -> None:
        self._tags = tags
        self._markets_by_tag = markets_by_tag
        self._top_markets = top_markets or []

    async def list_tags(self) -> list[Tag]:
        return self._tags

    async def list_markets(
        self,
        tag_id: str,
        active: bool = True,
        closed: bool = False,
    ) -> list[Market]:
        return self._markets_by_tag.get(tag_id, [])

    async def list_top_markets(
        self,
        limit: int,
        order: str | None,
        ascending: bool,
        featured_only: bool,
        closed: bool = False,
    ) -> list[Market]:
        return self._top_markets[:limit]


def test_resolve_tag_ids_prefers_exact() -> None:
    tags = [
        Tag(tag_id="1", slug="finance", name="Finance"),
        Tag(tag_id="2", slug="geopolitics", name="Geopolitics"),
    ]
    mapping = resolve_tag_ids(tags, ["finance", "geo"])
    assert mapping["finance"] == "1"
    assert mapping["geo"] == "2"


@pytest.mark.asyncio
async def test_market_discovery_refresh_selects_and_sets_category() -> None:
    tags = [Tag(tag_id="1", slug="finance", name="Finance")]
    markets = [
        Market(market_id="m1", question="A", liquidity=10, volume_24h=50),
        Market(market_id="m2", question="B", liquidity=25, volume_24h=10, active=False),
        Market(market_id="m3", question="C", liquidity=5, volume_24h=100),
        Market(market_id="m4", question="D", liquidity=999, volume_24h=100, enable_orderbook=False),
    ]
    catalog = FakeCatalog(tags=tags, markets_by_tag={"1": markets})
    discovery = MarketDiscovery(
        catalog=catalog,
        top_k_per_category=1,
        hot_sort=["liquidity", "volume_24h"],
        min_liquidity=None,
        keyword_allow=[],
        keyword_block=[],
        rolling_enabled=False,
        primary_selection_priority=["liquidity"],
        max_markets_per_topic=1,
        top_enabled=False,
        top_limit=10,
        top_order="volume24hr",
        top_ascending=False,
        top_featured_only=False,
        top_category_name="top",
    )

    results = await discovery.refresh(["finance", "missing"])
    markets_by_category = results.markets_by_category
    assert "finance" in markets_by_category
    assert "missing" in markets_by_category
    assert markets_by_category["missing"] == []
    assert len(markets_by_category["finance"]) == 1
    assert markets_by_category["finance"][0].market_id == "m1"
    assert markets_by_category["finance"][0].category == "finance"


@pytest.mark.asyncio
async def test_market_discovery_includes_top_markets() -> None:
    tags = [Tag(tag_id="1", slug="finance", name="Finance")]
    markets = [Market(market_id="m1", question="A", liquidity=10, volume_24h=50)]
    top_markets = [
        Market(market_id="m2", question="Top One", liquidity=999, volume_24h=999),
        Market(market_id="m1", question="Dup", liquidity=5, volume_24h=1),
    ]
    catalog = FakeCatalog(tags=tags, markets_by_tag={"1": markets}, top_markets=top_markets)
    discovery = MarketDiscovery(
        catalog=catalog,
        top_k_per_category=1,
        hot_sort=["liquidity", "volume_24h"],
        min_liquidity=None,
        keyword_allow=[],
        keyword_block=[],
        rolling_enabled=False,
        primary_selection_priority=["liquidity"],
        max_markets_per_topic=1,
        top_enabled=True,
        top_limit=5,
        top_order="volume24hr",
        top_ascending=False,
        top_featured_only=False,
        top_category_name="top",
    )

    results = await discovery.refresh(["finance"])
    markets_by_category = results.markets_by_category
    assert markets_by_category["finance"][0].market_id == "m1"
    assert markets_by_category["top"][0].market_id == "m2"
    assert markets_by_category["top"][0].category == "top"
    assert results.unsubscribable == []


@pytest.mark.asyncio
async def test_market_discovery_collects_unsubscribable_top_markets() -> None:
    tags = [Tag(tag_id="1", slug="finance", name="Finance")]
    markets = [Market(market_id="m1", question="A", liquidity=10, volume_24h=50)]
    top_markets = [
        Market(
            market_id="m2",
            question="No Orderbook",
            liquidity=999,
            volume_24h=999,
            enable_orderbook=False,
        )
    ]
    catalog = FakeCatalog(tags=tags, markets_by_tag={"1": markets}, top_markets=top_markets)
    discovery = MarketDiscovery(
        catalog=catalog,
        top_k_per_category=1,
        hot_sort=["liquidity", "volume_24h"],
        min_liquidity=None,
        keyword_allow=[],
        keyword_block=[],
        rolling_enabled=False,
        primary_selection_priority=["liquidity"],
        max_markets_per_topic=1,
        top_enabled=True,
        top_limit=5,
        top_order="volume24hr",
        top_ascending=False,
        top_featured_only=False,
        top_category_name="top",
    )

    results = await discovery.refresh(["finance"])
    assert results.unsubscribable[0].market_id == "m2"
    assert results.unsubscribable[0].category == "top"
