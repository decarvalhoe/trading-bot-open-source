from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Iterable

from .schemas import StrategySetup, SymbolSetups, TickPayload, WatchlistSnapshot


class WatchlistState:
    def __init__(self, watchlist_id: str, symbols: Iterable[str]):
        self.id = watchlist_id
        self.symbols = list(symbols)
        self._setups: dict[str, dict[str, StrategySetup]] = {}
        self.updated_at: datetime | None = None

    def apply_setup(self, setup: StrategySetup) -> bool:
        if setup.symbol not in self.symbols:
            return False
        symbol_setups = self._setups.setdefault(setup.symbol, {})
        symbol_setups[setup.strategy] = setup
        self.updated_at = setup.updated_at
        return True

    def snapshot(self) -> WatchlistSnapshot:
        symbols: list[SymbolSetups] = []
        for symbol in self.symbols:
            setups = list(self._setups.get(symbol, {}).values())
            setups.sort(key=lambda item: item.updated_at, reverse=True)
            symbols.append(SymbolSetups(symbol=symbol, setups=setups))
        return WatchlistSnapshot(id=self.id, symbols=symbols, updated_at=self.updated_at)


class InPlayState:
    def __init__(self, watchlists: Dict[str, Iterable[str]]):
        self._lock = asyncio.Lock()
        self._watchlists: dict[str, WatchlistState] = {
            watchlist_id: WatchlistState(watchlist_id, symbols)
            for watchlist_id, symbols in watchlists.items()
        }

    async def apply_tick(self, payload: TickPayload) -> list[WatchlistSnapshot]:
        setup = StrategySetup(
            symbol=payload.symbol,
            strategy=payload.strategy,
            entry=payload.entry,
            target=payload.target,
            stop=payload.stop,
            probability=payload.probability,
            updated_at=payload.received_at,
        )
        async with self._lock:
            updated: list[WatchlistSnapshot] = []
            target_watchlists = payload.watchlists or list(self._watchlists.keys())
            for watchlist_id in target_watchlists:
                watchlist = self._watchlists.get(watchlist_id)
                if watchlist and watchlist.apply_setup(setup):
                    updated.append(watchlist.snapshot())
            return updated

    async def get_watchlist(self, watchlist_id: str) -> WatchlistSnapshot:
        async with self._lock:
            if watchlist_id not in self._watchlists:
                raise KeyError(watchlist_id)
            return self._watchlists[watchlist_id].snapshot()

    async def list_watchlists(self) -> list[WatchlistSnapshot]:
        async with self._lock:
            return [watchlist.snapshot() for watchlist in self._watchlists.values()]

    async def register_watchlist(self, watchlist_id: str, symbols: Iterable[str]) -> None:
        async with self._lock:
            self._watchlists[watchlist_id] = WatchlistState(watchlist_id, symbols)
