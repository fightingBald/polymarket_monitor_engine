from __future__ import annotations

from polymarket_monitor_engine.application.orderbook import OrderBookRegistry
from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot


def test_orderbook_snapshot_and_price_change() -> None:
    registry = OrderBookRegistry()
    snapshot = BookSnapshot(
        token_id="t1",
        bids=[BookLevel(price=1.0, size=10.0)],
        asks=[BookLevel(price=1.1, size=5.0)],
        ts_ms=1000,
    )
    result = registry.apply_snapshot(snapshot, {"sequence": 1})
    assert result.snapshot is snapshot

    payload = {
        "asset_id": "t1",
        "price_changes": [
            {"price": 1.0, "size": 0.0, "side": "BUY"},
            {"price": 1.2, "size": 7.0, "side": "SELL"},
        ],
        "sequence": 2,
        "ts_ms": 2000,
    }
    update = registry.apply_price_change(payload)
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
    registry.apply_snapshot(snapshot, {"seq": 1})

    payload = {
        "asset_id": "t1",
        "changes": [{"price": 1.0, "size": 5.0, "side": "BUY"}],
        "seq": 3,
    }
    result = registry.apply_price_change(payload)
    assert result.resync_needed is True
    assert result.expected_seq == 2
    assert result.received_seq == 3
