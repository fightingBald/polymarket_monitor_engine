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
    def __init__(
        self,
        max_retries: int,
        timeout_sec: float,
        aggregate_multi_outcome: bool = True,
        aggregate_window_sec: float = 2.0,
        aggregate_max_items: int = 5,
    ) -> None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        self._webhook_url = webhook_url
        self._max_retries = max(0, int(max_retries))
        self._aggregate_multi_outcome = aggregate_multi_outcome
        self._aggregate_window_sec = max(0.2, float(aggregate_window_sec))
        self._aggregate_max_items = max(1, int(aggregate_max_items))
        self._pending: dict[tuple[str, str], list[DomainEvent]] = {}
        self._pending_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._client: httpx.AsyncClient | None = None
        self._enabled = bool(webhook_url)
        if self._enabled:
            self._client = httpx.AsyncClient(timeout=timeout_sec)
        else:
            logger.warning("discord_webhook_missing")

    async def publish(self, event: DomainEvent) -> None:
        if not self._enabled or self._client is None:
            return
        if self._should_aggregate(event):
            await self._enqueue(event)
            return
        payload = self._build_payload(event)
        await self._post_payload(payload)

    def _should_aggregate(self, event: DomainEvent) -> bool:
        if not self._aggregate_multi_outcome:
            return False
        if event.event_type != EventType.TRADE_SIGNAL:
            return False
        signal = str(event.metrics.get("signal") or "")
        if signal not in {"major_change", "big_trade", "volume_spike_1m"}:
            return False
        if not event.market_id or not event.side:
            return False
        side = event.side.upper()
        if side in {"YES", "NO"}:
            return False
        return True

    async def _enqueue(self, event: DomainEvent) -> None:
        key = (event.market_id or "n/a", str(event.metrics.get("signal") or "signal"))
        async with self._lock:
            self._pending.setdefault(key, []).append(event)
            if key not in self._pending_tasks:
                self._pending_tasks[key] = asyncio.create_task(self._flush_after(key))

    async def _flush_after(self, key: tuple[str, str]) -> None:
        await asyncio.sleep(self._aggregate_window_sec)
        async with self._lock:
            events = self._pending.pop(key, [])
            self._pending_tasks.pop(key, None)
        if not events:
            return
        payload = self._build_aggregate_payload(events)
        await self._post_payload(payload)

    async def _post_payload(self, payload: dict) -> None:
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

    def _build_aggregate_payload(self, events: list[DomainEvent]) -> dict:
        embed = _build_aggregate_embed(events, max_items=self._aggregate_max_items)
        return {"embeds": [embed]} if embed else {"content": _fallback_text(events[0])}


def _build_embed(event: DomainEvent) -> dict | None:
    ts = datetime.fromtimestamp(event.ts_ms / 1000, tz=UTC)
    market = event.title or event.topic_key or "(unknown market)"
    market_id = event.market_id or "n/a"
    side = event.side
    category = event.category or "n/a"

    if event.event_type == EventType.MONITORING_STATUS:
        metrics = event.metrics
        status = metrics.get("status", "connected")
        market_count = metrics.get("market_count")
        token_count = metrics.get("token_count")
        unsub_count = metrics.get("unsubscribable_count")

        raw = event.raw or {}
        subscribed = raw.get("subscribed_markets") if isinstance(raw, dict) else None
        unsub = raw.get("unsubscribable_markets") if isinstance(raw, dict) else None

        subscribed_lines = _format_market_list(subscribed, limit=12)
        unsub_lines = _format_market_list(unsub, limit=8)

        fields = [
            {"name": "状态", "value": str(status), "inline": True},
            {
                "name": "统计",
                "value": f"markets: {market_count} | tokens: {token_count} | grey: {unsub_count}",
                "inline": True,
            },
            {"name": "监控盘口", "value": subscribed_lines, "inline": False},
            {"name": "灰盘（无 orderbook）", "value": unsub_lines, "inline": False},
        ]
        return {
            "title": "🟢 已连接 | 监控启动",
            "color": 0x2ECC71,
            "fields": fields,
            "timestamp": ts.isoformat(),
        }

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


