from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class FeedMessage:
    kind: str
    payload: dict


class FeedPort(Protocol):
    async def connect(self) -> None: ...

    async def subscribe(self, token_ids: list[str]) -> None: ...

    async def resubscribe(self, token_ids: list[str]) -> None: ...

    async def messages(self) -> AsyncIterator[FeedMessage]: ...

    async def close(self) -> None: ...
