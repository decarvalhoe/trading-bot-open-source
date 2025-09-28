from __future__ import annotations

import asyncio
import time

from services.market_data.adapters import AsyncRateLimiter


def test_rate_limiter_enforces_spacing() -> None:
    async def run() -> None:
        limiter = AsyncRateLimiter(rate=1, per_seconds=0.2)
        timestamps: list[float] = []

        async def call() -> None:
            await limiter.acquire()
            timestamps.append(time.monotonic())

        await call()
        await call()
        assert timestamps[1] - timestamps[0] >= 0.18

    asyncio.run(run())
