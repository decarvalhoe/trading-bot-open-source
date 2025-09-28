"""Async messaging primitives shared by Codex services."""

from __future__ import annotations

import asyncio
from typing import Protocol

from .events import CodexEvent


class EventPublisher(Protocol):
    """Publisher capable of emitting Codex events."""

    async def publish(self, event: CodexEvent) -> None:
        """Publish an event to the downstream worker."""
        raise NotImplementedError


class EventConsumer(Protocol):
    """Consumer interface used by the worker service."""

    async def get(self) -> CodexEvent:
        """Fetch the next available event, waiting if necessary."""
        raise NotImplementedError


class MemoryEventBroker(EventPublisher, EventConsumer):
    """In-memory broker used for development and testing."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[CodexEvent] = asyncio.Queue()

    async def publish(self, event: CodexEvent) -> None:
        await self._queue.put(event)

    async def get(self) -> CodexEvent:
        event = await self._queue.get()
        self._queue.task_done()
        return event
