from __future__ import annotations

import asyncio
import os
import random
from datetime import UTC, datetime

import httpx
import structlog

from polymarket_monitor_engine.domain.events import DomainEvent, EventType

logger = structlog.get_logger(__name__)


class DiscordWebhookSink:
    def __init__(self, max_retries: int, timeout_sec: float) -> None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        self._webhook_url = webhook_url
        self._max_retries = max(0, int(max_retries))
        self._client: httpx.AsyncClient | None = None
        self._enabled = bool(webhook_url)
        if self._enabled:
            self._client = httpx.AsyncClient(timeout=timeout_sec)
        else:
            logger.warning("discord_webhook_missing")

    async def publish(self, event: DomainEvent) -> None:
        if not self._enabled or self._client is None:
            return
        payload = {"content": self._format_message(event)}
        attempt = 0
        while True:
            try:
                resp = await self._client.post(self._webhook_url, json=payload)
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    logger.warning("discord_post_failed", error_type=type(exc).__name__)
                    raise RuntimeError("Discord webhook request failed") from exc
                await asyncio.sleep(_backoff_delay(attempt))
                attempt += 1
                continue

            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                if attempt >= self._max_retries:
                    logger.warning("discord_post_failed", status=resp.status_code)
                    raise RuntimeError(f"Discord webhook HTTP {resp.status_code}")
                delay = _retry_after(resp) or _backoff_delay(attempt)
                await asyncio.sleep(delay)
                attempt += 1
                continue

            if 200 <= resp.status_code < 300:
                return

            logger.warning("discord_post_failed", status=resp.status_code)
            raise RuntimeError(f"Discord webhook HTTP {resp.status_code}")

    @staticmethod
    def _format_message(event: DomainEvent) -> str:
        ts = datetime.fromtimestamp(event.ts_ms / 1000, tz=UTC)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
        market = event.title or event.topic_key or "(unknown market)"
        market_id = event.market_id or "n/a"
        header = "Polymarket Alert"

        if event.event_type == EventType.HEALTH_EVENT:
            status = event.metrics.get("status", "unknown")
            duration = event.metrics.get("duration_ms")
            detail = f"status={status}"
            if duration is not None:
                detail += f", duration_ms={duration}"
            body = f"🩺 Health | {detail}"
        else:
            signal = event.metrics.get("signal", "signal")
            if signal == "major_change":
                pct = event.metrics.get("pct_change")
                price = event.metrics.get("price")
                prev_price = event.metrics.get("prev_price")
                window = event.metrics.get("window_sec")
                source = event.metrics.get("source")
                body = (
                    "🚨 Major Change\n"
                    f"Market: {market} ({_short_id(market_id)})\n"
                    f"Change: {_fmt_pct(pct)} within {window}s (src={source})\n"
                    f"Price: {_fmt_float(prev_price)} → {_fmt_float(price)}"
                )
            elif signal == "big_trade":
                notional = event.metrics.get("notional")
                price = event.metrics.get("price")
                size = event.metrics.get("size")
                body = (
                    "💥 Big Trade\n"
                    f"Market: {market} ({_short_id(market_id)})\n"
                    f"Price: {_fmt_float(price)} | Size: {_fmt_float(size)}\n"
                    f"Notional: {_fmt_money(notional)}"
                )
            elif signal == "volume_spike_1m":
                vol = event.metrics.get("vol_1m")
                body = (
                    "📈 Volume Spike (1m)\n"
                    f"Market: {market} ({_short_id(market_id)})\n"
                    f"Volume: {_fmt_money(vol)}"
                )
            else:
                body = f"🔔 {signal}\nMarket: {market} ({_short_id(market_id)})"

        message = f"**{header}**\n{body}\nTime: {ts_str}"
        return message[:2000]


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        data = resp.json()
        retry_after = data.get("retry_after")
        if retry_after is not None:
            return float(retry_after)
    except (ValueError, TypeError):
        pass

    header_value = resp.headers.get("Retry-After")
    if header_value:
        try:
            return float(header_value)
        except ValueError:
            return None
    return None


def _backoff_delay(attempt: int) -> float:
    base = 0.5
    delay = base * (2**attempt)
    jitter = random.random() * 0.25
    return min(delay + jitter, 30.0)


def _short_id(value: str) -> str:
    if value == "n/a":
        return value
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _fmt_float(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.4f}".rstrip("0").rstrip(".")


def _fmt_pct(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}%"


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"${float(value):,.2f}"
