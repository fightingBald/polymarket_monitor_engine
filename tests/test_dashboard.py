import pytest

from polymarket_monitor_engine.application.dashboard import TerminalDashboard
from polymarket_monitor_engine.application.types import TokenMeta
from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot, TradeTick


@pytest.mark.asyncio
async def test_dashboard_snapshot_updates() -> None:
    dashboard = TerminalDashboard(refresh_hz=1.0, max_rows=5)
    token_meta = {
        "token-1": TokenMeta(
            token_id="token-1",
            market_id="market-1",
            category="finance",
            title="Test Market",
            side="YES",
            topic_key="test market",
        )
    }
    await dashboard.update_registry(token_meta)

    now_ms = 1_000_000
    trade = TradeTick(
        token_id="token-1",
        market_id="market-1",
        side="YES",
        price=0.25,
        size=100,
        ts_ms=now_ms,
        raw=None,
    )
    await dashboard.update_trade(trade)

    book = BookSnapshot(
        token_id="token-1",
        bids=[BookLevel(price=0.24, size=50)],
        asks=[BookLevel(price=0.26, size=60)],
        ts_ms=now_ms,
        raw=None,
    )
    await dashboard.update_book(book)

    snapshot = await dashboard.snapshot(now_ms=now_ms)
    assert snapshot.token_count == 1
    assert snapshot.market_count == 1

    row = snapshot.rows[0]
    assert row.last_price == pytest.approx(0.25)
    assert row.best_bid == pytest.approx(0.24)
    assert row.best_ask == pytest.approx(0.26)
    assert row.vol_1m == pytest.approx(25.0)
    assert row.last_trade_notional == pytest.approx(25.0)
