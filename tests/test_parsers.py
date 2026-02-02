from __future__ import annotations

from datetime import UTC, datetime

from polymarket_monitor_engine.application.parsers import _parse_ts_ms, parse_book, parse_trade


def test_parse_ts_ms_seconds_and_iso() -> None:
    assert _parse_ts_ms(1_700_000_000) == 1_700_000_000_000

    iso = datetime(2024, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")
    assert _parse_ts_ms(iso) == 1_704_067_200_000


def test_parse_ts_ms_invalid() -> None:
    assert _parse_ts_ms("not-a-ts") is None


def test_parse_trade_happy_path() -> None:
    payload = {"asset_id": "token-1", "price": "1.5", "size": 10, "ts_ms": 123}
    trade = parse_trade(payload)
    assert trade is not None
    assert trade.token_id == "token-1"
    assert trade.price == 1.5
    assert trade.size == 10.0
    assert trade.ts_ms == 123000


def test_parse_trade_missing_fields_returns_none() -> None:
    payload = {"asset_id": "token-1", "price": 1.5, "ts_ms": 123}
    assert parse_trade(payload) is None


def test_parse_book_parses_levels_and_timestamp() -> None:
    payload = {
        "asset_id": "token-1",
        "bids": [["1.0", "2.0"], {"price": 0.9, "size": 1}],
        "asks": [{"price": 1.1, "qty": 3}, [1.2, "4"]],
        "ts": 1_700_000_000,
    }
    book = parse_book(payload)
    assert book is not None
    assert book.token_id == "token-1"
    assert len(book.bids) == 2
    assert len(book.asks) == 2
    assert book.ts_ms == 1_700_000_000_000


def test_parse_book_missing_token_returns_none() -> None:
    assert parse_book({"bids": []}) is None
