from __future__ import annotations

from polymarket_monitor_engine.adapters.discord_sink import _build_aggregate_embed, _build_embed
from polymarket_monitor_engine.domain.events import DomainEvent, EventType


def test_discord_format_major_change() -> None:
    event = DomainEvent(
        event_id="evt-1",
        ts_ms=1_700_000_000_000,
        event_type=EventType.TRADE_SIGNAL,
        market_id="m1",
        title="Test Market",
        metrics={
            "signal": "major_change",
            "pct_change": 12.5,
            "price": 1.2,
            "prev_price": 1.0,
            "window_sec": 60,
            "notional": 0.0,
            "source": "trade",
        },
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
            metrics={
                "signal": "major_change",
                "pct_change": 12.5,
                "pct_change_signed": 12.5,
                "price": 0.88,
                "prev_price": 0.78,
                "window_sec": 60,
                "source": "trade",
            },
        ),
        DomainEvent(
            event_id="evt-2",
            ts_ms=1_700_000_000_100,
            event_type=EventType.TRADE_SIGNAL,
            market_id="m1",
            title="Multi Market",
            side="Judy",
            metrics={
                "signal": "major_change",
                "pct_change": 8.0,
                "pct_change_signed": -8.0,
                "price": 0.12,
                "prev_price": 0.13,
                "window_sec": 60,
                "source": "trade",
            },
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
        metrics={"status": "new", "end_ts": 1_800_000_000_000},
    )
    embed = _build_embed(event)
    assert embed is not None
    assert "新盘口" in embed.get("title", "")
