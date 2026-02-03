from __future__ import annotations

from pathlib import Path

from polymarket_monitor_engine.config import SignalSettings
from tests.utils.alert_dataset import load_records
from tests.utils.alert_rules import should_alert


def test_alert_rules_match_dataset_expectations() -> None:
    settings = SignalSettings()
    dataset = Path("tests/fixtures/alert_dataset.jsonl")
    records = list(load_records(dataset))
    assert records
    for record in records:
        if record.expected_alert is None:
            continue
        assert should_alert(record, settings=settings) == record.expected_alert