def _build_aggregate_embed(events: list[DomainEvent], max_items: int) -> dict | None:
    if not events:
        return None
    latest_ts_ms = max(event.ts_ms for event in events)
    ts = datetime.fromtimestamp(latest_ts_ms / 1000, tz=UTC)
    event = events[0]
    market = event.title or event.topic_key or "(unknown market)"
    market_id = event.market_id or "n/a"
    category = event.category or "n/a"
    signal = str(event.metrics.get("signal") or "signal")

    lines = _aggregate_lines(events, signal, max_items)
    summary = f"{market} | {signal} | {len(events)} 个结果触发"
    fields = [
        {"name": "摘要", "value": summary, "inline": False},
        {"name": "明细", "value": "\n".join(lines), "inline": False},
        {"name": "分类", "value": category, "inline": True},
    ]
    window = event.metrics.get("window_sec")
    source = event.metrics.get("source")
    if window is not None:
        fields.append({"name": "窗口", "value": f"{window}s", "inline": True})
    if source is not None:
        fields.append({"name": "来源", "value": str(source), "inline": True})
    if market_id != "n/a":
        fields.append({"name": "市场ID", "value": market_id, "inline": False})

    return {
        "title": _aggregate_title(signal),
        "color": _aggregate_color(events, signal),
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


def _format_market_list(raw: object, limit: int) -> str:
    if not isinstance(raw, list) or not raw:
        return "无"
    lines: list[str] = []
    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "(unknown)")
        category = str(item.get("category") or "n/a")
        lines.append(f"• [{category}] {title}")
    if not lines:
        return "无"
    if isinstance(raw, list) and len(raw) > limit:
        lines.append(f"... 还有 {len(raw) - limit} 个")
    return "\n".join(lines)


def _aggregate_lines(events: list[DomainEvent], signal: str, max_items: int) -> list[str]:
    def sort_key(event: DomainEvent) -> float:
        metrics = event.metrics
        if signal == "major_change":
            value = metrics.get("pct_change_signed") or metrics.get("pct_change") or 0.0
            return abs(float(value))
        if signal == "big_trade":
            return float(metrics.get("notional") or 0.0)
        if signal == "volume_spike_1m":
            return float(metrics.get("vol_1m") or 0.0)
        return 0.0

    def format_line(event: DomainEvent) -> str:
        name = event.side or "?"
        metrics = event.metrics
        if signal == "major_change":
            pct_signed = float(metrics.get("pct_change_signed") or 0.0)
            arrow = "↑" if pct_signed > 0 else "↓" if pct_signed < 0 else "→"
            price = _fmt_price(metrics.get("price"))
            return f"{name}: {arrow}{abs(pct_signed):.2f}% → {price}"
        if signal == "big_trade":
            notional = _fmt_money(metrics.get("notional"))
            price = _fmt_price(metrics.get("price"))
            return f"{name}: 大单 {notional} @ {price}"
        if signal == "volume_spike_1m":
            vol = _fmt_money(metrics.get("vol_1m"))
            return f"{name}: 1m 放量 {vol}"
        return f"{name}"

    sorted_events = sorted(events, key=sort_key, reverse=True)
    lines = [format_line(event) for event in sorted_events[:max_items]]
    if len(sorted_events) > max_items:
        lines.append(f"... 还有 {len(sorted_events) - max_items} 个结果")
    return lines


def _aggregate_title(signal: str) -> str:
    if signal == "major_change":
        return "📊 多选盘异动汇总"
    if signal == "big_trade":
        return "💥 多选盘大单汇总"
    if signal == "volume_spike_1m":
        return "📈 多选盘放量汇总"
    return "🔔 多选盘预警汇总"


def _aggregate_color(events: list[DomainEvent], signal: str) -> int:
    if signal != "major_change":
        return 0x3498DB
    directions = []
    for event in events:
        value = event.metrics.get("pct_change_signed")
        if value is None:
            continue
        directions.append(float(value))
    if not directions:
        return 0xE67E22
    if all(val > 0 for val in directions):
        return 0x2ECC71
    if all(val < 0 for val in directions):
        return 0xE74C3C
    return 0xE67E22
