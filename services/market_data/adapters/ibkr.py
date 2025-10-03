from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable, List

from ib_async.ib import IB

from libs.connectors import MarketConnector

from .rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


class IBKRMarketConnector(MarketConnector):
    """Adapter that wraps the asynchronous interface exposed by ``ib_async``."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        client_id: int,
        ib: IB | None = None,
        request_rate: int | None = None,
        request_interval_seconds: float | None = None,
        reconnect_delay: float = 2.0,
    ) -> None:
        self._ib = ib or IB()
        self._host = host
        self._port = port
        self._client_id = client_id
        rate = request_rate or self._ib.MaxRequests
        interval = request_interval_seconds or self._ib.RequestsInterval
        self._rate_limiter = AsyncRateLimiter(rate, interval)
        self._reconnect_delay = reconnect_delay
        self._lock = asyncio.Lock()

    async def ensure_connected(self) -> None:
        async with self._lock:
            if self._ib.isConnected():
                return
            logger.info("Connecting to IBKR gateway %s:%s", self._host, self._port)
            await self._ib.connectAsync(self._host, self._port, clientId=self._client_id)

    async def fetch_ohlcv(
        self,
        contract: Any,
        *,
        end: Any,
        duration: str,
        bar_size: str,
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        format_date: int = 1,
    ) -> Iterable[dict[str, Any]]:
        await self.ensure_connected()
        await self._rate_limiter.acquire()
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=format_date,
        )
        normalized: list[dict[str, Any]] = []
        for bar in bars:
            bar_time = getattr(bar, "date", None)
            if isinstance(bar_time, (int, float)):
                timestamp = datetime.fromtimestamp(float(bar_time), tz=timezone.utc)
            elif isinstance(bar_time, str):
                try:
                    timestamp = datetime.strptime(bar_time, "%Y%m%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    timestamp = datetime.fromtimestamp(0, tz=timezone.utc)
            elif isinstance(bar_time, datetime):
                timestamp = bar_time if bar_time.tzinfo else bar_time.replace(tzinfo=timezone.utc)
            else:
                timestamp = datetime.fromtimestamp(0, tz=timezone.utc)

            normalized.append(
                {
                    "timestamp": timestamp,
                    "open": float(getattr(bar, "open", 0.0)),
                    "high": float(getattr(bar, "high", 0.0)),
                    "low": float(getattr(bar, "low", 0.0)),
                    "close": float(getattr(bar, "close", 0.0)),
                    "volume": float(getattr(bar, "volume", 0.0)),
                    "bar_count": int(getattr(bar, "barCount", 0)),
                    "average": float(getattr(bar, "average", 0.0)),
                }
            )

        return normalized

    async def stream_trades(self, contract: Any) -> AsyncIterator[Any]:
        while True:
            try:
                await self.ensure_connected()
                try:
                    self._ib.reqMktData(contract)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("IBKR market data request failed: %s", exc)
                    await self._handle_disconnect()
                    await asyncio.sleep(self._reconnect_delay)
                    continue

                async for tickers in self._ib.pendingTickersEvent.aiter():
                    ticker_iterable = tickers if isinstance(tickers, (list, tuple)) else (tickers,)
                    for ticker in ticker_iterable:
                        if getattr(ticker, "contract", None) == contract:
                            yield ticker
            except Exception as exc:  # noqa: BLE001
                logger.warning("IBKR tick stream error: %s", exc)
                await self._handle_disconnect()
                await asyncio.sleep(self._reconnect_delay)
            finally:
                try:
                    self._ib.cancelMktData(contract)
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to cancel market data cleanly", exc_info=True)

    async def _handle_disconnect(self) -> None:
        try:
            self._ib.disconnect()
        finally:
            await asyncio.sleep(0)

    async def list_symbols(self, pattern: str, *, limit: int | None = None) -> List[dict[str, Any]]:
        if not pattern:
            raise ValueError("pattern must be provided for IBKR symbol search")

        await self.ensure_connected()
        await self._rate_limiter.acquire()
        matches = await self._ib.reqMatchingSymbolsAsync(pattern)

        symbols: list[dict[str, Any]] = []
        for match in matches:
            summary = getattr(match, "contract", getattr(match, "summary", None))
            symbol = getattr(summary, "symbol", None)
            symbols.append(
                {
                    "symbol": symbol,
                    "description": getattr(summary, "description", None),
                    "currency": getattr(summary, "currency", None),
                    "exchange": getattr(summary, "exchange", None),
                    "security_type": getattr(summary, "secType", None),
                }
            )

        if limit is not None:
            symbols = symbols[:limit]
        return symbols

    async def fetch_order_book(self, contract: Any) -> dict[str, Any]:
        await self.ensure_connected()
        await self._rate_limiter.acquire()
        ticker = await self._ib.reqMktDataAsync(contract, "", False, False, None)
        bids = []
        asks = []
        bid = getattr(ticker, "bid", None)
        bid_size = getattr(ticker, "bidSize", None)
        ask = getattr(ticker, "ask", None)
        ask_size = getattr(ticker, "askSize", None)
        if bid is not None:
            bids.append({"price": float(bid), "size": float(bid_size or 0.0)})
        if ask is not None:
            asks.append({"price": float(ask), "size": float(ask_size or 0.0)})

        return {
            "bids": bids,
            "asks": asks,
            "timestamp": datetime.now(timezone.utc),
        }
