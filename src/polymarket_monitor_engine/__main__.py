from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import structlog
from dotenv import load_dotenv

from polymarket_monitor_engine.adapters.clob_ws import ClobWebSocketFeed
from polymarket_monitor_engine.adapters.discord_sink import DiscordWebhookSink
from polymarket_monitor_engine.adapters.gamma_http import GammaHttpCatalog
from polymarket_monitor_engine.adapters.multiplex_sink import MultiplexEventSink
from polymarket_monitor_engine.adapters.redis_sink import RedisPubSubSink
from polymarket_monitor_engine.adapters.stdout_sink import StdoutSink
from polymarket_monitor_engine.application.component import PolymarketComponent
from polymarket_monitor_engine.application.dashboard import TerminalDashboard
from polymarket_monitor_engine.application.discovery import MarketDiscovery
from polymarket_monitor_engine.application.monitor import SignalDetector
from polymarket_monitor_engine.config import Settings, load_settings
from polymarket_monitor_engine.util.clock import SystemClock
from polymarket_monitor_engine.util.httpx_setup import silence_httpx_logs
from polymarket_monitor_engine.util.logging_setup import configure_logging

logger = structlog.get_logger(__name__)


def _default_config_path() -> Path | None:
    candidate = Path("config/config.yaml")
    if candidate.exists():
        return candidate
    return None


def build_component(settings: Settings) -> PolymarketComponent:
    catalog = GammaHttpCatalog(
        base_url=settings.gamma.base_url,
        timeout_sec=settings.gamma.timeout_sec,
        page_size=settings.gamma.page_size,
        use_events_endpoint=settings.gamma.use_events_endpoint,
        events_limit_per_category=settings.gamma.events_limit_per_category,
        events_sort_primary=settings.gamma.events_sort_primary,
        events_sort_secondary=settings.gamma.events_sort_secondary,
        events_sort_desc=settings.gamma.events_sort_desc,
        related_tags=settings.gamma.related_tags,
        request_interval_ms=settings.gamma.request_interval_ms,
        tags_cache_sec=settings.gamma.tags_cache_sec,
        retry_max_attempts=settings.gamma.retry_max_attempts,
    )

    feed = ClobWebSocketFeed(
        ws_url=settings.clob.ws_url,
        channel=settings.clob.channel,
        custom_feature_enabled=settings.clob.custom_feature_enabled,
        initial_dump=settings.clob.initial_dump,
        max_frame_bytes=settings.clob.max_frame_bytes,
        max_message_bytes=settings.clob.max_message_bytes,
        ping_interval_sec=settings.clob.ping_interval_sec,
        ping_message=settings.clob.ping_message,
        pong_message=settings.clob.pong_message,
        reconnect_backoff_sec=settings.clob.reconnect_backoff_sec,
        reconnect_max_sec=settings.clob.reconnect_max_sec,
    )

    sinks = {}
    if settings.sinks.stdout.enabled:
        sinks["stdout"] = StdoutSink()
    if settings.sinks.redis.enabled:
        sinks["redis"] = RedisPubSubSink(
            url=settings.sinks.redis.url,
            channel=settings.sinks.redis.channel,
        )
    if settings.sinks.discord.enabled:
        sinks["discord"] = DiscordWebhookSink(
            max_retries=settings.sinks.discord.max_retries,
            timeout_sec=settings.sinks.discord.timeout_sec,
            aggregate_multi_outcome=settings.sinks.discord.aggregate_multi_outcome,
            aggregate_window_sec=settings.sinks.discord.aggregate_window_sec,
            aggregate_max_items=settings.sinks.discord.aggregate_max_items,
            log_payloads=settings.sinks.discord.log_payloads,
            log_payloads_path=settings.sinks.discord.log_payloads_path,
        )

    sink = MultiplexEventSink(
        sinks=sinks,
        mode=settings.sinks.mode,
        required_sinks=settings.sinks.required_sinks,
        routes=settings.sinks.routes,
        transform=settings.sinks.transform,
    )

    clock = SystemClock()
    discovery = MarketDiscovery(
        catalog=catalog,
        top_k_per_category=settings.filters.top_k_per_category,
        hot_sort=settings.filters.hot_sort,
        min_liquidity=settings.filters.min_liquidity,
        focus_keywords=settings.filters.focus_keywords,
        keyword_allow=settings.filters.keyword_allow,
        keyword_block=settings.filters.keyword_block,
        rolling_enabled=settings.rolling.enabled,
        primary_selection_priority=settings.rolling.primary_selection_priority,
        max_markets_per_topic=settings.rolling.max_markets_per_topic,
        top_enabled=settings.top.enabled,
        top_limit=settings.top.limit,
        top_order=settings.top.order,
        top_ascending=settings.top.ascending,
        top_featured_only=settings.top.featured_only,
        top_category_name=settings.top.category_name,
    )
    detector = SignalDetector(
        clock=clock,
        sink=sink,
        big_trade_usd=settings.signals.big_trade_usd,
        big_volume_1m_usd=settings.signals.big_volume_1m_usd,
        big_wall_size=settings.signals.big_wall_size,
        cooldown_sec=settings.signals.cooldown_sec,
        major_change_pct=settings.signals.major_change_pct,
        major_change_window_sec=settings.signals.major_change_window_sec,
        major_change_min_notional=settings.signals.major_change_min_notional,
        major_change_source=settings.signals.major_change_source,
    )

    dashboard = None
    if settings.dashboard.enabled:
        dashboard = TerminalDashboard(
            refresh_hz=settings.dashboard.refresh_hz,
            max_rows=settings.dashboard.max_rows,
            sort_by=settings.dashboard.sort_by,
            sort_desc=settings.dashboard.sort_desc,
        )

    return PolymarketComponent(
        categories=settings.app.categories,
        refresh_interval_sec=settings.app.refresh_interval_sec,
        discovery=discovery,
        feed=feed,
        sink=sink,
        clock=clock,
        detector=detector,
        resync_on_gap=settings.clob.resync_on_gap,
        resync_min_interval_sec=settings.clob.resync_min_interval_sec,
        polling_volume_threshold_usd=settings.signals.big_volume_1m_usd,
        polling_cooldown_sec=settings.signals.cooldown_sec,
        dashboard=dashboard,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket monitor engine")
    parser.add_argument(
        "--config",
        type=Path,
        default=_default_config_path(),
        help="Path to config YAML/JSON (default: config/config.yaml if present)",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Enable live terminal dashboard",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    settings = load_settings(args.config)
    if args.dashboard:
        settings.dashboard.enabled = True
    configure_logging(
        settings.logging.level,
        settings.logging.style,
        settings.logging.console,
        settings.logging.file_path,
    )
    silence_httpx_logs()

    component = build_component(settings)
    logger.info("component_start", categories=settings.app.categories)

    try:
        try:
            import uvloop

            uvloop.run(component.run())
        except ImportError:
            asyncio.run(component.run())
    except KeyboardInterrupt:
        logger.info("component_shutdown")


if __name__ == "__main__":
    main()
