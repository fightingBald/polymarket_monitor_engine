from __future__ import annotations

import json

import httpx
import pytest

from polymarket_monitor_engine.adapters.discord_sink import (
    DiscordWebhookSink,
    _build_aggregate_embed,
    _build_embed,
)
from polymarket_monitor_engine.domain.events import DomainEvent, EventType
from polymarket_monitor_engine.domain.schemas.event_payloads import (
    MajorChangePayload,
    MarketLifecyclePayload,
    MonitoringStatusPayload,
    SignalType,
)


def test_discord_format_major_change() -> None:
    event = DomainEvent(
        event_id="evt-1",
        ts_ms=1_700_000_000_000,
        event_type=EventType.TRADE_SIGNAL,
        market_id="m1",
        title="Test Market",
        payload=MajorChangePayload(
            signal=SignalType.MAJOR_CHANGE,
            pct_change=12.5,
            pct_change_signed=12.5,
            direction="up",
            price=1.2,
            prev_price=1.0,
            window_sec=60,
            notional=0.0,
            source="trade",
        ),
    )
    embed = _build_embed(event)
    assert embed is not None
    assert "重大变动" in embed.get("title", "")
    assert "Test Market" in embed.get("description", "")
    assert any(field.get("name") == "摘要" for field in embed.get("fields", []))


def test_discord_format_multi_outcome_aggregate() -> None:
    events = [
        DomainEvent(
            event_id="evt-1",
            ts_ms=1_700_000_000_000,
            event_type=EventType.TRADE_SIGNAL,
            market_id="m1",
            title="Multi Market",
            side="Kevin",
            payload=MajorChangePayload(
                signal=SignalType.MAJOR_CHANGE,
                pct_change=12.5,
                pct_change_signed=12.5,
                direction="up",
                price=0.88,
                prev_price=0.78,
                window_sec=60,
                notional=0.0,
                source="trade",
            ),
        ),
        DomainEvent(
            event_id="evt-2",
            ts_ms=1_700_000_000_100,
            event_type=EventType.TRADE_SIGNAL,
            market_id="m1",
            title="Multi Market",
            side="Judy",
            payload=MajorChangePayload(
                signal=SignalType.MAJOR_CHANGE,
                pct_change=8.0,
                pct_change_signed=-8.0,
                direction="down",
                price=0.12,
                prev_price=0.13,
                window_sec=60,
                notional=0.0,
                source="trade",
            ),
        ),
    ]

    embed = _build_aggregate_embed(events, max_items=5)
    assert embed is not None
    assert "多选盘" in embed.get("title", "")
    fields = embed.get("fields", [])
    detail = next((field for field in fields if field.get("name") == "明细"), None)
    assert detail is not None
    assert "Kevin" in detail.get("value", "")


def test_discord_format_market_lifecycle() -> None:
    event = DomainEvent(
        event_id="evt-3",
        ts_ms=1_700_000_000_000,
        event_type=EventType.MARKET_LIFECYCLE,
        market_id="m9",
        title="Brand New Market",
        category="finance",
        payload=MarketLifecyclePayload(status="new", end_ts=1_800_000_000_000),
    )
    embed = _build_embed(event)
    assert embed is None


def test_discord_format_monitoring_status_category_counts() -> None:
    event = DomainEvent(
        event_id="evt-4",
        ts_ms=1_700_000_000_000,
        event_type=EventType.MONITORING_STATUS,
        payload=MonitoringStatusPayload(
            status="connected",
            market_count=3,
            token_count=6,
            unsubscribable_count=1,
        ),
        raw={
            "subscribed_markets": [
                {"market_id": "m1", "event_id": "e1", "title": "A", "category": "finance"},
                {"market_id": "m2", "event_id": "e1", "title": "B", "category": "finance"},
                {"market_id": "m3", "event_id": "e2", "title": "C", "category": "geopolitics"},
            ],
            "unsubscribable_markets": [],
        },
    )
    embed = _build_embed(event)
    assert embed is not None
    fields = embed.get("fields", [])
    counts = next((field for field in fields if field.get("name") == "分类统计"), None)
    assert counts is not None
    assert "finance: 1" in counts.get("value", "")


@pytest.mark.asyncio
async def test_discord_sink_logs_payload_to_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.com/webhook")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    log_path = tmp_path / "discord.out.jsonl"
    sink = DiscordWebhookSink(
        max_retries=0,
        timeout_sec=1,
        aggregate_multi_outcome=False,
        aggregate_window_sec=0.2,
        aggregate_max_items=5,
        log_payloads=True,
        log_payloads_path=str(log_path),
    )
    sink._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    event = DomainEvent(
        event_id="evt-log",
        ts_ms=1_700_000_000_000,
        event_type=EventType.TRADE_SIGNAL,
        market_id="m1",
        title="Big Move",
        category="finance",
        side="YES",
        payload=MajorChangePayload(
            signal=SignalType.MAJOR_CHANGE,
            pct_change=12.0,
            pct_change_signed=12.0,
            direction="up",
            price=0.42,
            prev_price=0.38,
            window_sec=60,
            notional=1200.0,
            source="trade",
        ),
    )

    await sink.publish(event)
    await sink._client.aclose()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert payload.get("event") == "🧷 discord_outgoing"
    assert "payload" in payload
    assert payload["payload"].get("embeds")
