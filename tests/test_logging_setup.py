from __future__ import annotations

from datetime import UTC, datetime

from polymarket_monitor_engine.util.logging_setup import resolve_log_path


def test_resolve_log_path_inserts_timestamp() -> None:
    fixed = datetime(2026, 2, 3, 1, 2, 3, tzinfo=UTC)
    resolved = resolve_log_path("logs/pme.log", now=fixed)
    assert resolved == "logs/pme-20260203-010203.log"


def test_resolve_log_path_template_supports_ts() -> None:
    fixed = datetime(2026, 2, 3, 1, 2, 3, tzinfo=UTC)
    resolved = resolve_log_path("logs/pme-{ts}.log", now=fixed)
    assert resolved == "logs/pme-20260203-010203.log"


def test_resolve_log_path_none_returns_none() -> None:
    fixed = datetime(2026, 2, 3, 1, 2, 3, tzinfo=UTC)
    assert resolve_log_path(None, now=fixed) is None
