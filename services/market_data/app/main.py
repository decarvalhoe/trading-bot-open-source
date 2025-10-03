from __future__ import annotations

import asyncio
import hmac
import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Awaitable, Callable, TypeVar

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from schemas.market import ExecutionVenue

from ..adapters import BinanceMarketConnector, IBKRMarketConnector
from .config import Settings, get_settings
from .database import session_scope
from .persistence import persist_ticks
from .schemas import (
    HistoricalCandle,
    HistoryResponse,
    MarketSymbol,
    PersistedTick,
    QuoteLevel,
    QuoteSnapshot,
    SymbolListResponse,
    TradingViewSignal,
)

configure_logging("market-data")
logger = logging.getLogger(__name__)

app = FastAPI(title="Market Data Service", version="0.1.0")
app.add_middleware(RequestContextMiddleware, service_name="market-data")
setup_metrics(app, service_name="market-data")


def get_binance_adapter(settings: Settings = Depends(get_settings)) -> BinanceMarketConnector:
    return BinanceMarketConnector(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
    )


def get_ibkr_adapter(settings: Settings = Depends(get_settings)) -> IBKRMarketConnector:
    return IBKRMarketConnector(
        host=settings.ibkr_host,
        port=settings.ibkr_port,
        client_id=settings.ibkr_client_id,
    )


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _resolve_connector(
    venue: ExecutionVenue,
    *,
    binance: BinanceMarketConnector,
    ibkr: IBKRMarketConnector,
) -> BinanceMarketConnector | IBKRMarketConnector:
    if venue == ExecutionVenue.BINANCE_SPOT:
        return binance
    if venue == ExecutionVenue.IBKR_PAPER:
        return ibkr
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported venue")


async def _persist_tradingview_tick(signal: TradingViewSignal) -> None:
    tick = PersistedTick(
        exchange=signal.exchange,
        symbol=signal.symbol,
        source="tradingview",
        timestamp=signal.timestamp,
        price=signal.price,
        size=signal.size,
        side=signal.direction,
        extra={"strategy": signal.strategy, **signal.metadata},
    )
    with session_scope() as session:
        persist_ticks(
            session,
            [
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
            ],
        )


@app.post("/webhooks/tradingview", status_code=202)
async def tradingview_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    signature: str = Header(..., alias="X-Signature"),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    body = await request.body()
    expected = hmac.new(
        settings.tradingview_hmac_secret.encode("utf-8"),
        body,
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:  # noqa: PERF203
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    signal = TradingViewSignal(**payload)
    background_tasks.add_task(_persist_tradingview_tick, signal)
    return {"status": "accepted"}



T = TypeVar("T")


async def _call_with_retries(
    operation: Callable[[], Awaitable[T]], *, attempts: int = 2, delay: float = 0.1
) -> T:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == attempts:
                break
            logger.warning("Retrying market data operation after error: %s", exc)
            await asyncio.sleep(delay * attempt)
    assert last_exc is not None
    raise last_exc


@app.get("/market-data/symbols", response_model=SymbolListResponse, tags=["reference"])
async def list_symbols(
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
    search: str | None = Query(None, min_length=1, description="Optional case-insensitive filter"),
    limit: int = Query(100, ge=1, le=1_000, description="Maximum number of symbols to return"),
    binance: BinanceMarketConnector = Depends(get_binance_adapter),
    ibkr: IBKRMarketConnector = Depends(get_ibkr_adapter),
) -> SymbolListResponse:
    connector = _resolve_connector(venue, binance=binance, ibkr=ibkr)

    async def _load() -> list[dict[str, Any]]:
        if hasattr(connector, "list_symbols"):
            return await connector.list_symbols(search=search, limit=limit)
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not supported")

    try:
        records = await _call_with_retries(_load)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load symbols for venue %s", venue)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream error") from exc

    symbols = [MarketSymbol(**record) for record in records[:limit]]
    return SymbolListResponse(venue=venue, symbols=symbols)


@app.get(
    "/market-data/quotes/{symbol}",
    response_model=QuoteSnapshot,
    tags=["quotes"],
)
async def get_quote(
    symbol: str,
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
    binance: BinanceMarketConnector = Depends(get_binance_adapter),
    ibkr: IBKRMarketConnector = Depends(get_ibkr_adapter),
) -> QuoteSnapshot:
    connector = _resolve_connector(venue, binance=binance, ibkr=ibkr)

    async def _load() -> dict[str, Any]:
        target_symbol = symbol.upper() if venue == ExecutionVenue.BINANCE_SPOT else symbol
        if hasattr(connector, "fetch_order_book"):
            return await connector.fetch_order_book(target_symbol)
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not supported")

    try:
        book = await _call_with_retries(_load)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch quote for %s on %s", symbol, venue)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream error") from exc

    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bid = QuoteLevel(**bids[0]) if bids else None
    ask = QuoteLevel(**asks[0]) if asks else None

    mid = None
    spread_bps = None
    if bid and ask and bid.price and ask.price:
        mid = (bid.price + ask.price) / 2
        spread = ask.price - bid.price
        spread_bps = (spread / mid) * 10_000 if mid else None

    timestamp = book.get("timestamp", datetime.now(timezone.utc))
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    return QuoteSnapshot(
        venue=venue,
        symbol=symbol.upper(),
        bid=bid,
        ask=ask,
        mid=mid,
        spread_bps=spread_bps,
        last_update=timestamp,
    )


@app.get(
    "/market-data/history/{symbol}",
    response_model=HistoryResponse,
    tags=["history"],
)
async def get_history(
    symbol: str,
    interval: str = Query(..., description="Exchange specific interval, e.g. 1m"),
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
    limit: int = Query(200, ge=1, le=1_000),
    binance: BinanceMarketConnector = Depends(get_binance_adapter),
    ibkr: IBKRMarketConnector = Depends(get_ibkr_adapter),
) -> HistoryResponse:
    connector = _resolve_connector(venue, binance=binance, ibkr=ibkr)

    async def _load() -> list[dict[str, Any]]:
        if venue == ExecutionVenue.BINANCE_SPOT:
            return list(await connector.fetch_ohlcv(symbol.upper(), interval, limit=limit))

        bars = await connector.fetch_ohlcv(
            symbol,
            end="",
            duration=interval,
            bar_size=interval,
        )
        return list(bars)

    try:
        candles = await _call_with_retries(_load)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load historical data for %s on %s", symbol, venue)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Upstream error") from exc

    normalized: list[HistoricalCandle] = []
    for candle in candles:
        if isinstance(candle, HistoricalCandle):
            normalized.append(candle)
            continue

        if isinstance(candle, dict):
            data = dict(candle)
        else:
            data = candle.__dict__ if hasattr(candle, "__dict__") else {}

        open_time = data.get("open_time") or data.get("timestamp")
        close_time = data.get("close_time") or data.get("timestamp")
        data.setdefault("open_time", open_time)
        data.setdefault("close_time", close_time)
        if "trades" not in data:
            trades = data.get("number_of_trades") or data.get("bar_count")
            if trades is not None:
                data["trades"] = trades
        if "quote_volume" not in data and data.get("quote_asset_volume") is not None:
            data["quote_volume"] = data["quote_asset_volume"]

        normalized.append(HistoricalCandle(**data))

    return HistoryResponse(
        venue=venue,
        symbol=symbol.upper(),
        interval=interval,
        candles=normalized[:limit],
    )


__all__ = ["app", "get_binance_adapter", "get_ibkr_adapter"]
