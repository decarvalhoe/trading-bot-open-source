from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Iterable

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
    ) -> Iterable[Any]:
        await self.ensure_connected()
        await self._rate_limiter.acquire()
        return await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end,
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=format_date,
        )

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
