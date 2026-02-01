from __future__ import annotations

from typing import Protocol


class ClockPort(Protocol):
    def now_ms(self) -> int:
        ...

    async def sleep(self, seconds: float) -> None:
        ...
