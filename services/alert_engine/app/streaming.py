"""Streaming utilities for the alert engine."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from .clients import MarketDataStreamClient
from .engine import AlertEngine
from .schemas import MarketEvent

logger = logging.getLogger(__name__)


class StreamProcessor:
    """Consume market data streams and push events into the alert engine."""

    def __init__(
        self,
        stream_client: MarketDataStreamClient,
        engine: AlertEngine,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._stream_client = stream_client
        self._engine = engine
        self._session_factory = session_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stop_event = asyncio.Event()

    async def start(self, symbols: list[str] | tuple[str, ...]) -> None:
        if self._tasks:
            return
        self._stop_event.clear()
        for symbol in symbols:
            task = asyncio.create_task(self._consume(symbol))
            self._tasks[symbol] = task

    async def stop(self) -> None:
        self._stop_event.set()
        for task in list(self._tasks.values()):
            task.cancel()
        for symbol, task in list(self._tasks.items()):
            try:
                await task
            except asyncio.CancelledError:  # pragma: no cover - expected on shutdown
                logger.debug("Stream task for %s cancelled", symbol)
            except Exception:  # noqa: BLE001
                logger.exception("Stream task for %s terminated with error", symbol)
        self._tasks.clear()

    async def _consume(self, symbol: str) -> None:
        try:
            async for payload in self._stream_client.subscribe(symbol):
                if self._stop_event.is_set():
                    break
                await self._handle_payload(symbol, payload)
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Market data stream consumption failed for %s", symbol)

    async def _handle_payload(self, symbol: str, payload: dict[str, Any]) -> None:
        try:
            event = MarketEvent.model_validate({"symbol": symbol, **payload})
        except Exception:  # noqa: BLE001
            logger.debug("Dropping malformed payload for %s: %s", symbol, payload, exc_info=True)
            return
        async with self._session_context() as session:
            await self._engine.handle_event(session, event)

    @asynccontextmanager
    async def _session_context(self):
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()


__all__ = ["StreamProcessor"]
