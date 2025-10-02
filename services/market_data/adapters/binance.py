from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable, Dict, Iterable

from binance.spot import Spot
from binance.websocket.websocket_client import BinanceWebsocketClient

from libs.connectors import MarketConnector

from .rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


class BinanceMarketConnector(MarketConnector):
    """Adapter that exposes a coroutine-based interface over Binance's APIs."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        rest_client: Spot | None = None,
        websocket_client_factory: Callable[..., BinanceWebsocketClient] | None = None,
        request_rate: int = 1200,
        request_interval_seconds: float = 60.0,
        reconnect_delay: float = 2.0,
        stream_url: str = "wss://stream.binance.com:9443/ws",
    ) -> None:
        self._rest_client = rest_client or Spot(api_key=api_key, api_secret=api_secret)
        if websocket_client_factory is None:
            websocket_client_factory = lambda **kwargs: BinanceWebsocketClient(stream_url, **kwargs)
        self._websocket_factory = websocket_client_factory
        self._rate_limiter = AsyncRateLimiter(request_rate, request_interval_seconds)
        self._reconnect_delay = reconnect_delay
        self._stream_url = stream_url

    async def fetch_ohlcv(
        self, symbol: str, interval: str, *, limit: int = 500
    ) -> Iterable[Dict[str, Any]]:
        await self._rate_limiter.acquire()
        loop = asyncio.get_running_loop()
        raw_bars = await loop.run_in_executor(
            None, lambda: self._rest_client.klines(symbol=symbol, interval=interval, limit=limit)
        )
        return [
            {
                "open_time": bar[0],
                "open": float(bar[1]),
                "high": float(bar[2]),
                "low": float(bar[3]),
                "close": float(bar[4]),
                "volume": float(bar[5]),
                "close_time": bar[6],
                "quote_asset_volume": float(bar[7]),
                "number_of_trades": int(bar[8]),
            }
            for bar in raw_bars
        ]

    async def stream_trades(self, symbol: str) -> AsyncIterator[Dict[str, Any]]:
        stream_name = f"{symbol.lower()}@trade"
        while True:
            queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

            def _handle_message(*args: Any) -> None:
                message = args[-1] if args else {}
                if isinstance(message, (bytes, bytearray)):
                    payload: Any = json.loads(message.decode("utf-8"))
                elif isinstance(message, str):
                    payload = json.loads(message)
                else:
                    payload = message
                queue.put_nowait(("data", payload))

            def _handle_close(*_: Any) -> None:
                queue.put_nowait(("error", ConnectionError("stream closed")))

            def _handle_error(*args: Any) -> None:
                error = args[-1] if args else ConnectionError("unknown error")
                if not isinstance(error, Exception):
                    error = ConnectionError(str(error))
                queue.put_nowait(("error", error))

            ws_client = self._websocket_factory(
                stream_url=self._stream_url,
                on_message=_handle_message,
                on_close=_handle_close,
                on_error=_handle_error,
            )
            try:
                ws_client.subscribe(stream_name)
                while True:
                    kind, payload = await queue.get()
                    if kind == "data":
                        yield payload
                    else:
                        raise payload
            except Exception as exc:  # noqa: BLE001
                logger.warning("Binance trade stream error for %s: %s", symbol, exc)
                await asyncio.sleep(self._reconnect_delay)
            finally:
                try:
                    ws_client.stop()
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to stop Binance websocket cleanly", exc_info=True)
