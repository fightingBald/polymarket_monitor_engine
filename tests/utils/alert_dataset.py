from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
from pydantic import BaseModel, ConfigDict

logger = structlog.get_logger(__name__)

_MONEY_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")
_PRICE_RE = re.compile(r"([\d.]+)¢")
_PCT_RE = re.compile(r"([\d.]+)%")


class AlertRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
    ts: str
    ts_ms: int | None = None
    signal: str
    market_id: str | None = None
    title: str | None = None
    category: str | None = None
    side: str | None = None
    price: float | None = None
    prev_price: float | None = None
    size: float | None = None
    notional: float | None = None
    vol_1m: float | None = None
    delta_volume: float | None = None
    pct_change: float | None = None
    window_sec: int | None = None
    source: str | None = None
    end_ts: int | None = None
    confidence: float | None = None
    is_aggregate: bool = False
    aggregate_group: str | None = None
    detail_index: int | None = None
    expected_alert: bool | None = None
    origin: str = "discord_log"
    raw_summary: str | None = None
    raw_title: str | None = None


@dataclass(frozen=True)
class ParseResult:
    records: list[AlertRecord]
    skipped: int


def build_dataset(
    input_path: Path,
    output_path: Path,
    expand_aggregates: bool = True,
) -> ParseResult:
    records: list[AlertRecord] = []
    skipped = 0
    for line in input_path.read_text(encoding="utf-8").splitlines():
        parsed = parse_discord_log_line(line, expand_aggregates=expand_aggregates)
        if not parsed:
            skipped += 1
            continue
        records.extend(parsed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(record.model_dump_json(ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    logger.info(
        "alert_dataset_built",
        input=str(input_path),
        output=str(output_path),
        records=len(records),
        skipped=skipped,
    )
    return ParseResult(records=records, skipped=skipped)


def append_mock_record(dataset_path: Path, record: AlertRecord) -> None:
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    with dataset_path.open("a", encoding="utf-8") as handle:
        handle.write(record.model_dump_json(ensure_ascii=False) + "\n")
    logger.info(
        "alert_dataset_mock_append",
        output=str(dataset_path),
        record_id=record.record_id,
    )


def parse_discord_log_line(
    line: str,
    expand_aggregates: bool = True,
) -> list[AlertRecord]:
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
        return []
    embeds = entry.get("payload", {}).get("embeds") or []
    if not embeds:
        return []
    records: list[AlertRecord] = []
    ts = entry.get("ts")
    for embed in embeds:
        records.extend(parse_discord_embed(embed, ts=ts, expand_aggregates=expand_aggregates))
    return records


def parse_discord_embed(
    embed: dict[str, Any],
    ts: str | None,
    expand_aggregates: bool = True,
) -> list[AlertRecord]:
    title = str(embed.get("title") or "")
    signal, is_aggregate = _resolve_signal(title)
    if not signal:
        return []
    fields = embed.get("fields") or []
    field_map = {str(item.get("name")): str(item.get("value")) for item in fields}
    description = embed.get("description")
    embed_ts = embed.get("timestamp") or ts or datetime.now(tz=UTC).isoformat()
    ts_ms = _parse_ts_ms(embed_ts)
    if is_aggregate and expand_aggregates:
        return _parse_aggregate_records(
            signal=signal,
            raw_title=title,
            embed_ts=embed_ts,
            ts_ms=ts_ms,
            description=description,
            field_map=field_map,
        )
    return [
        _base_record(
            signal=signal,
            raw_title=title,
            embed_ts=embed_ts,
            ts_ms=ts_ms,
            description=description,
            field_map=field_map,
            is_aggregate=is_aggregate,
        )
    ]


def load_records(path: Path) -> Iterator[AlertRecord]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield AlertRecord.model_validate_json(line)


def _parse_aggregate_records(
    signal: str,
    raw_title: str,
    embed_ts: str,
    ts_ms: int | None,
    description: str | None,
    field_map: dict[str, str],
) -> list[AlertRecord]:
    detail = field_map.get("明细") or ""
    lines = [line.strip() for line in detail.splitlines() if line.strip()]
    if not lines:
        return [
            _base_record(
                signal=signal,
                raw_title=raw_title,
                embed_ts=embed_ts,
                ts_ms=ts_ms,
                description=description,
                field_map=field_map,
                is_aggregate=True,
            )
        ]
    group_id = _aggregate_group_id(signal=signal, market_id=field_map.get("市场ID"), ts=embed_ts)
    records: list[AlertRecord] = []
    for idx, line in enumerate(lines):
        detail_fields = _parse_aggregate_detail(signal, line)
        record = _base_record(
            signal=signal,
            raw_title=raw_title,
            embed_ts=embed_ts,
            ts_ms=ts_ms,
            description=description,
            field_map=field_map,
            is_aggregate=True,
        )
        record.aggregate_group = group_id
        record.detail_index = idx
        if detail_fields.side:
            record.side = detail_fields.side
        if detail_fields.price is not None:
            record.price = detail_fields.price
        if detail_fields.notional is not None:
            record.notional = detail_fields.notional
        if detail_fields.vol_1m is not None:
            record.vol_1m = detail_fields.vol_1m
        if detail_fields.pct_change is not None:
            record.pct_change = detail_fields.pct_change
        if detail_fields.raw_summary:
            record.raw_summary = detail_fields.raw_summary
        if record.price is not None:
            record.confidence = max(record.price, 1.0 - record.price)
        records.append(record)
    return records


@dataclass(frozen=True)
class _DetailFields:
    side: str | None = None
    notional: float | None = None
    price: float | None = None
    vol_1m: float | None = None
    pct_change: float | None = None
    raw_summary: str | None = None


def _parse_aggregate_detail(signal: str, line: str) -> _DetailFields:
    side, rest = _split_detail_side(line)
    if signal == "big_trade":
        money = _parse_money(rest)
        price = _parse_price(rest)
        return _DetailFields(
            side=side,
            notional=money,
            price=price,
            raw_summary=line,
        )
    if signal == "volume_spike_1m":
        money = _parse_money(rest)
        return _DetailFields(side=side, vol_1m=money, raw_summary=line)
    if signal == "major_change":
        pct = _parse_pct(rest)
        price = _parse_price(rest)
        return _DetailFields(side=side, pct_change=pct, price=price, raw_summary=line)
    return _DetailFields(raw_summary=line)


def _split_detail_side(line: str) -> tuple[str | None, str]:
    if ":" not in line:
        return None, line
    side, rest = line.split(":", 1)
    side = side.strip()
    return side or None, rest.strip()


def _base_record(
    signal: str,
    raw_title: str,
    embed_ts: str,
    ts_ms: int | None,
    description: str | None,
    field_map: dict[str, str],
    is_aggregate: bool,
) -> AlertRecord:
    raw_summary = field_map.get("摘要")
    price_field = field_map.get("价格")
    price, prev_price = _parse_price_pair(price_field)
    pct_change = _parse_pct(raw_summary) if raw_summary else None
    if pct_change is None and price is not None and prev_price is not None and prev_price > 0:
        pct_change = abs(price - prev_price) / prev_price * 100
    vol_1m = _parse_money(field_map.get("1m 放量") or field_map.get("成交额"))
    delta_volume = _parse_money(field_map.get("区间成交"))
    notional = _parse_money(field_map.get("成交额"))
    size = _parse_float(field_map.get("数量"))
    window_sec = _parse_window(field_map.get("窗口"))
    source = field_map.get("来源")
    side = field_map.get("方向")
    category = field_map.get("分类")
    market_id = field_map.get("市场ID")
    record = AlertRecord(
        record_id=str(uuid4()),
        ts=str(embed_ts),
        ts_ms=ts_ms,
        signal=signal,
        market_id=market_id,
        title=description or None,
        category=category,
        side=side,
        price=price,
        prev_price=prev_price,
        size=size,
        notional=notional,
        vol_1m=vol_1m,
        delta_volume=delta_volume,
        pct_change=pct_change,
        window_sec=window_sec,
        source=source,
        confidence=max(price, 1.0 - price) if price is not None else None,
        is_aggregate=is_aggregate,
        raw_summary=raw_summary,
        raw_title=raw_title,
    )
    return record


def _resolve_signal(title: str) -> tuple[str | None, bool]:
    if title.startswith("🚨 重大变动"):
        return "major_change", False
    if title.startswith("💥 大单成交"):
        return "big_trade", False
    if title.startswith("📈 放量（1分钟）"):
        return "volume_spike_1m", False
    if title.startswith("🧊 灰盘放量"):
        return "web_volume_spike", False
    if title.startswith("💥 多选盘大单汇总"):
        return "big_trade", True
    if title.startswith("📈 多选盘放量汇总"):
        return "volume_spike_1m", True
    if title.startswith("📊 多选盘异动汇总"):
        return "major_change", True
    return None, False


def _aggregate_group_id(signal: str, market_id: str | None, ts: str) -> str:
    return f"{market_id or 'n/a'}:{signal}:{ts}"


def _parse_money(value: str | None) -> float | None:
    if not value:
        return None
    match = _MONEY_RE.search(value)
    if not match:
        return None
    return _parse_float(match.group(1))


def _parse_price_pair(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    if "→" in value:
        left, right = [part.strip() for part in value.split("→", 1)]
        prev = _parse_price(left)
        current = _parse_price(right)
        return current, prev
    price = _parse_price(value)
    return price, None


def _parse_price(value: str | None) -> float | None:
    if not value:
        return None
    match = _PRICE_RE.search(value)
    if not match:
        return None
    number = _parse_float(match.group(1))
    if number is None:
        return None
    return number / 100.0


def _parse_pct(value: str | None) -> float | None:
    if not value:
        return None
    match = _PCT_RE.search(value)
    if not match:
        return None
    return _parse_float(match.group(1))


def _parse_window(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip().lower().rstrip("s")
    if not value.isdigit():
        return None
    return int(value)


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _parse_ts_ms(value: str) -> int | None:
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None
