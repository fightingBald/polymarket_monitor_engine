from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
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


class SignalSettings(BaseModel):
    big_trade_usd: float = 10_000.0
    big_volume_1m_usd: float = 25_000.0
    big_wall_size: float | None = None
    cooldown_sec: int = 120


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


class ClobSettings(BaseModel):
    ws_url: str = "wss://clob.polymarket.com/ws"
    channel: str = "market"
    subscribe_action: str = "subscribe"
    unsubscribe_action: str = "unsubscribe"
    asset_key: str = "assets_ids"
    reconnect_backoff_sec: int = 5


class StdoutSinkSettings(BaseModel):
    enabled: bool = True


class RedisSinkSettings(BaseModel):
    enabled: bool = True
    url: str = "redis://localhost:6379/0"
    channel: str = "polymarket.events"


class SinkSettings(BaseModel):
    mode: str = "best_effort"
    required_sinks: list[str] = Field(default_factory=list)
    routes: dict[str, list[str]] = Field(default_factory=dict)
    transform: str = "full"
    stdout: StdoutSinkSettings = Field(default_factory=StdoutSinkSettings)
    redis: RedisSinkSettings = Field(default_factory=RedisSinkSettings)

    @field_validator("required_sinks", mode="before")
    @classmethod
    def _parse_required(cls, value: Any) -> Any:
        return _split_csv(value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PME__",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    filters: FilterSettings = Field(default_factory=FilterSettings)
    signals: SignalSettings = Field(default_factory=SignalSettings)
    rolling: RollingSettings = Field(default_factory=RollingSettings)
    gamma: GammaSettings = Field(default_factory=GammaSettings)
    clob: ClobSettings = Field(default_factory=ClobSettings)
    sinks: SinkSettings = Field(default_factory=SinkSettings)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


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

    env_settings = Settings()
    overrides = env_settings.model_dump(exclude_unset=True)
    merged = _deep_merge(file_data, overrides)
    return Settings.model_validate(merged)
