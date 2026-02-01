from __future__ import annotations

import re
from typing import Iterable

from polymarket_monitor_engine.domain.models import Market


def normalize_topic(text: str) -> str:
    lowered = text.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
    return re.sub(r"\s+", " ", cleaned)


def assign_topic_keys(markets: Iterable[Market]) -> None:
    for market in markets:
        if not market.topic_key:
            market.topic_key = normalize_topic(market.question)


def _priority_value(market: Market, key: str) -> float | int:
    if key == "liquidity":
        return -(market.liquidity or 0.0)
    if key == "volume_24h":
        return -(market.volume_24h or 0.0)
    if key == "end_ts":
        return market.end_ts or 2**63
    return 0


def select_primary_markets(
    markets: list[Market],
    priority: list[str],
    max_per_topic: int = 1,
) -> list[Market]:
    assign_topic_keys(markets)
    grouped: dict[str, list[Market]] = {}
    for market in markets:
        key = market.topic_key or market.market_id
        grouped.setdefault(key, []).append(market)

    selected: list[Market] = []
    for group in grouped.values():
        group.sort(key=lambda m: tuple(_priority_value(m, key) for key in priority))
        selected.extend(group[:max_per_topic])

    return selected


def select_top_markets(
    markets: list[Market],
    top_k: int,
    hot_sort: list[str],
    min_liquidity: float | None,
    keyword_allow: list[str],
    keyword_block: list[str],
) -> list[Market]:
    filtered: list[Market] = []
    allow = [kw.lower() for kw in keyword_allow]
    block = [kw.lower() for kw in keyword_block]

    for market in markets:
        if min_liquidity is not None and (market.liquidity or 0) < min_liquidity:
            continue
        question = market.question.lower()
        if allow and not any(kw in question for kw in allow):
            continue
        if block and any(kw in question for kw in block):
            continue
        filtered.append(market)

    filtered.sort(key=lambda m: tuple(_priority_value(m, key) for key in hot_sort))
    return filtered[:top_k]
