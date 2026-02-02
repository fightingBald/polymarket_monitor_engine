from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Tag(BaseModel):
    tag_id: str
    slug: str | None = None
    name: str | None = None
    raw: dict[str, Any] | None = None


class OutcomeToken(BaseModel):
    token_id: str
    side: str | None = None
    raw: dict[str, Any] | None = None


class Market(BaseModel):
    market_id: str
    question: str
    event_id: str | None = None
    category: str | None = None
    enable_orderbook: bool | None = None
    active: bool = True
    closed: bool = False
    resolved: bool = False
    end_ts: int | None = None
    liquidity: float | None = None
    volume_24h: float | None = None
    token_ids: list[str] = Field(default_factory=list)
    outcomes: list[OutcomeToken] = Field(default_factory=list)
    topic_key: str | None = None
    raw: dict[str, Any] | None = None


class TradeTick(BaseModel):
    token_id: str
    market_id: str | None = None
    side: str | None = None
    price: float
    size: float
    ts_ms: int
    raw: dict[str, Any] | None = None


class BookLevel(BaseModel):
    price: float
    size: float


class BookSnapshot(BaseModel):
    token_id: str
    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)
    ts_ms: int
    raw: dict[str, Any] | None = None
