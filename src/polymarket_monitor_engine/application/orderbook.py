from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot

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
        payload: dict[str, Any],
    ) -> OrderBookUpdateResult:
        token_id = snapshot.token_id
        seq = _extract_sequence(payload)
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

    def apply_price_change(self, payload: dict[str, Any]) -> OrderBookUpdateResult:
        token_id = _extract_token_id(payload)
        if token_id is None:
            return OrderBookUpdateResult(token_id=None, snapshot=None)

        state = self._books.get(token_id)
        if state is None:
            logger.debug("orderbook_missing_snapshot", token_id=token_id)
            return OrderBookUpdateResult(token_id=token_id, snapshot=None)

        seq = _extract_sequence(payload)
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

        changes = _parse_price_changes(payload)
        if not changes:
            return OrderBookUpdateResult(token_id=token_id, snapshot=None)

        for side, price, size in changes:
            state.apply_change(side, price, size)
        state.last_seq = seq if seq is not None else state.last_seq
        state.last_ts_ms = _extract_ts_ms(payload) or state.last_ts_ms
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


def _extract_sequence(payload: dict[str, Any]) -> int | None:
    for key in ("sequence", "seq", "sequence_number", "seqNum"):
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _extract_token_id(payload: dict[str, Any]) -> str | None:
    for key in ("asset_id", "assetId", "token_id", "tokenId", "clobTokenId"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return None


def _extract_ts_ms(payload: dict[str, Any]) -> int | None:
    value = payload.get("ts_ms") or payload.get("timestamp") or payload.get("ts")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_price_changes(payload: dict[str, Any]) -> list[tuple[str, float, float]]:
    raw_changes = payload.get("price_changes") or payload.get("changes") or []
    if not isinstance(raw_changes, list):
        return []

    parsed: list[tuple[str, float, float]] = []
    for item in raw_changes:
        if isinstance(item, dict):
            side_raw = item.get("side") or item.get("type")
            side = str(side_raw or "").upper()
            price = _to_float(_coalesce(item.get("price"), item.get("p")))
            size = _to_float(_coalesce(item.get("size"), item.get("s"), item.get("quantity")))
        elif isinstance(item, (list, tuple)) and len(item) >= 3:
            side = str(item[2] or "").upper()
            price = _to_float(item[0])
            size = _to_float(item[1])
        else:
            continue

        if side not in {"BUY", "SELL"}:
            continue
        if price is None or size is None:
            continue
        parsed.append((side, price, size))

    return parsed


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
