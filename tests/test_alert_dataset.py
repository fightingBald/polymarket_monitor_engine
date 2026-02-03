from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.utils.alert_dataset import parse_discord_log_line


def test_parse_big_trade_line() -> None:
    line = json.dumps(
        {
            "ts": "2026-02-02T17:25:11.000Z",
            "event": "🧷 discord_outgoing",
            "payload": {
                "embeds": [
                    {
                        "title": "💥 大单成交",
                        "description": "Test Market",
                        "fields": [
                            {"name": "摘要", "value": "Test Market | 大单 $19,611.83 | 方向：YES"},
                            {"name": "价格", "value": "99.0¢"},
                            {"name": "数量", "value": "19809.93"},
                            {"name": "成交额", "value": "$19,611.83"},
                            {"name": "方向", "value": "YES"},
                            {"name": "分类", "value": "geopolitics"},
                            {"name": "市场ID", "value": "m1"},
                        ],
                    }
                ]
            },
        }
    )
    records = parse_discord_log_line(line)
    assert len(records) == 1
    record = records[0]
    assert record.signal == "big_trade"
    assert record.market_id == "m1"
    assert record.price == 0.99
    assert record.notional == 19611.83
    assert record.size == 19809.93
    assert record.side == "YES"


def test_parse_major_change_line() -> None:
    line = json.dumps(
        {
            "ts": "2026-02-02T17:24:59.000Z",
            "event": "🧷 discord_outgoing",
            "payload": {
                "embeds": [
                    {
                        "title": "🚨 重大变动",
                        "description": "US strikes Iran by February 5, 2026?",
                        "fields": [
                            {
                                "name": "摘要",
                                "value": (
                                    "US strikes Iran by February 5, 2026? | 变动 20.00% / 60s | "
                                    "方向：YES | 来源：trade"
                                ),
                            },
                            {"name": "价格", "value": "1.5¢ → 1.8¢"},
                            {"name": "窗口", "value": "60s"},
                            {"name": "来源", "value": "trade"},
                            {"name": "方向", "value": "YES"},
                            {"name": "分类", "value": "geopolitics"},
                            {"name": "市场ID", "value": "m2"},
                        ],
                    }
                ]
            },
        }
    )
    records = parse_discord_log_line(line)
    assert len(records) == 1
    record = records[0]
    assert record.signal == "major_change"
    assert record.price == pytest.approx(0.018)
    assert record.prev_price == pytest.approx(0.015)
    assert record.pct_change == pytest.approx(20.0)
    assert record.window_sec == 60


def test_parse_aggregate_volume_spike_expands() -> None:
    line = json.dumps(
        {
            "ts": "2026-02-02T18:00:00.000Z",
            "event": "🧷 discord_outgoing",
            "payload": {
                "embeds": [
                    {
                        "title": "📈 多选盘放量汇总",
                        "description": "Market X",
                        "fields": [
                            {"name": "摘要", "value": "Market X | volume_spike_1m | 2 个结果触发"},
                            {
                                "name": "明细",
                                "value": "DOWN: 1m 放量 $41,332.76\nUP: 1m 放量 $1,200.00",
                            },
                            {"name": "分类", "value": "finance"},
                            {"name": "市场ID", "value": "m3"},
                        ],
                    }
                ]
            },
        }
    )
    records = parse_discord_log_line(line)
    assert len(records) == 2
    assert records[0].signal == "volume_spike_1m"
    assert records[0].side == "DOWN"
    assert records[0].vol_1m == 41332.76
    assert records[1].side == "UP"
    assert records[1].vol_1m == 1200.0


def test_fixture_dataset_contains_all_signals() -> None:
    dataset = Path("tests/fixtures/alert_dataset.jsonl")
    assert dataset.exists()
    signals = set()
    with dataset.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            signals.add(payload.get("signal"))
    assert {"big_trade", "volume_spike_1m", "major_change", "web_volume_spike"} <= signals
