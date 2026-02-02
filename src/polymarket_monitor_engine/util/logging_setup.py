from __future__ import annotations

import logging

import structlog

GENZ_EVENT_MAP: dict[str, str] = {
    "component_start": "🚀 开局啦 (ง •̀_•́)ง",
    "component_shutdown": "👋 收工咯 (￣▽￣)ゞ",
    "gamma_paginate": "🧭 拉盘数据ing (ง •̀_•́)ง",
    "category_refresh": "🧪 刷新分类 OK (•̀ᴗ•́)و",
    "refresh_failed": "😵 刷新翻车了",
    "tag_not_found": "🕵️ 标签没找到 (•́⍛•̀)",
    "signal_emit": "🚨 预警触发!",
    "domain_event": "📣 事件已发",
    "redis_publish": "📮 Redis 已推",
    "sink_publish_failed": "💥 下游炸了",
    "discord_webhook_missing": "⚠️ Discord 没配 Webhook",
    "discord_post_failed": "🚨 Discord 推送失败",
    "clob_connected": "🔌 WS 连上啦",
    "clob_decode_failed": "🧨 WS 解码翻车",
    "clob_reconnect": "🔄 WS 重连中",
    "clob_subscribe": "📡 订阅更新",
    "clob_operation": "🧰 WS 操作",
    "orderbook_resync": "🔁 盘口重订阅",
    "orderbook_resync_throttled": "⏳ 盘口重订太频繁",
    "feed_price_update": "💸 价格更新",
    "feed_message_ignored": "🙈 忽略消息",
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


def configure_logging(level: str, style: str = "genz") -> None:
    level_name = level.upper()
    numeric_level = logging._nameToLevel.get(level_name, logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(message)s")
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
