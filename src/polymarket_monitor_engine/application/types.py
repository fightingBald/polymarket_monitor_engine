from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TokenMeta:
    token_id: str
    market_id: str
    category: str
    title: str | None
    side: str | None
    topic_key: str | None
    end_ts: int | None = None
