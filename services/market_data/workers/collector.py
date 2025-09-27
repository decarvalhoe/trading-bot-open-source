from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping

from sqlalchemy.orm import Session

from ..adapters import BinanceMarketDataAdapter, IBKRMarketDataAdapter
from ..app.persistence import persist_ohlcv, persist_ticks
from ..app.schemas import PersistedBar, PersistedTick


class MarketDataCollector:
    """Coordinates ingestion from upstream adapters into the persistence layer."""

    def __init__(
        self,
        *,
        binance: BinanceMarketDataAdapter,
        ibkr: IBKRMarketDataAdapter,
        session_factory: Callable[[], AbstractContextManager[Session]],
    ) -> None:
        self._binance = binance
        self._ibkr = ibkr
        self._session_factory = session_factory
        self._stop_event = asyncio.Event()

    async def collect_binance_ohlcv(self, symbol: str, interval: str) -> None:
        while not self._stop_event.is_set():
            bars = await self._binance.fetch_ohlcv(symbol, interval)
            rows = [
                PersistedBar(
                    exchange="binance",
                    symbol=symbol,
                    interval=interval,
                    timestamp=datetime.fromtimestamp(bar["open_time"] / 1000, tz=timezone.utc),
                    open=bar["open"],
                    high=bar["high"],
                    low=bar["low"],
                    close=bar["close"],
                    volume=bar["volume"],
                    quote_volume=bar.get("quote_asset_volume"),
                    trades=bar.get("number_of_trades"),
                    extra={"close_time": bar["close_time"]},
                )
                for bar in bars
            ]
            self._persist_bars(rows)
            await asyncio.sleep(60)

    async def stream_ibkr_ticks(self, contract) -> None:
        async for ticker in self._ibkr.stream_ticks(contract):
            if self._stop_event.is_set():
                break
            row = PersistedTick(
                exchange="ibkr",
                symbol=getattr(ticker.contract, "symbol", "unknown"),
                source="ibkr",
                timestamp=getattr(ticker, "time", datetime.now(timezone.utc)),
                price=getattr(ticker, "last", getattr(ticker, "marketPrice", 0.0)),
                size=getattr(ticker, "lastSize", getattr(ticker, "marketSize", 0.0)),
                side=None,
                extra={"bid": getattr(ticker, "bid", None), "ask": getattr(ticker, "ask", None)},
            )
            self._persist_ticks([row])

    def stop(self) -> None:
        self._stop_event.set()

    def _persist_bars(self, bars: Iterable[PersistedBar]) -> None:
        payload: list[Mapping[str, object]] = [
            {
                "exchange": bar.exchange,
                "symbol": bar.symbol,
                "interval": bar.interval,
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "quote_volume": bar.quote_volume,
                "trades": bar.trades,
                "extra": bar.extra,
            }
            for bar in bars
        ]
        if not payload:
            return
        with self._session_factory() as session:
            persist_ohlcv(session, payload)

    def _persist_ticks(self, ticks: Iterable[PersistedTick]) -> None:
        payload: list[Mapping[str, object]] = [
            {
                "exchange": tick.exchange,
                "symbol": tick.symbol,
                "source": tick.source,
                "timestamp": tick.timestamp,
                "price": tick.price,
                "size": tick.size,
                "side": tick.side,
                "extra": tick.extra,
            }
            for tick in ticks
        ]
        if not payload:
            return
        with self._session_factory() as session:
            persist_ticks(session, payload)
