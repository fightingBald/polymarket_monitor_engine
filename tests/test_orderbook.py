from __future__ import annotations

from polymarket_monitor_engine.application.orderbook import OrderBookRegistry
from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot
from polymarket_monitor_engine.ports.feed import FeedKind, PriceChangeMessage, PriceLevelChange


def test_orderbook_snapshot_and_price_change() -> None:
    registry = OrderBookRegistry()
    snapshot = BookSnapshot(
        token_id="t1",
        bids=[BookLevel(price=1.0, size=10.0)],
        asks=[BookLevel(price=1.1, size=5.0)],
        ts_ms=1000,
    )
    result = registry.apply_snapshot(snapshot, 1)
    assert result.snapshot is snapshot

    change = PriceChangeMessage(
        kind=FeedKind.PRICE_CHANGE,
        token_id="t1",
        changes=[
            PriceLevelChange(side="BUY", price=1.0, size=0.0),
            PriceLevelChange(side="SELL", price=1.2, size=7.0),
        ],
        seq=2,
        ts_ms=2000,
    )
    update = registry.apply_price_change(change)
    assert update.snapshot is not None
    bids = {level.price: level.size for level in update.snapshot.bids}
    asks = {level.price: level.size for level in update.snapshot.asks}
    assert 1.0 not in bids
    assert asks[1.2] == 7.0


def test_orderbook_sequence_gap() -> None:
    registry = OrderBookRegistry()
    snapshot = BookSnapshot(
        token_id="t1",
        bids=[BookLevel(price=1.0, size=10.0)],
        asks=[BookLevel(price=1.1, size=5.0)],
        ts_ms=1000,
    )
    registry.apply_snapshot(snapshot, 1)

    change = PriceChangeMessage(
        kind=FeedKind.PRICE_CHANGE,
        token_id="t1",
        changes=[PriceLevelChange(side="BUY", price=1.0, size=5.0)],
        seq=3,
        ts_ms=None,
    )
    result = registry.apply_price_change(change)
    assert result.resync_needed is True
    assert result.expected_seq == 2
    assert result.received_seq == 3
