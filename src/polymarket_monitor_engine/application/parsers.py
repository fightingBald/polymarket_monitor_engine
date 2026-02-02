from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from polymarket_monitor_engine.domain.models import BookLevel, BookSnapshot, TradeTick


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


def parse_trade(payload: dict[str, Any]) -> TradeTick | None:
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


def parse_book(payload: dict[str, Any]) -> BookSnapshot | None:
    token_id = _get_token_id(payload)
    if token_id is None:
        return None
    bids = _parse_levels(payload.get("bids") or payload.get("bid") or payload.get("buys"))
    asks = _parse_levels(payload.get("asks") or payload.get("ask") or payload.get("sells"))
    ts_ms = _parse_ts_ms(payload.get("ts_ms") or payload.get("timestamp") or payload.get("ts"))
    if ts_ms is None:
        ts_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    return BookSnapshot(token_id=token_id, bids=bids, asks=asks, ts_ms=ts_ms, raw=payload)
