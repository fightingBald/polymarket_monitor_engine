from __future__ import annotations

import httpx
import pytest

from polymarket_monitor_engine.adapters.gamma_http import GammaHttpCatalog


def test_parse_market_and_outcomes() -> None:
    raw = {
        "condition_id": "m1",
        "question": "Test?",
        "active": "true",
        "closed": "false",
        "resolved": "false",
        "endDateIso": "2024-01-01T00:00:00Z",
        "liquidityUSD": "12.5",
        "volume24h": "3.2",
        "clobTokenIds": '["t1", "t2"]',
        "outcomes": '[{"token_id":"t3","side":"YES"}]',
        "tokens": [{"asset_id": "t4", "side": "NO"}],
    }
    market = GammaHttpCatalog._parse_market(raw)

    assert market.market_id == "m1"
    assert market.active is True
    assert market.closed is False
    assert market.resolved is False
    assert market.end_ts == 1_704_067_200_000
    assert market.liquidity == 12.5
    assert market.volume_24h == 3.2
    assert set(market.token_ids) == {"t1", "t2", "t3", "t4"}


@pytest.mark.asyncio
async def test_list_tags_paginates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/tags":
            return httpx.Response(404)
        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", 2))
        pages = {
            0: [{"id": "1", "slug": "finance"}, {"id": "2", "slug": "geo"}],
            2: [{"id": "3", "slug": "sports"}],
        }
        items = pages.get(offset, [])
        # simulate smaller than limit to end pagination
        if offset and len(items) >= limit:
            items = items[: limit - 1]
        return httpx.Response(200, json={"data": items})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="https://example.com", transport=transport)
    catalog = GammaHttpCatalog(
        base_url="https://example.com",
        timeout_sec=1,
        page_size=2,
        use_events_endpoint=True,
        related_tags=False,
        request_interval_ms=0,
    )
    catalog._client = client

    tags = await catalog.list_tags()
    await client.aclose()

    assert [tag.tag_id for tag in tags] == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_list_markets_events_endpoint_uses_event_title() -> None:
    seen_params = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/events":
            return httpx.Response(404)
        seen_params.update(request.url.params)
        payload = {
            "data": [
                {
                    "title": "Event Title",
                    "markets": [
                        {"conditionId": "m1", "question": "", "active": True, "closed": False},
                        {"conditionId": "m2", "active": False, "closed": False},
                    ],
                }
            ]
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(base_url="https://example.com", transport=transport)
    catalog = GammaHttpCatalog(
        base_url="https://example.com",
        timeout_sec=1,
        page_size=200,
        use_events_endpoint=True,
        related_tags=True,
        request_interval_ms=0,
    )
    catalog._client = client

    markets = await catalog.list_markets(tag_id="tag-1", active=True, closed=False)
    await client.aclose()

    assert seen_params.get("related_tags") == "true"
    assert [market.market_id for market in markets] == ["m1"]
    assert markets[0].question == "Event Title"
