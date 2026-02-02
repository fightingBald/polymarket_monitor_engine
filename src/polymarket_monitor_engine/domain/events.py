from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    CANDIDATE_SELECTED = "CandidateSelected"
    SUBSCRIPTION_CHANGED = "SubscriptionChanged"
    MONITORING_STATUS = "MonitoringStatus"
    TRADE_SIGNAL = "TradeSignal"
    BOOK_SIGNAL = "BookSignal"
    PRICE_SIGNAL = "PriceSignal"
    MARKET_LIFECYCLE = "MarketLifecycle"
    HEALTH_EVENT = "HealthEvent"


class DomainEvent(BaseModel):
    event_id: str
    ts_ms: int
    source: str = "polymarket"
    category: str | None = None
    event_type: EventType
    market_id: str | None = None
    token_id: str | None = None
    side: str | None = None
    title: str | None = None
    topic_key: str | None = None
    metrics: dict[str, float | int | str] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None
