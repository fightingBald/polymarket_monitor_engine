from __future__ import annotations

from polymarket_monitor_engine.domain.models import Market
from polymarket_monitor_engine.domain.selection import select_primary_markets, select_top_markets


def test_select_top_markets_sorts_by_priority() -> None:
    markets = [
        Market(market_id="1", question="A", liquidity=10, volume_24h=50),
        Market(market_id="2", question="B", liquidity=25, volume_24h=10),
        Market(market_id="3", question="C", liquidity=20, volume_24h=60),
    ]
    selected = select_top_markets(
        markets,
        top_k=2,
        hot_sort=["liquidity", "volume_24h"],
        min_liquidity=None,
        keyword_allow=[],
        keyword_block=[],
    )
    assert [m.market_id for m in selected] == ["2", "3"]


def test_select_primary_markets_groups_by_topic() -> None:
    markets = [
        Market(market_id="1", question="BTC price", liquidity=10, volume_24h=50),
        Market(market_id="2", question="BTC price", liquidity=25, volume_24h=10),
        Market(market_id="3", question="Oil price", liquidity=20, volume_24h=60),
    ]
    selected = select_primary_markets(markets, priority=["liquidity", "volume_24h", "end_ts"])
    assert {m.market_id for m in selected} == {"2", "3"}
