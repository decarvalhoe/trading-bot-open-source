from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass
class DTCConfig:
    host: str
    port: int
    client_user_id: str = ""


class DTCAdapter:
    """Stub adapter for the Sierra Chart Data and Trading Communications protocol."""

    def __init__(self, config: DTCConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        async with self._lock:
            if self._connected:
                return
            logger.info(
                "Establishing DTC connection to %s:%s for %s",
                self._config.host,
                self._config.port,
                self._config.client_user_id or "anonymous",
            )
            # Real implementation would negotiate the binary protocol handshake here.
            await asyncio.sleep(0)
            self._connected = True

    async def publish_ticks(self, ticks: Iterable[Any]) -> None:
        if not self._connected:
            raise RuntimeError("DTC connection has not been established")
        # Placeholder for encoding and sending messages to Sierra Chart.
        batch = tuple(ticks)
        if not batch:
            return
        logger.debug("Publishing %s ticks to DTC", len(batch))

    async def close(self) -> None:
        async with self._lock:
            if not self._connected:
                return
            logger.info("Closing DTC connection")
            await asyncio.sleep(0)
            self._connected = False
