from __future__ import annotations

from polymarket_monitor_engine.adapters.discord_sink import DiscordWebhookSink
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
    message = DiscordWebhookSink._format_message(event)
    assert "Major Change" in message
    assert "Market:" in message
    assert "Test Market" in message
