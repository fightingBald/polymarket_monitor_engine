from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot, TradeTick


class FeedKind(StrEnum):
    TRADE = "trade"
    BOOK = "book"
    PRICE_CHANGE = "price_change"
    MARKET_LIFECYCLE = "market_lifecycle"
    BEST_BID_ASK = "best_bid_ask"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class TradeMessage:
    kind: FeedKind
    trade: TradeTick
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class BookMessage:
    kind: FeedKind
    book: BookSnapshot
    seq: int | None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class PriceLevelChange:
    side: str
    price: float
    size: float


@dataclass(slots=True)
class PriceChangeMessage:
    kind: FeedKind
    token_id: str
    changes: list[PriceLevelChange]
    seq: int | None
    ts_ms: int | None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class MarketLifecycleMessage:
    kind: FeedKind
    status: str
    market_id: str | None
    token_id: str | None
    title: str | None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class BestBidAskMessage:
    kind: FeedKind
    token_id: str | None
    best_bid: float | None
    best_ask: float | None
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class UnknownMessage:
    kind: FeedKind
    raw: dict[str, Any]


FeedMessage = (
    TradeMessage
    | BookMessage
    | PriceChangeMessage
    | MarketLifecycleMessage
    | BestBidAskMessage
    | UnknownMessage
)


class FeedPort(Protocol):
    async def connect(self) -> None: ...

    async def subscribe(self, token_ids: list[str]) -> None: ...

    async def resubscribe(self, token_ids: list[str]) -> None: ...

    async def messages(self) -> AsyncIterator[FeedMessage]: ...

    async def close(self) -> None: ...


def normalize_message(kind: str, payload: dict[str, Any]) -> FeedMessage | None:
    normalized_kind = FeedKind(kind) if kind in FeedKind._value2member_map_ else FeedKind.UNKNOWN
    if normalized_kind == FeedKind.TRADE:
        trade = parse_trade_payload(payload)
        if trade is None:
            return None
        return TradeMessage(kind=normalized_kind, trade=trade, raw=payload)
    if normalized_kind == FeedKind.BOOK:
        book, seq = parse_book_payload(payload)
        if book is None:
            return None
        return BookMessage(kind=normalized_kind, book=book, seq=seq, raw=payload)
    if normalized_kind == FeedKind.PRICE_CHANGE:
        change = parse_price_change_payload(payload)
        if change is None:
            return None
        return change
    if normalized_kind == FeedKind.MARKET_LIFECYCLE:
        lifecycle = parse_market_lifecycle_payload(payload)
        if lifecycle is None:
            return None
        return lifecycle
    if normalized_kind == FeedKind.BEST_BID_ASK:
        token_id = _get_token_id(payload)
        best_bid = _to_float(payload.get("best_bid") or payload.get("bid"))
        best_ask = _to_float(payload.get("best_ask") or payload.get("ask"))
        return BestBidAskMessage(
            kind=normalized_kind,
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            raw=payload,
        )
    return UnknownMessage(kind=normalized_kind, raw=payload)


def parse_trade_payload(payload: dict[str, Any]) -> TradeTick | None:
    token_id = _get_token_id(payload)
    price = _to_float(
        payload.get("price")
        or payload.get("p")
        or payload.get("last_trade_price")
        or payload.get("trade_price")
    )
    size = _to_float(
        payload.get("size")
        or payload.get("quantity")
        or payload.get("qty")
        or payload.get("last_trade_size")
        or payload.get("trade_size")
    )
    ts_ms = _parse_ts_ms(payload.get("ts_ms") or payload.get("timestamp") or payload.get("ts"))
    if token_id is None or price is None or size is None or ts_ms is None:
        return None
    return TradeTick(
        token_id=token_id,
        price=price,
        size=size,
        ts_ms=ts_ms,
        side=payload.get("side"),
        market_id=payload.get("market_id") or payload.get("marketId"),
        raw=payload,
    )


