from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Protocol

import redis.asyncio as redis

from .config import get_settings
from .schemas import TickPayload


class TickStream(Protocol):
    async def listen(self) -> AsyncIterator[TickPayload]:
        ...


class RedisTickStream:
    def __init__(self, channel: str = "market-data") -> None:
        self._settings = get_settings()
        self._channel = channel
        self._client = redis.from_url(self._settings.redis_url)

    async def listen(self) -> AsyncIterator[TickPayload]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(self._channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                payload = TickPayload.model_validate_json(message["data"])
                yield payload
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()
            await self._client.close()


class SimulatedTickStream:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[TickPayload | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ready = threading.Event()

    async def listen(self) -> AsyncIterator[TickPayload]:
        self._loop = asyncio.get_running_loop()
        self._ready.set()
        while True:
            payload = await self._queue.get()
            if payload is None:
                break
            yield payload

    def publish(self, payload: TickPayload) -> None:
        if not self._ready.wait(timeout=1):
            raise RuntimeError("Stream not initialised")
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(self._queue.put(payload), self._loop)
        fut.result()

    def close(self) -> None:
        if not self._ready.wait(timeout=1):
            return
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(self._queue.put(None), self._loop)
        fut.result()
