from __future__ import annotations

from dataclasses import dataclass

import structlog

from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot
from polymarket_monitor_engine.ports.feed import PriceChangeMessage

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class OrderBookUpdateResult:
    token_id: str | None
    snapshot: BookSnapshot | None
    resync_needed: bool = False
    expected_seq: int | None = None
    received_seq: int | None = None


@dataclass(slots=True)
class OrderBookState:
    token_id: str
    bids: dict[float, float]
    asks: dict[float, float]
    last_seq: int | None = None
    last_ts_ms: int | None = None

    def apply_snapshot(self, snapshot: BookSnapshot, seq: int | None) -> None:
        self.bids = {level.price: level.size for level in snapshot.bids}
        self.asks = {level.price: level.size for level in snapshot.asks}
        self.last_seq = seq if seq is not None else self.last_seq
        self.last_ts_ms = snapshot.ts_ms

    def apply_change(self, side: str, price: float, size: float) -> None:
        book = self.bids if side == "BUY" else self.asks
        if size <= 0:
            book.pop(price, None)
        else:
            book[price] = size

    def to_snapshot(self) -> BookSnapshot:
        bids = [BookLevel(price=price, size=size) for price, size in self.bids.items()]
        asks = [BookLevel(price=price, size=size) for price, size in self.asks.items()]
        bids.sort(key=lambda level: level.price, reverse=True)
        asks.sort(key=lambda level: level.price)
        ts_ms = self.last_ts_ms or 0
        return BookSnapshot(token_id=self.token_id, bids=bids, asks=asks, ts_ms=ts_ms)

    def clear(self) -> None:
        self.bids = {}
        self.asks = {}
        self.last_seq = None


class OrderBookRegistry:
    def __init__(self) -> None:
        self._books: dict[str, OrderBookState] = {}

    def apply_snapshot(
        self,
        snapshot: BookSnapshot,
        seq: int | None,
    ) -> OrderBookUpdateResult:
        token_id = snapshot.token_id
        state = self._books.get(token_id) or OrderBookState(token_id=token_id, bids={}, asks={})

        resync_needed, expected = _sequence_gap(state.last_seq, seq)
        if resync_needed:
            logger.warning(
                "orderbook_seq_gap",
                token_id=token_id,
                expected_seq=expected,
                received_seq=seq,
            )
            state.clear()
            self._books[token_id] = state
            return OrderBookUpdateResult(
                token_id=token_id,
                snapshot=None,
                resync_needed=True,
                expected_seq=expected,
                received_seq=seq,
            )

        state.apply_snapshot(snapshot, seq)
        self._books[token_id] = state
        return OrderBookUpdateResult(token_id=token_id, snapshot=snapshot)

    def apply_price_change(self, message: PriceChangeMessage) -> OrderBookUpdateResult:
        token_id = message.token_id

        state = self._books.get(token_id)
        if state is None:
            logger.debug("orderbook_missing_snapshot", token_id=token_id)
            return OrderBookUpdateResult(token_id=token_id, snapshot=None)

        seq = message.seq
        resync_needed, expected = _sequence_gap(state.last_seq, seq)
        if resync_needed:
            logger.warning(
                "orderbook_seq_gap",
                token_id=token_id,
                expected_seq=expected,
                received_seq=seq,
            )
            state.clear()
            return OrderBookUpdateResult(
                token_id=token_id,
                snapshot=None,
                resync_needed=True,
                expected_seq=expected,
                received_seq=seq,
            )

        for change in message.changes:
            state.apply_change(change.side, change.price, change.size)
        state.last_seq = seq if seq is not None else state.last_seq
        state.last_ts_ms = message.ts_ms or state.last_ts_ms
        snapshot = state.to_snapshot()
        return OrderBookUpdateResult(token_id=token_id, snapshot=snapshot)


def _sequence_gap(last_seq: int | None, next_seq: int | None) -> tuple[bool, int | None]:
    if next_seq is None:
        return False, None
    if last_seq is None:
        return False, None
    expected = last_seq + 1
    if next_seq != expected:
        return True, expected
    return False, expected
