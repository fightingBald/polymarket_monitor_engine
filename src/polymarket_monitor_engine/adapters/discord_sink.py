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
        payload = self._build_payload(event)
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
    def _build_payload(event: DomainEvent) -> dict:
        embed = _build_embed(event)
        return {"embeds": [embed]} if embed else {"content": _fallback_text(event)}


def _build_embed(event: DomainEvent) -> dict | None:
    ts = datetime.fromtimestamp(event.ts_ms / 1000, tz=UTC)
    market = event.title or event.topic_key or "(unknown market)"
    market_id = event.market_id or "n/a"
    side = event.side
    category = event.category or "n/a"

    if event.event_type == EventType.HEALTH_EVENT:
        status = event.metrics.get("status", "unknown")
        duration = event.metrics.get("duration_ms")
        color = 0x2ECC71 if status == "refresh_ok" else 0xE74C3C
        fields = [{"name": "状态", "value": str(status), "inline": True}]
        if duration is not None:
            fields.append({"name": "耗时(ms)", "value": str(duration), "inline": True})
        return {
            "title": "🩺 健康检查",
            "color": color,
            "fields": fields,
            "timestamp": ts.isoformat(),
        }

    signal = event.metrics.get("signal", "signal")
    if signal == "major_change":
        pct = event.metrics.get("pct_change")
        price = event.metrics.get("price")
        prev_price = event.metrics.get("prev_price")
        window = event.metrics.get("window_sec")
        source = event.metrics.get("source")
        summary = _summary_major_change(market, pct, window, side, source)
        fields = [
            {"name": "摘要", "value": summary, "inline": False},
            {
                "name": "价格",
                "value": f"{_fmt_price(prev_price)} → {_fmt_price(price)}",
                "inline": True,
            },
            {"name": "窗口", "value": f"{window}s", "inline": True},
            {"name": "来源", "value": str(source), "inline": True},
            {"name": "方向", "value": _fmt_side(side), "inline": True},
            {"name": "分类", "value": category, "inline": True},
        ]
        if market_id != "n/a":
            fields.append({"name": "市场ID", "value": market_id, "inline": False})
        return {
            "title": "🚨 重大变动",
            "color": _color_for_side(side) or 0xE74C3C,
            "description": market,
            "fields": fields,
            "url": _market_url(market_id, market),
            "timestamp": ts.isoformat(),
        }

    if signal == "big_trade":
        notional = event.metrics.get("notional")
        price = event.metrics.get("price")
        size = event.metrics.get("size")
        summary = _summary_big_trade(market, notional, side)
        fields = [
            {"name": "摘要", "value": summary, "inline": False},
            {"name": "价格", "value": _fmt_price(price), "inline": True},
            {"name": "数量", "value": _fmt_float(size), "inline": True},
            {"name": "成交额", "value": _fmt_money(notional), "inline": True},
            {"name": "方向", "value": _fmt_side(side), "inline": True},
            {"name": "分类", "value": category, "inline": True},
        ]
        if market_id != "n/a":
            fields.append({"name": "市场ID", "value": market_id, "inline": False})
        return {
            "title": "💥 大单成交",
            "color": _color_for_side(side) or 0xF39C12,
            "description": market,
            "fields": fields,
            "url": _market_url(market_id, market),
            "timestamp": ts.isoformat(),
        }

    if signal == "volume_spike_1m":
        vol = event.metrics.get("vol_1m")
        summary = _summary_volume_spike(market, vol)
        fields = [
            {"name": "摘要", "value": summary, "inline": False},
            {"name": "成交额", "value": _fmt_money(vol), "inline": True},
            {"name": "分类", "value": category, "inline": True},
        ]
        if market_id != "n/a":
            fields.append({"name": "市场ID", "value": market_id, "inline": False})
        return {
            "title": "📈 放量（1分钟）",
            "color": 0xF1C40F,
            "description": market,
            "fields": fields,
            "url": _market_url(market_id, market),
            "timestamp": ts.isoformat(),
        }

    if signal == "web_volume_spike":
        delta = event.metrics.get("delta_volume")
        window = event.metrics.get("window_sec")
        total = event.metrics.get("volume_24h")
        summary = _summary_web_volume(market, delta, window)
        fields = [
            {"name": "摘要", "value": summary, "inline": False},
            {"name": "区间成交", "value": _fmt_money(delta), "inline": True},
            {"name": "24h 成交", "value": _fmt_money(total), "inline": True},
            {"name": "窗口", "value": f"{window}s", "inline": True},
            {"name": "分类", "value": category, "inline": True},
        ]
        if market_id != "n/a":
            fields.append({"name": "市场ID", "value": market_id, "inline": False})
        return {
            "title": "🧊 灰盘放量（无 orderbook）",
            "color": 0x1ABC9C,
            "description": market,
            "fields": fields,
            "url": _market_url(market_id, market),
            "timestamp": ts.isoformat(),
        }

    summary = f"{market} | {signal}"
    fields = [
        {"name": "摘要", "value": summary, "inline": False},
        {"name": "分类", "value": category, "inline": True},
    ]
    if market_id != "n/a":
        fields.append({"name": "市场ID", "value": market_id, "inline": False})
    return {
        "title": f"🔔 {signal}",
        "color": 0x3498DB,
        "description": market,
        "fields": fields,
        "url": _market_url(market_id, market),
        "timestamp": ts.isoformat(),
    }


def _fallback_text(event: DomainEvent) -> str:
    ts = datetime.fromtimestamp(event.ts_ms / 1000, tz=UTC)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
    market = event.title or event.topic_key or "(unknown market)"
    market_id = event.market_id or "n/a"
    signal = event.metrics.get("signal", event.event_type.value)
    message = f"Polymarket Alert | {signal} | {market} | {market_id} | {ts_str}"
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


def _fmt_price(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}¢"


def _fmt_side(value: str | None) -> str:
    return value or "未知"


def _color_for_side(value: str | None) -> int | None:
    if value is None:
        return None
    side = value.upper()
    if side == "YES":
        return 0x2ECC71
    if side == "NO":
        return 0xE74C3C
    return None


def _market_url(market_id: str, market: str) -> str | None:
    if market_id == "n/a":
        return None
    slug = _slugify(market)
    if not slug:
        return None
    return f"https://polymarket.com/market/{slug}"


def _slugify(text: str) -> str:
    lower = text.lower()
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() or ch == "-" else " " for ch in lower)
    parts = [part for part in cleaned.split() if part]
    return "-".join(parts)


def _summary_major_change(
    market: str,
    pct: float | int | None,
    window: int | None,
    side: str | None,
    source: str | None,
) -> str:
    window_text = f"{window}s" if window is not None else "n/a"
    return (
        f"{market} | 变动 {_fmt_pct(pct)} / {window_text} | "
        f"方向：{_fmt_side(side)} | 来源：{source}"
    )


def _summary_big_trade(market: str, notional: float | int | None, side: str | None) -> str:
    return f"{market} | 大单 {_fmt_money(notional)} | 方向：{_fmt_side(side)}"


def _summary_volume_spike(market: str, vol: float | int | None) -> str:
    return f"{market} | 1分钟放量 {_fmt_money(vol)}"


def _summary_web_volume(market: str, delta: float | int | None, window: int | None) -> str:
    window_text = f"{window}s" if window is not None else "n/a"
    return f"{market} | 灰盘放量 {_fmt_money(delta)} / {window_text}"
