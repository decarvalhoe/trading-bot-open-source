"""Dependency wiring for the Codex gateway."""

from __future__ import annotations

from fastapi import Depends

from libs.codex import MemoryEventBroker

from .config import Settings, get_settings


async def get_broker(settings: Settings = Depends(get_settings)) -> MemoryEventBroker:
    """Return the in-memory broker used to push events to the worker."""

    if settings.broker_backend != "memory":  # pragma: no cover - placeholder for future backends
        msg = f"Unsupported broker backend: {settings.broker_backend}"
        raise RuntimeError(msg)

    if not hasattr(get_broker, "_broker"):
        get_broker._broker = MemoryEventBroker()  # type: ignore[attr-defined]
    return get_broker._broker  # type: ignore[attr-defined]
