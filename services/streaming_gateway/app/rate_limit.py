"""Simple IP based leaky bucket rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Track requests per IP over a rolling time window."""

    def __init__(self, max_calls: int, window_seconds: int = 60) -> None:
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, ip: str) -> None:
        now = time.time()
        bucket = self._calls[ip]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.max_calls:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS)
        bucket.append(now)


async def rate_limit_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    limiter: RateLimiter = request.app.state.rate_limiter
    client_ip = request.client.host if request.client else "anonymous"
    limiter.check(client_ip)
    return await call_next(request)
