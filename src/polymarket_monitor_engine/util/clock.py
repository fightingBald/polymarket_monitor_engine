from __future__ import annotations

import asyncio
import time


class SystemClock:
    @staticmethod
    def now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    async def sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)
