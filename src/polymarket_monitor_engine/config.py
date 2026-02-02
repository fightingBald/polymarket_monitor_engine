from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from deepmerge import Merger
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: Any) -> Any:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        return items
    return value


class AppSettings(BaseModel):
    categories: list[str] = Field(default_factory=lambda: ["finance", "geopolitics"])
    refresh_interval_sec: int = 60

    @field_validator("categories", mode="before")
    @classmethod
    def _parse_categories(cls, value: Any) -> Any:
        return _split_csv(value)


class LoggingSettings(BaseModel):
    level: str = "INFO"
    style: str = "genz"
    console: bool = True
    file_path: str | None = None


class DashboardSettings(BaseModel):
    enabled: bool = False
    refresh_hz: float = 2.0
    max_rows: int = 50
    sort_by: str = "activity"
    sort_desc: bool = True


class FilterSettings(BaseModel):
    top_k_per_category: int = 10
    hot_sort: list[str] = Field(default_factory=lambda: ["liquidity", "volume_24h"])
    min_liquidity: float | None = None
    keyword_allow: list[str] = Field(default_factory=list)
    keyword_block: list[str] = Field(default_factory=list)

    @field_validator("hot_sort", "keyword_allow", "keyword_block", mode="before")
    @classmethod
    def _parse_lists(cls, value: Any) -> Any:
        return _split_csv(value)


class TopSettings(BaseModel):
    enabled: bool = False
    limit: int = 30
    order: str = "volume24hr"
    ascending: bool = False
    featured_only: bool = False
    category_name: str = "top"


class SignalSettings(BaseModel):
    big_trade_usd: float = 10_000.0
    big_volume_1m_usd: float = 25_000.0
    big_wall_size: float | None = None
    cooldown_sec: int = 120
    major_change_pct: float = 5.0
    major_change_window_sec: int = 60
    major_change_min_notional: float = 0.0
    major_change_source: str = "trade"


class RollingSettings(BaseModel):
    enabled: bool = True
    primary_selection_priority: list[str] = Field(
        default_factory=lambda: ["liquidity", "volume_24h", "end_ts"]
    )
    max_markets_per_topic: int = 1

    @field_validator("primary_selection_priority", mode="before")
    @classmethod
    def _parse_priority(cls, value: Any) -> Any:
        return _split_csv(value)


class GammaSettings(BaseModel):
    base_url: str = "https://gamma-api.polymarket.com"
    timeout_sec: float = 10.0
    page_size: int = 200
    use_events_endpoint: bool = True
    related_tags: bool = False
    request_interval_ms: int = 0
    tags_cache_sec: int = 600
    retry_max_attempts: int = 5


class ClobSettings(BaseModel):
    ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    channel: str = "market"
    custom_feature_enabled: bool = True
    initial_dump: bool = True
    ping_interval_sec: int | None = 10
    ping_message: str = "PING"
    pong_message: str = "pong"
    reconnect_backoff_sec: int = 5
    reconnect_max_sec: int = 60
    resync_on_gap: bool = True
    resync_min_interval_sec: int = 30


class StdoutSinkSettings(BaseModel):
    enabled: bool = True


class RedisSinkSettings(BaseModel):
    enabled: bool = True
    url: str = "redis://localhost:6379/0"
    channel: str = "polymarket.events"


class DiscordSinkSettings(BaseModel):
    enabled: bool = False
    max_retries: int = 5
    timeout_sec: float = 10.0
    aggregate_multi_outcome: bool = True
    aggregate_window_sec: float = 2.0
    aggregate_max_items: int = 5


class SinkSettings(BaseModel):
    mode: str = "best_effort"
    required_sinks: list[str] = Field(default_factory=list)
    routes: dict[str, list[str]] = Field(default_factory=dict)
    transform: str = "full"
    stdout: StdoutSinkSettings = Field(default_factory=StdoutSinkSettings)
    redis: RedisSinkSettings = Field(default_factory=RedisSinkSettings)
    discord: DiscordSinkSettings = Field(default_factory=DiscordSinkSettings)

    @field_validator("required_sinks", mode="before")
    @classmethod
    def _parse_required(cls, value: Any) -> Any:
        return _split_csv(value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PME__",
        env_nested_delimiter="__",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)
    filters: FilterSettings = Field(default_factory=FilterSettings)
    top: TopSettings = Field(default_factory=TopSettings)
    signals: SignalSettings = Field(default_factory=SignalSettings)
    rolling: RollingSettings = Field(default_factory=RollingSettings)
    gamma: GammaSettings = Field(default_factory=GammaSettings)
    clob: ClobSettings = Field(default_factory=ClobSettings)
    sinks: SinkSettings = Field(default_factory=SinkSettings)


_MERGER = Merger([(dict, ["merge"]), (list, ["override"])], ["override"], ["override"])


def _merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    return _MERGER.merge(dict(base), override)


def load_settings(path: Path | None) -> Settings:
    file_data: dict[str, Any] = {}
    if path is not None:
        raw = path.read_text(encoding="utf-8")
        if path.suffix in {".yaml", ".yml"}:
            file_data = yaml.safe_load(raw) or {}
        elif path.suffix == ".json":
            file_data = json.loads(raw)
        else:
            raise ValueError(f"Unsupported config format: {path}")

    _sanitize_env_overrides()
    env_settings = Settings()
    overrides = env_settings.model_dump(exclude_unset=True)
    merged = _merge_settings(file_data, overrides)
    return Settings.model_validate(merged)


def _sanitize_env_overrides(prefix: str = "PME__") -> None:
    list_env_keys = {
        f"{prefix}APP__CATEGORIES",
        f"{prefix}FILTERS__HOT_SORT",
        f"{prefix}FILTERS__KEYWORD_ALLOW",
        f"{prefix}FILTERS__KEYWORD_BLOCK",
        f"{prefix}ROLLING__PRIMARY_SELECTION_PRIORITY",
        f"{prefix}SINKS__REQUIRED_SINKS",
    }
    for key in list(os.environ.keys()):
        if not key.startswith(prefix):
            continue
        value = os.environ.get(key)
        if value is None:
            continue
        if not value.strip():
            os.environ.pop(key, None)
            continue
        if key in list_env_keys:
            stripped = value.strip()
            if not (stripped.startswith("[") or stripped.startswith("{")):
                items = [item.strip() for item in stripped.split(",") if item.strip()]
                os.environ[key] = json.dumps(items)
                continue
        suffix = key[len(prefix) :]
        if "__" not in suffix:
            try:
                json.loads(value)
            except Exception:
                os.environ.pop(key, None)
