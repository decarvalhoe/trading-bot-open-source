"""Async primitives used to propagate leader executions to the worker."""

from __future__ import annotations

import asyncio
from typing import Protocol

from .events import LeaderExecutionEvent


class LeaderExecutionPublisher(Protocol):
    """Publisher interface forwarding leader executions to the worker."""

    async def publish(self, event: LeaderExecutionEvent) -> None:
        raise NotImplementedError


class LeaderExecutionConsumer(Protocol):
    """Consumer interface implemented by the worker event loop."""

    async def get(self) -> LeaderExecutionEvent | None:
        raise NotImplementedError


class InMemoryLeaderExecutionBroker(LeaderExecutionPublisher, LeaderExecutionConsumer):
    """Simple asyncio queue used for development and testing."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[LeaderExecutionEvent | None] = asyncio.Queue()

    async def publish(self, event: LeaderExecutionEvent) -> None:
        await self._queue.put(event)

    async def get(self) -> LeaderExecutionEvent | None:
        event = await self._queue.get()
        self._queue.task_done()
        return event

    async def close(self) -> None:
        """Unblock pending consumers and signal shutdown."""

        await self._queue.put(None)


__all__ = [
    "LeaderExecutionPublisher",
    "LeaderExecutionConsumer",
    "InMemoryLeaderExecutionBroker",
]
