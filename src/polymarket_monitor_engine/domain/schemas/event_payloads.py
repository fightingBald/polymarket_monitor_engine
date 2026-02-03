from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SignalType(StrEnum):
    MAJOR_CHANGE = "major_change"
    BIG_TRADE = "big_trade"
    VOLUME_SPIKE_1M = "volume_spike_1m"
    BIG_WALL = "big_wall"
    WEB_VOLUME_SPIKE = "web_volume_spike"


class MajorChangePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: Literal[SignalType.MAJOR_CHANGE]
    pct_change: float
    pct_change_signed: float
    direction: str
    price: float
    prev_price: float
    window_sec: int
    notional: float
    source: str


class BigTradePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: Literal[SignalType.BIG_TRADE]
    notional: float
    price: float
    size: float
    vol_1m: float | None = None


class VolumeSpikePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: Literal[SignalType.VOLUME_SPIKE_1M]
    vol_1m: float
    price: float
    size: float


class BigWallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: Literal[SignalType.BIG_WALL]
    max_bid: float
    max_ask: float
    threshold: float


class WebVolumeSpikePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: Literal[SignalType.WEB_VOLUME_SPIKE]
    delta_volume: float
    volume_24h: float
    window_sec: int


SignalPayload = Annotated[
    MajorChangePayload
    | BigTradePayload
    | VolumeSpikePayload
    | BigWallPayload
    | WebVolumeSpikePayload,
    Field(discriminator="signal"),
]


class MonitoringStatusPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    market_count: int | None = None
    event_count: int | None = None
    token_count: int | None = None
    unsubscribable_count: int | None = None
    unsubscribable_event_count: int | None = None


class MarketLifecyclePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    end_ts: int | None = None


class HealthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    duration_ms: int | None = None
    error: str | None = None


class CandidateSelectedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    market_count: int


class SubscriptionChangedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token_count: int


EventPayload = (
    SignalPayload
    | MonitoringStatusPayload
    | MarketLifecyclePayload
    | HealthPayload
    | CandidateSelectedPayload
    | SubscriptionChangedPayload
)
