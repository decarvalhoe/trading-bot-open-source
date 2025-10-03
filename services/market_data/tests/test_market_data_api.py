from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi.testclient import TestClient

os.environ.setdefault("TRADINGVIEW_HMAC_SECRET", "test-secret")

from services.market_data.app.main import app, get_binance_adapter, get_ibkr_adapter  # noqa: E402
from schemas.market import ExecutionVenue  # noqa: E402


class _BaseConnector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((method, args, kwargs))


class BinanceConnectorFake(_BaseConnector):
    def __init__(self) -> None:
        super().__init__()
        self.order_book_attempts = 0

    async def list_symbols(self, *, search: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        self._record("list_symbols", search, limit)
        return [
            {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "status": "TRADING",
                "tick_size": 0.1,
                "lot_size": 0.001,
            }
        ]

    async def fetch_order_book(self, symbol: str) -> dict[str, Any]:
        self.order_book_attempts += 1
        self._record("fetch_order_book", symbol)
        if self.order_book_attempts == 1:
            raise RuntimeError("transient error")
        return {
            "bids": [{"price": 100.0, "size": 1.0}],
            "asks": [{"price": 101.0, "size": 2.0}],
            "timestamp": datetime.now(timezone.utc),
        }

    async def fetch_ohlcv(self, symbol: str, interval: str, *, limit: int = 500) -> list[dict[str, Any]]:
        self._record("fetch_ohlcv", symbol, interval, limit)
        now = datetime.now(timezone.utc)
        return [
            {
                "open_time": now,
                "close_time": now,
                "open": 99.0,
                "high": 105.0,
                "low": 95.0,
                "close": 100.5,
                "volume": 10.0,
                "trades": 5,
            }
        ]


class IBKRConnectorFake(_BaseConnector):
    async def list_symbols(self, *, search: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        self._record("list_symbols", search, limit)
        raise ValueError("pattern must be provided for IBKR symbol search")

    async def fetch_ohlcv(self, symbol: str, *, end: str, duration: str, bar_size: str) -> list[dict[str, Any]]:
        self._record("fetch_ohlcv", symbol, end, duration, bar_size)
        now = datetime.now(timezone.utc)
        return [
            {
                "timestamp": now,
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 2.0,
                "bar_count": 3,
            }
        ]

    async def fetch_order_book(self, symbol: str) -> dict[str, Any]:
        self._record("fetch_order_book", symbol)
        return {
            "bids": [{"price": 200.0, "size": 1.0}],
            "asks": [{"price": 201.0, "size": 1.5}],
            "timestamp": datetime.now(timezone.utc),
        }


def test_list_symbols_returns_payload() -> None:
    binance = BinanceConnectorFake()
    ibkr = IBKRConnectorFake()

    app.dependency_overrides[get_binance_adapter] = lambda: binance
    app.dependency_overrides[get_ibkr_adapter] = lambda: ibkr

    client = TestClient(app)
    try:
        response = client.get("/market-data/symbols", params={"limit": 1})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["venue"] == ExecutionVenue.BINANCE_SPOT.value
    assert payload["symbols"][0]["symbol"] == "BTCUSDT"
    assert binance.calls[0][0] == "list_symbols"


def test_quote_endpoint_retries_transient_failure() -> None:
    binance = BinanceConnectorFake()
    ibkr = IBKRConnectorFake()

    app.dependency_overrides[get_binance_adapter] = lambda: binance
    app.dependency_overrides[get_ibkr_adapter] = lambda: ibkr

    client = TestClient(app)
    try:
        response = client.get("/market-data/quotes/BTCUSDT")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert binance.order_book_attempts == 2
    assert payload["bid"]["price"] == 100.0
    assert payload["ask"]["price"] == 101.0


def test_history_endpoint_handles_ibkr_and_binance() -> None:
    binance = BinanceConnectorFake()
    ibkr = IBKRConnectorFake()

    app.dependency_overrides[get_binance_adapter] = lambda: binance
    app.dependency_overrides[get_ibkr_adapter] = lambda: ibkr

    client = TestClient(app)
    try:
        binance_response = client.get(
            "/market-data/history/BTCUSDT",
            params={"interval": "1m", "limit": 1},
        )
        ibkr_response = client.get(
            "/market-data/history/ES",
            params={
                "venue": ExecutionVenue.IBKR_PAPER.value,
                "interval": "1 D",
                "limit": 1,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert binance_response.status_code == 200
    assert binance_response.json()["candles"][0]["open"] == 99.0

    assert ibkr_response.status_code == 200
    assert ibkr_response.json()["candles"][0]["open"] == 10.0
    assert ibkr.calls[-1][0] == "fetch_ohlcv"


def test_ibkr_symbol_search_requires_pattern() -> None:
    binance = BinanceConnectorFake()
    ibkr = IBKRConnectorFake()

    app.dependency_overrides[get_binance_adapter] = lambda: binance
    app.dependency_overrides[get_ibkr_adapter] = lambda: ibkr

    client = TestClient(app)
    try:
        response = client.get(
            "/market-data/symbols",
            params={"venue": ExecutionVenue.IBKR_PAPER.value},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "pattern" in response.json()["detail"]


class StreamingConnectorStub(_BaseConnector):
    def __init__(self, sequences: list[list[Any]]) -> None:
        super().__init__()
        self._sequences = sequences
        self.stream_calls = 0
        self.stream_symbols: list[str] = []

    async def stream_trades(self, symbol: str) -> AsyncIterator[Any]:
        self.stream_calls += 1
        self.stream_symbols.append(symbol)
        index = self.stream_calls - 1
        sequence = self._sequences[index] if index < len(self._sequences) else []
        for item in sequence:
            await asyncio.sleep(0)
            if isinstance(item, Exception):
                raise item
            yield item
        while True:
            await asyncio.sleep(0.05)


def test_market_data_stream_forwards_trades() -> None:
    connector = StreamingConnectorStub(
        [[{"trade_id": 1, "price": 100.0}, {"trade_id": 2, "price": 101.5}]]
    )

    app.dependency_overrides[get_binance_adapter] = lambda: connector
    app.dependency_overrides[get_ibkr_adapter] = lambda: connector

    with TestClient(app) as client:
        with client.websocket_connect("/market-data/stream?symbol=BTCUSDT") as websocket:
            first = websocket.receive_json()
            second = websocket.receive_json()

    app.dependency_overrides.clear()

    assert first["trade_id"] == 1
    assert second["trade_id"] == 2
    assert connector.stream_calls == 1
    assert connector.stream_symbols == ["BTCUSDT"]


def test_market_data_stream_recovers_after_error() -> None:
    connector = StreamingConnectorStub(
        [[{"sequence": 1}, ConnectionError("stream dropped")], [{"sequence": 2}]]
    )

    app.dependency_overrides[get_binance_adapter] = lambda: connector
    app.dependency_overrides[get_ibkr_adapter] = lambda: connector

    with TestClient(app) as client:
        with client.websocket_connect(
            "/market-data/stream",
            params={"symbol": "ES", "venue": ExecutionVenue.IBKR_PAPER.value},
        ) as websocket:
            first = websocket.receive_json()
            second = websocket.receive_json()

    app.dependency_overrides.clear()

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert connector.stream_calls >= 2
    assert all(symbol == "ES" for symbol in connector.stream_symbols)
