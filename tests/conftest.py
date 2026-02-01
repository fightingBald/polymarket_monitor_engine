from __future__ import annotations


class FakeClock:
    def __init__(self, start_ms: int = 1_700_000_000_000) -> None:
        self._now = start_ms

    def now_ms(self) -> int:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self._now += int(seconds * 1000)

    def advance(self, ms: int) -> None:
        self._now += ms


class CaptureSink:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event) -> None:
        self.events.append(event)
