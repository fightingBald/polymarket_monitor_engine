from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

import orjson
import structlog
import websockets
from websockets.protocol import State

from polymarket_monitor_engine.ports.feed import FeedMessage

logger = structlog.get_logger(__name__)


class ClobWebSocketFeed:
    def __init__(
        self,
        ws_url: str,
        channel: str,
        custom_feature_enabled: bool,
        initial_dump: bool,
        ping_interval_sec: int | None,
        ping_message: str,
        pong_message: str,
        reconnect_backoff_sec: int,
        reconnect_max_sec: int,
    ) -> None:
        self._ws_url = ws_url
        self._channel = channel
        self._custom_feature_enabled = custom_feature_enabled
        self._initial_dump = initial_dump
        self._ping_interval_sec = ping_interval_sec
        self._ping_message = ping_message
        self._pong_message = pong_message
        self._reconnect_backoff_sec = reconnect_backoff_sec
        self._reconnect_max_sec = reconnect_max_sec
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._stop = asyncio.Event()
        self._desired_ids: set[str] = set()
        self._subscribed_ids: set[str] = set()
        self._ping_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        if self._is_closed():
            self._ws = await websockets.connect(self._resolve_ws_url(), ping_interval=None)
            self._subscribed_ids.clear()
            logger.info("clob_connected", ws_url=self._resolve_ws_url())

    async def subscribe(self, token_ids: list[str]) -> None:
        self._desired_ids = set(token_ids)
        if self._is_closed():
            return
        await self._apply_subscription_changes()

    async def resubscribe(self, token_ids: list[str]) -> None:
        self._desired_ids = set(token_ids)
        if self._is_closed():
            return
        await self._send_initial_subscription(sorted(self._desired_ids))
        self._subscribed_ids = set(self._desired_ids)

    async def messages(self) -> AsyncIterator[FeedMessage]:
        backoff = self._reconnect_backoff_sec
        while not self._stop.is_set():
            try:
                if not self._desired_ids:
                    await asyncio.sleep(0.5)
                    continue
                await self.connect()
                await self._ensure_subscription()
                self._start_ping_task()

                assert self._ws is not None
                async for raw in self._ws:
                    if self._handle_ping(raw):
                        continue
                    try:
                        payload = self._decode(raw)
                    except json.JSONDecodeError:
                        logger.warning("clob_decode_failed")
                        continue
                    if isinstance(payload, list):
                        for item in payload:
                            if not isinstance(item, dict):
                                continue
                            if self._handle_ping_payload(item):
                                continue
                            kind = self._detect_kind(item)
                            yield FeedMessage(kind=kind, payload=item)
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if self._handle_ping_payload(payload):
                        continue
                    kind = self._detect_kind(payload)
                    yield FeedMessage(kind=kind, payload=payload)

                backoff = self._reconnect_backoff_sec
            except Exception as exc:  # noqa: BLE001
                logger.warning("clob_reconnect", error=str(exc))
                await self._stop_ping_task()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._reconnect_max_sec)

    async def close(self) -> None:
        self._stop.set()
        await self._stop_ping_task()
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _ensure_subscription(self) -> None:
        if not self._desired_ids:
            return
        await self._apply_subscription_changes(initial=True)

    async def _apply_subscription_changes(self, initial: bool = False) -> None:
        if self._is_closed():
            return

        if initial or not self._subscribed_ids:
            await self._send_initial_subscription(sorted(self._desired_ids))
            self._subscribed_ids = set(self._desired_ids)
            return

        to_add = sorted(self._desired_ids - self._subscribed_ids)
        to_remove = sorted(self._subscribed_ids - self._desired_ids)

        if to_add:
            await self._send_operation("subscribe", to_add)
            self._subscribed_ids.update(to_add)
        if to_remove:
            await self._send_operation("unsubscribe", to_remove)
            self._subscribed_ids.difference_update(to_remove)

    async def _send_initial_subscription(self, token_ids: list[str]) -> None:
        if not token_ids:
            return
        payload = {
            "type": self._channel,
            "assets_ids": token_ids,
            "custom_feature_enabled": self._custom_feature_enabled,
            "initial_dump": self._initial_dump,
        }
        await self._send(payload)
        logger.info("clob_subscribe", count=len(token_ids))

    async def _send_operation(self, operation: str, token_ids: list[str]) -> None:
        if not token_ids:
            return
        payload = {
            "assets_ids": token_ids,
            "operation": operation,
            "custom_feature_enabled": self._custom_feature_enabled,
        }
        await self._send(payload)
        logger.info("clob_operation", operation=operation, count=len(token_ids))

    async def _send(self, payload: dict) -> None:
        if self._ws is None:
            return
        await self._ws.send(orjson.dumps(payload))

    def _start_ping_task(self) -> None:
        if self._ping_interval_sec is None or self._ping_task is not None:
            return
        self._ping_task = asyncio.create_task(self._ping_loop())

    async def _stop_ping_task(self) -> None:
        if self._ping_task is None:
            return
        self._ping_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._ping_task
        self._ping_task = None

    async def _ping_loop(self) -> None:
        assert self._ping_interval_sec is not None
        while not self._stop.is_set():
            if self._is_closed():
                await asyncio.sleep(self._ping_interval_sec)
                continue
            await self._ws.send(self._ping_message)
            await asyncio.sleep(self._ping_interval_sec)

    def _handle_ping(self, raw: str | bytes) -> bool:
        text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw
        if text.strip().lower() not in {"ping", "pong"}:
            return False
        if self._is_closed():
            return True
        if text.strip().lower() == "ping":
            asyncio.create_task(self._ws.send(self._pong_message))
        return True

    def _handle_ping_payload(self, payload: dict) -> bool:
        hint = str(payload.get("type") or payload.get("event_type") or "").lower()
        if hint not in {"ping", "pong"}:
            return False
        if self._is_closed():
            return True
        if hint == "ping":
            asyncio.create_task(self._ws.send(self._pong_message))
        return True

    def _is_closed(self) -> bool:
        if self._ws is None:
            return True
        return self._ws.state in {State.CLOSING, State.CLOSED}

    def _resolve_ws_url(self) -> str:
        if "/ws/" in self._ws_url:
            return self._ws_url
        return f"{self._ws_url.rstrip('/')}/ws/{self._channel}"

    @staticmethod
    def _decode(raw: str | bytes) -> dict:
        if isinstance(raw, bytes):
            return orjson.loads(raw)
        try:
            return orjson.loads(raw.encode("utf-8"))
        except orjson.JSONDecodeError:
            return json.loads(raw)

    @staticmethod
    def _detect_kind(payload: dict) -> str:
        hint = str(payload.get("event_type") or payload.get("type") or "").lower()
        if hint in {"last_trade_price", "trade", "last_trade", "fill"}:
            return "trade"
        if hint in {"book", "orderbook"}:
            return "book"
        if hint == "price_change":
            return "price_change"
        if hint == "best_bid_ask":
            return "best_bid_ask"
        if hint in {"new_market", "market_resolved"}:
            return "market_lifecycle"
        if "bids" in payload or "asks" in payload or "buys" in payload or "sells" in payload:
            return "book"
        return "raw"
