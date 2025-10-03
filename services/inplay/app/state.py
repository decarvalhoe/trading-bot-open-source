from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, Iterable, Tuple
from urllib.parse import quote

from .schemas import SessionName, StrategySetup, SymbolSetups, TickPayload, WatchlistSnapshot


class WatchlistState:
    def __init__(self, watchlist_id: str, symbols: Iterable[str]):
        self.id = watchlist_id
        self.symbols = list(symbols)
        self._setups: dict[str, dict[Tuple[str, SessionName], StrategySetup]] = {}
        self.updated_at: datetime | None = None

    def apply_setup(self, setup: StrategySetup) -> bool:
        if setup.symbol not in self.symbols:
            return False
        symbol_setups = self._setups.setdefault(setup.symbol, {})
        symbol_setups[(setup.strategy, setup.session)] = setup
        self.updated_at = setup.updated_at
        return True

    def snapshot(self, session: SessionName | None = None) -> WatchlistSnapshot:
        symbols: list[SymbolSetups] = []
        for symbol in self.symbols:
            setups = list(self._setups.get(symbol, {}).values())
            if session is not None:
                setups = [item for item in setups if item.session == session]
            setups.sort(key=lambda item: item.updated_at, reverse=True)
            symbols.append(SymbolSetups(symbol=symbol, setups=setups))
        return WatchlistSnapshot(id=self.id, symbols=symbols, updated_at=self.updated_at)

    def iter_setups(self, symbol: str | None = None) -> Iterable[StrategySetup]:
        if symbol is not None:
            yield from self._setups.get(symbol, {}).values()
            return
        for setups in self._setups.values():
            yield from setups.values()


class InPlayState:
    def __init__(self, watchlists: Dict[str, Iterable[str]]):
        self._lock = asyncio.Lock()
        self._watchlists: dict[str, WatchlistState] = {
            watchlist_id: WatchlistState(watchlist_id, symbols)
            for watchlist_id, symbols in watchlists.items()
        }

    async def apply_tick(self, payload: TickPayload) -> list[WatchlistSnapshot]:
        report_url = payload.report_url
        if not report_url:
            encoded_symbol = quote(payload.symbol, safe="")
            encoded_strategy = quote(payload.strategy, safe="")
            report_url = f"/inplay/setups/{encoded_symbol}/{encoded_strategy}"

        setup = StrategySetup(
            symbol=payload.symbol,
            strategy=payload.strategy,
            entry=payload.entry,
            target=payload.target,
            stop=payload.stop,
            probability=payload.probability,
            status=payload.status,
            session=payload.session,
            updated_at=payload.received_at,
            report_url=report_url,
        )
        async with self._lock:
            updated: list[WatchlistSnapshot] = []
            target_watchlists = payload.watchlists or list(self._watchlists.keys())
            for watchlist_id in target_watchlists:
                watchlist = self._watchlists.get(watchlist_id)
                if watchlist and watchlist.apply_setup(setup):
                    updated.append(watchlist.snapshot())
            return updated

    async def get_strategy_setup(self, symbol: str, strategy: str) -> StrategySetup | None:
        async with self._lock:
            candidates: list[StrategySetup] = []
            for watchlist in self._watchlists.values():
                for item in watchlist.iter_setups(symbol=symbol):
                    if item.strategy.lower() == strategy.lower():
                        candidates.append(item)
            if not candidates:
                return None
            candidates.sort(key=lambda item: item.updated_at, reverse=True)
            return candidates[0]

    async def get_watchlist(
        self, watchlist_id: str, session: SessionName | None = None
    ) -> WatchlistSnapshot:
        async with self._lock:
            if watchlist_id not in self._watchlists:
                raise KeyError(watchlist_id)
            return self._watchlists[watchlist_id].snapshot(session=session)

    async def list_watchlists(self) -> list[WatchlistSnapshot]:
        async with self._lock:
            return [watchlist.snapshot() for watchlist in self._watchlists.values()]

    async def register_watchlist(self, watchlist_id: str, symbols: Iterable[str]) -> None:
        async with self._lock:
            self._watchlists[watchlist_id] = WatchlistState(watchlist_id, symbols)
