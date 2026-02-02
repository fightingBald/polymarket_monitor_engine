from __future__ import annotations

import asyncio
import json

import pytest
import websockets

from polymarket_monitor_engine.adapters.clob_ws import ClobWebSocketFeed


@pytest.mark.asyncio
async def test_clob_ws_subscribe_and_receive_trade() -> None:
    received = {}

    async def handler(websocket):
        raw = await websocket.recv()
        received["sub"] = json.loads(raw)

        await websocket.send("ping")
        await websocket.send(
            json.dumps(
                {
                    "event_type": "trade",
                    "asset_id": "token-1",
                    "price": 1.25,
                    "size": 10,
                    "ts_ms": 123,
                }
            )
        )

        # Drain client messages (pong/ping) briefly.
        for _ in range(2):
            try:
                await asyncio.wait_for(websocket.recv(), timeout=0.2)
            except TimeoutError:
                break
            except websockets.ConnectionClosed:
                break
        await websocket.close()

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    feed = ClobWebSocketFeed(
        ws_url=f"ws://127.0.0.1:{port}/ws/market",
        channel="market",
        custom_feature_enabled=True,
        initial_dump=True,
        ping_interval_sec=1,
        ping_message="PING",
        pong_message="pong",
        reconnect_backoff_sec=1,
        reconnect_max_sec=2,
    )
    await feed.subscribe(["token-1"])

    async def _next_message():
        async for message in feed.messages():
            await feed.close()
            return message
        return None

    message = await asyncio.wait_for(_next_message(), timeout=5)

    server.close()
    await server.wait_closed()

    assert message is not None
    assert message.kind == "trade"
    assert message.payload["asset_id"] == "token-1"
    assert received["sub"]["assets_ids"] == ["token-1"]
    assert received["sub"]["type"] == "market"
