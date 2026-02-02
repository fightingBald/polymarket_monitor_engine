from __future__ import annotations

import pytest

from polymarket_monitor_engine.application.discovery import MarketDiscovery, resolve_tag_ids
from polymarket_monitor_engine.domain.models import Market, Tag


class FakeCatalog:
    def __init__(self, tags: list[Tag], markets_by_tag: dict[str, list[Market]]) -> None:
        self._tags = tags
        self._markets_by_tag = markets_by_tag

    async def list_tags(self) -> list[Tag]:
        return self._tags

    async def list_markets(self, tag_id: str, active: bool = True, closed: bool = False) -> list[Market]:
        return self._markets_by_tag.get(tag_id, [])


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
    )

    results = await discovery.refresh(["finance", "missing"])
    assert "finance" in results
    assert "missing" in results
    assert results["missing"] == []
    assert len(results["finance"]) == 1
    assert results["finance"][0].market_id == "m1"
    assert results["finance"][0].category == "finance"
