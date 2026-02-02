from __future__ import annotations

import json

import pytest

from polymarket_monitor_engine.config import load_settings


def test_load_settings_yaml_with_env_override(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  categories: "finance, geopolitics"
filters:
  hot_sort: "liquidity,volume_24h"
sinks:
  redis:
    enabled: false
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("PME__SINKS__REDIS__URL", "redis://example:6379/1")
    settings = load_settings(config_path)

    assert settings.app.categories == ["finance", "geopolitics"]
    assert settings.filters.hot_sort == ["liquidity", "volume_24h"]
    assert settings.sinks.redis.enabled is False
    assert settings.sinks.redis.url == "redis://example:6379/1"


def test_load_settings_env_csv_lists(monkeypatch) -> None:
    monkeypatch.setenv("PME__APP__CATEGORIES", "finance,politics")
    monkeypatch.setenv("PME__FILTERS__HOT_SORT", "liquidity,volume_24h")
    settings = load_settings(None)

    assert settings.app.categories == ["finance", "politics"]
    assert settings.filters.hot_sort == ["liquidity", "volume_24h"]


def test_load_settings_json(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"app": {"categories": ["finance"]}}),
        encoding="utf-8",
    )
    settings = load_settings(config_path)
    assert settings.app.categories == ["finance"]


def test_load_settings_unsupported_format(tmp_path) -> None:
    config_path = tmp_path / "config.txt"
    config_path.write_text("noop", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(config_path)
