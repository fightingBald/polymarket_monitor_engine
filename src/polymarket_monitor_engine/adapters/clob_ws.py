from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import orjson
import structlog
import websockets

from polymarket_monitor_engine.ports.feed import FeedMessage

logger = structlog.get_logger(__name__)


class ClobWebSocketFeed:
    def __init__(
        self,
        ws_url: str,
        channel: str,
        subscribe_action: str,
        unsubscribe_action: str,
        asset_key: str,
        reconnect_backoff_sec: int,
    ) -> None:
        self._ws_url = ws_url
        self._channel = channel
        self._subscribe_action = subscribe_action
        self._unsubscribe_action = unsubscribe_action
        self._asset_key = asset_key
        self._reconnect_backoff_sec = reconnect_backoff_sec
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._token_ids: list[str] = []
        self._stop = asyncio.Event()

    async def connect(self) -> None:
        if self._ws is None or self._ws.closed:
            self._ws = await websockets.connect(self._ws_url)
            logger.info("clob_connected", ws_url=self._ws_url)

    async def subscribe(self, token_ids: list[str]) -> None:
        self._token_ids = token_ids
        if not token_ids:
            return
        await self.connect()
        if self._ws is None:
            return
        payload = {
            "type": self._subscribe_action,
            "channel": self._channel,
            self._asset_key: token_ids,
        }
        await self._ws.send(orjson.dumps(payload))
        logger.info("clob_subscribe", count=len(token_ids))

    async def messages(self) -> AsyncIterator[FeedMessage]:
        while not self._stop.is_set():
            try:
                await self.connect()
                if self._token_ids:
                    await self.subscribe(self._token_ids)

                assert self._ws is not None
                async for raw in self._ws:
                    payload = self._decode(raw)
                    kind = self._detect_kind(payload)
                    yield FeedMessage(kind=kind, payload=payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("clob_reconnect", error=str(exc))
                await asyncio.sleep(self._reconnect_backoff_sec)

    async def close(self) -> None:
        self._stop.set()
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    @staticmethod
    def _decode(raw: str | bytes) -> dict:
        try:
            if isinstance(raw, bytes):
                return orjson.loads(raw)
            return orjson.loads(raw.encode("utf-8"))
        except orjson.JSONDecodeError:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            return json.loads(raw)

    @staticmethod
    def _detect_kind(payload: dict) -> str:
        hint = str(payload.get("type") or payload.get("event_type") or "").lower()
        if hint in {"trade", "last_trade", "fill"}:
            return "trade"
        if hint in {"book", "book_update", "orderbook"}:
            return "book"
        if "bids" in payload or "asks" in payload:
            return "book"
        return "raw"
