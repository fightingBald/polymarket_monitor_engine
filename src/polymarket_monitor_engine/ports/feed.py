from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


@dataclass(slots=True)
class FeedMessage:
    kind: str
    payload: dict


class FeedPort(Protocol):
    async def connect(self) -> None:
        ...

    async def subscribe(self, token_ids: list[str]) -> None:
        ...

    async def messages(self) -> AsyncIterator[FeedMessage]:
        ...

    async def close(self) -> None:
        ...
