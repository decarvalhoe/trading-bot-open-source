from __future__ import annotations

import asyncio
import time

import pytest

from services.market_data.adapters import AsyncRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_enforces_spacing() -> None:
    limiter = AsyncRateLimiter(rate=1, per_seconds=0.2)
    timestamps: list[float] = []

    async def call() -> None:
        await limiter.acquire()
        timestamps.append(time.monotonic())

    await call()
    await call()
    assert timestamps[1] - timestamps[0] >= 0.18