def parse_book_payload(payload: dict[str, Any]) -> tuple[BookSnapshot | None, int | None]:
    token_id = _get_token_id(payload)
    if token_id is None:
        return None, None
    bids = _parse_levels(payload.get("bids") or payload.get("bid") or payload.get("buys"))
    asks = _parse_levels(payload.get("asks") or payload.get("ask") or payload.get("sells"))
    ts_ms = _parse_ts_ms(payload.get("ts_ms") or payload.get("timestamp") or payload.get("ts"))
    if ts_ms is None:
        ts_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    snapshot = BookSnapshot(token_id=token_id, bids=bids, asks=asks, ts_ms=ts_ms, raw=payload)
    seq = _extract_sequence(payload)
    return snapshot, seq


def parse_price_change_payload(payload: dict[str, Any]) -> PriceChangeMessage | None:
    token_id = _get_token_id(payload)
    if token_id is None:
        return None
    changes = _parse_price_changes(payload)
    if not changes:
        return None
    return PriceChangeMessage(
        kind=FeedKind.PRICE_CHANGE,
        token_id=token_id,
        changes=changes,
        seq=_extract_sequence(payload),
        ts_ms=_extract_ts_ms(payload),
        raw=payload,
    )


def parse_market_lifecycle_payload(payload: dict[str, Any]) -> MarketLifecycleMessage | None:
    event_type = str(payload.get("event_type") or payload.get("type") or "").lower()
    if not event_type:
        return None
    status = "new" if event_type == "new_market" else "resolved"
    market_id = (
        str(
            payload.get("market")
            or payload.get("conditionId")
            or payload.get("condition_id")
            or payload.get("market_id")
            or payload.get("marketId")
            or ""
        )
        or None
    )
    token_id = payload.get("asset_id") or payload.get("assetId") or payload.get("token_id")
    if token_id is None:
        assets_ids = payload.get("assets_ids") or payload.get("asset_ids")
        if isinstance(assets_ids, list) and assets_ids:
            token_id = assets_ids[0]
    token_id = str(token_id) if token_id else None
    title = payload.get("question") or payload.get("title")
    return MarketLifecycleMessage(
        kind=FeedKind.MARKET_LIFECYCLE,
        status=status,
        market_id=market_id,
        token_id=token_id,
        title=str(title) if title else None,
        raw=payload,
    )


def _get_token_id(payload: dict[str, Any]) -> str | None:
    for key in ("asset_id", "assetId", "token_id", "tokenId", "clobTokenId"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_ts_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        num = int(value)
        if num < 10_000_000_000:  # seconds
            return num * 1000
        return num
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return int(dt.astimezone(UTC).timestamp() * 1000)
            except ValueError:
                return None
    return None


def _parse_levels(raw_levels: Any) -> list[BookLevel]:
    levels: list[BookLevel] = []
    if not isinstance(raw_levels, list):
        return levels
    for level in raw_levels:
        if isinstance(level, list) and len(level) >= 2:
            price = _to_float(level[0])
            size = _to_float(level[1])
        elif isinstance(level, dict):
            price = _to_float(level.get("price"))
            size = _to_float(level.get("size") or level.get("qty"))
        else:
            price = None
            size = None
        if price is None or size is None:
            continue
        levels.append(BookLevel(price=price, size=size))
    return levels


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


def _extract_ts_ms(payload: dict[str, Any]) -> int | None:
    value = payload.get("ts_ms") or payload.get("timestamp") or payload.get("ts")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_price_changes(payload: dict[str, Any]) -> list[PriceLevelChange]:
    raw_changes = payload.get("price_changes") or payload.get("changes") or []
    if not isinstance(raw_changes, list):
        return []

    parsed: list[PriceLevelChange] = []
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
        parsed.append(PriceLevelChange(side=side, price=price, size=size))

    return parsed


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
