from __future__ import annotations

from dataclasses import dataclass

from polymarket_monitor_engine.config import SignalSettings
from tests.utils.alert_dataset import AlertRecord


@dataclass(frozen=True)
class AlertDecision:
    allowed: bool
    reason: str


def should_alert(record: AlertRecord, settings: SignalSettings, now_ms: int | None = None) -> bool:
    return evaluate_alert(record, settings=settings, now_ms=now_ms).allowed


def evaluate_alert(
    record: AlertRecord,
    settings: SignalSettings,
    now_ms: int | None = None,
) -> AlertDecision:
    if settings.drop_expired_markets and record.end_ts is not None:
        compare_ts = now_ms if now_ms is not None else record.ts_ms
        if compare_ts is not None and record.end_ts <= compare_ts:
            return AlertDecision(False, "expired_market")

    if (
        record.signal in {"big_trade", "volume_spike_1m"}
        and record.price is not None
        and _is_high_confidence(record.price, settings)
        and not _is_reverse_allow(record.price, settings)
    ):
        return AlertDecision(False, "high_confidence")

    if record.signal == "big_trade":
        if record.notional is not None and record.notional < settings.big_trade_usd:
            return AlertDecision(False, "big_trade_threshold")
        return AlertDecision(True, "ok")

    if record.signal == "volume_spike_1m":
        if record.vol_1m is not None and record.vol_1m < settings.big_volume_1m_usd:
            return AlertDecision(False, "volume_spike_threshold")
        return AlertDecision(True, "ok")

    if record.signal == "web_volume_spike":
        if record.delta_volume is not None and record.window_sec is not None:
            threshold = settings.big_volume_1m_usd * max(record.window_sec, 1) / 60.0
            if record.delta_volume < threshold:
                return AlertDecision(False, "web_volume_threshold")
        return AlertDecision(True, "ok")

    if record.signal == "major_change":
        price = record.price
        prev_price = record.prev_price
        pct_change = record.pct_change
        if price is not None and prev_price is not None:
            abs_delta = abs(price - prev_price)
            low_price_zone = (
                settings.major_change_low_price_abs > 0
                and settings.major_change_low_price_max > 0
                and min(price, prev_price) <= settings.major_change_low_price_max
            )
            if low_price_zone:
                if abs_delta < settings.major_change_low_price_abs:
                    return AlertDecision(False, "low_price_abs")
            else:
                if pct_change is None and prev_price > 0:
                    pct_change = abs_delta / prev_price * 100
                if pct_change is not None and pct_change < settings.major_change_pct:
                    return AlertDecision(False, "major_change_threshold")
        return AlertDecision(True, "ok")

    return AlertDecision(True, "unknown_signal")


def _is_high_confidence(price: float, settings: SignalSettings) -> bool:
    if settings.high_confidence_threshold <= 0:
        return False
    if price < 0 or price > 1:
        return False
    confidence = max(price, 1.0 - price)
    return confidence >= settings.high_confidence_threshold


def _is_reverse_allow(price: float, settings: SignalSettings) -> bool:
    if settings.reverse_allow_threshold <= 0:
        return False
    if price < 0 or price > 1:
        return False
    return price <= settings.reverse_allow_threshold
