from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Deque


class AsyncRateLimiter:
    """Simple asynchronous rate limiter using a sliding window.

    Parameters
    ----------
    rate:
        Maximum number of operations allowed during the configured period.
    per_seconds:
        Length of the sliding window expressed in seconds.
    """

    def __init__(self, rate: int, per_seconds: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if per_seconds <= 0:
            raise ValueError("per_seconds must be positive")

        self._rate = rate
        self._per_seconds = per_seconds
        self._timestamps: Deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self._per_seconds:
                    self._timestamps.popleft()

                if len(self._timestamps) < self._rate:
                    self._timestamps.append(now)
                    return

                sleep_for = self._per_seconds - (now - self._timestamps[0])

            await asyncio.sleep(max(sleep_for, 0))
