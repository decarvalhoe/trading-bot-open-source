"""Caching primitives used by the alert engine."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any

from .clients import MarketDataClient, ReportsClient
from .schemas import MarketEvent


@dataclass(slots=True)
class _CacheEntry:
    data: dict[str, Any]
    expires_at: float | None


class ExpiringCache:
    """Simple TTL cache that stores dictionaries keyed by symbol."""

    def __init__(self, ttl_seconds: float | None = None) -> None:
        self._ttl_seconds = ttl_seconds
        self._values: dict[str, _CacheEntry] = {}

    def store(self, key: str, data: dict[str, Any]) -> None:
        expires_at: float | None
        if self._ttl_seconds is None:
            expires_at = None
        else:
            expires_at = monotonic() + self._ttl_seconds
        self._values[key] = _CacheEntry(data=data, expires_at=expires_at)

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._values.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at <= monotonic():
            self._values.pop(key, None)
            return None
        return entry.data


class AlertContextCache:
    """Maintain latest contexts by combining streamed events and service lookups."""

    def __init__(
        self,
        *,
        market_client: MarketDataClient,
        reports_client: ReportsClient,
        market_ttl_seconds: float | None = 30.0,
        event_ttl_seconds: float | None = 2.0,
        reports_ttl_seconds: float | None = 60.0,
    ) -> None:
        self._market_client = market_client
        self._reports_client = reports_client
        self._market_cache = ExpiringCache(market_ttl_seconds)
        self._event_cache = ExpiringCache(event_ttl_seconds)
        self._reports_cache = ExpiringCache(reports_ttl_seconds)
        self._lock = asyncio.Lock()

    async def build_context_for_event(self, event: MarketEvent) -> dict[str, Any]:
        """Merge the incoming event with cached contexts from downstream services."""

        base = event.model_dump(exclude_none=True)
        async with self._lock:
            self._event_cache.store(event.symbol, base)
            merged = await self._compose(event.symbol, base)
        return merged

    async def build_context_for_symbol(self, symbol: str) -> dict[str, Any]:
        """Return a context for a symbol when no fresh event is available."""

        async with self._lock:
            merged = await self._compose(symbol, {"symbol": symbol})
        return merged

    async def _compose(self, symbol: str, base: dict[str, Any]) -> dict[str, Any]:
        context = dict(base)
        market_context = await self._market_context(symbol)
        reports_context = await self._reports_context(symbol)
        context.update(market_context)
        context.update(reports_context)
        return self._normalise_context(context)

    async def _market_context(self, symbol: str) -> dict[str, Any]:
        snapshot = self._market_cache.get(symbol)
        if snapshot is None:
            snapshot = await self._market_client.fetch_context(symbol)
            self._market_cache.store(symbol, snapshot)
        event_override = self._event_cache.get(symbol) or {}
        if not event_override:
            return snapshot
        merged = dict(snapshot)
        merged.update(event_override)
        return merged

    async def _reports_context(self, symbol: str) -> dict[str, Any]:
        cached = self._reports_cache.get(symbol)
        if cached is not None:
            return cached
        fresh = await self._reports_client.fetch_context(symbol)
        self._reports_cache.store(symbol, fresh)
        return fresh

    def _normalise_context(self, context: dict[str, Any]) -> dict[str, Any]:
        normalised = dict(context)

        performance = normalised.get("performance") or normalised.get("metrics") or {}
        if isinstance(performance, dict):
            if "pnl" in performance:
                normalised.setdefault("pnl", performance.get("pnl"))
            if "current_pnl" in performance:
                normalised.setdefault("pnl", performance.get("current_pnl"))
            if "drawdown" in performance:
                normalised.setdefault("drawdown", performance.get("drawdown"))
            if "current_drawdown" in performance:
                normalised.setdefault("drawdown", performance.get("current_drawdown"))

        if "current_pnl" in normalised and "pnl" not in normalised:
            normalised["pnl"] = normalised["current_pnl"]
        if "current_drawdown" in normalised and "drawdown" not in normalised:
            normalised["drawdown"] = normalised["current_drawdown"]

        indicators = normalised.get("indicators")
        if isinstance(indicators, dict):
            for name, value in indicators.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        key = f"indicator_{name}_{sub_key}".lower()
                        normalised.setdefault(key, sub_value)
                else:
                    key = f"indicator_{name}".lower()
                    normalised.setdefault(key, value)

        return normalised


__all__ = ["AlertContextCache"]
