from __future__ import annotations

import logging
from pathlib import Path

import structlog

GENZ_EVENT_MAP: dict[str, str] = {
    "component_start": "🚀 开局啦 (ง •̀_•́)ง",
    "component_shutdown": "👋 收工咯 (￣▽￣)ゞ",
    "gamma_paginate": "🧭 拉盘数据ing (ง •̀_•́)ง",
    "category_refresh": "🧪 刷新分类 OK (•̀ᴗ•́)و",
    "top_refresh": "🏆 Top 刷新 OK (ง •̀_•́)ง",
    "refresh_failed": "😵 刷新翻车了",
    "tag_not_found": "🕵️ 标签没找到 (•́⍛•̀)",
    "signal_emit": "🚨 预警触发!",
    "domain_event": "📣 事件已发",
    "redis_publish": "📮 Redis 已推",
    "sink_publish_failed": "💥 下游炸了",
    "discord_webhook_missing": "⚠️ Discord 没配 Webhook",
    "discord_post_failed": "🚨 Discord 推送失败",
    "discord_payload_log_failed": "🧻 Discord 落盘翻车",
    "clob_connected": "🔌 WS 连上啦",
    "clob_decode_failed": "🧨 WS 解码翻车",
    "clob_reconnect": "🔄 WS 重连中",
    "clob_subscribe": "📡 订阅更新",
    "clob_operation": "🧰 WS 操作",
    "clob_payload_too_large": "🧱 WS 包太胖了",
    "orderbook_resync": "🔁 盘口重订阅",
    "orderbook_resync_throttled": "⏳ 盘口重订太频繁",
    "orderbook_seq_gap": "🧩 盘口序号断档",
    "orderbook_missing_snapshot": "🫥 盘口没快照",
    "web_volume_spike_emit": "🧊 灰盘放量警报",
    "monitoring_status_emit": "🟢 监控就绪通报",
    "feed_price_update": "💸 价格更新",
    "feed_message_ignored": "🙈 忽略消息",
    "market_lifecycle_ignored": "🙈 生命周期无关盘",
    "focus_filter": "🎯 关键词聚焦",
}


def _apply_genz_style(style: str):
    style_value = (style or "").lower()

    def processor(_: object, __: str, event_dict: dict) -> dict:
        if style_value not in {"genz", "gen-z"}:
            return event_dict
        event = event_dict.get("event")
        if not isinstance(event, str):
            return event_dict
        event_dict.setdefault("event_key", event)
        event_dict["event"] = GENZ_EVENT_MAP.get(event, f"✨ {event}")
        event_dict.setdefault("vibe", "genz")
        return event_dict

    return processor


def configure_logging(
    level: str,
    style: str = "genz",
    console: bool = True,
    file_path: str | None = None,
) -> None:
    level_name = level.upper()
    numeric_level = logging._nameToLevel.get(level_name, logging.INFO)
    handlers: list[logging.Handler] = []
    if console:
        handlers.append(logging.StreamHandler())
    if file_path:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path, encoding="utf-8"))
    if not handlers:
        handlers.append(logging.NullHandler())

    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        handlers=handlers,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _apply_genz_style(style),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
