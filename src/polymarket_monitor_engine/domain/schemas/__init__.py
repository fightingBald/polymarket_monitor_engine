"""Typed schemas for domain events."""

from .event_payloads import (
    BigTradePayload,
    BigWallPayload,
    CandidateSelectedPayload,
    EventPayload,
    HealthPayload,
    MajorChangePayload,
    MarketLifecyclePayload,
    MonitoringStatusPayload,
    SignalPayload,
    SignalType,
    SubscriptionChangedPayload,
    VolumeSpikePayload,
    WebVolumeSpikePayload,
)

__all__ = [
    "BigTradePayload",
    "BigWallPayload",
    "CandidateSelectedPayload",
    "EventPayload",
    "HealthPayload",
    "MajorChangePayload",
    "MarketLifecyclePayload",
    "MonitoringStatusPayload",
    "SignalPayload",
    "SignalType",
    "SubscriptionChangedPayload",
    "VolumeSpikePayload",
    "WebVolumeSpikePayload",
]
