from __future__ import annotations

import asyncio
import json

import pytest
from websockets.protocol import State

from polymarket_monitor_engine.adapters.clob_ws import ClobWebSocketFeed


def _maybe_json(raw: str | bytes) -> dict | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class FakeWebSocket:
    def __init__(self, incoming: list[str | bytes] | None = None) -> None:
        self._incoming = incoming or []
        self.sent: list[str | bytes] = []
        self.state = State.OPEN

    def __aiter__(self):
        async def _iter():
            for item in self._incoming:
                yield item

        return _iter()

    async def send(self, data: str | bytes) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.state = State.CLOSED


@pytest.mark.asyncio
async def test_clob_ws_subscribe_and_receive_trade() -> None:
    trade_payload = json.dumps(
        {
            "event_type": "trade",
            "asset_id": "token-1",
            "price": 1.25,
            "size": 10,
            "ts_ms": 123,
        }
    )
    fake_ws = FakeWebSocket(incoming=["ping", trade_payload])

    feed = ClobWebSocketFeed(
        ws_url="ws://example/ws/market",
        channel="market",
        custom_feature_enabled=True,
        initial_dump=True,
        ping_interval_sec=None,
        ping_message="PING",
        pong_message="pong",
        reconnect_backoff_sec=1,
        reconnect_max_sec=2,
    )
    await feed.subscribe(["token-1"])
    feed._ws = fake_ws

    async def _next_message():
        async for message in feed.messages():
            await feed.close()
            return message
        return None

    message = await asyncio.wait_for(_next_message(), timeout=5)

    assert message is not None
    assert message.kind == "trade"
    assert message.payload["asset_id"] == "token-1"

    subscribe_payloads = []
    for raw in fake_ws.sent:
        parsed = _maybe_json(raw)
        if isinstance(parsed, dict) and "assets_ids" in parsed:
            subscribe_payloads.append(parsed)
    assert subscribe_payloads
    assert subscribe_payloads[0]["assets_ids"] == ["token-1"]
    assert subscribe_payloads[0]["type"] == "market"


@pytest.mark.asyncio
async def test_clob_ws_subscribe_chunks_payload() -> None:
    max_frame_bytes = 200
    token_ids = [f"token-{idx:03d}" for idx in range(60)]
    fake_ws = FakeWebSocket()

    feed = ClobWebSocketFeed(
        ws_url="ws://example/ws/market",
        channel="market",
        custom_feature_enabled=True,
        initial_dump=True,
        ping_interval_sec=None,
        ping_message="PING",
        pong_message="pong",
        reconnect_backoff_sec=1,
        reconnect_max_sec=2,
        max_frame_bytes=max_frame_bytes,
    )
    feed._ws = fake_ws
    await feed.subscribe(token_ids)

    assert len(fake_ws.sent) > 1
    payloads = []
    for raw in fake_ws.sent:
        parsed = _maybe_json(raw)
        if parsed is not None:
            payloads.append(parsed)
    combined = [asset for payload in payloads for asset in payload["assets_ids"]]
    assert sorted(combined) == sorted(token_ids)
    assert all(payload["type"] == "market" for payload in payloads)

    for raw in fake_ws.sent:
        raw_bytes = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        assert len(raw_bytes) <= max_frame_bytes
