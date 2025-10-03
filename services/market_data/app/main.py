from __future__ import annotations

import asyncio
import hmac
import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, AsyncIterator, Awaitable, Callable, Iterable, TypeVar

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.websockets import WebSocketState

from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from schemas.market import ExecutionVenue

import httpx

from ..adapters import (
    BinanceMarketConnector,
    DTCAdapter,
    DTCConfig,
    IBKRMarketConnector,
    TopStepAdapter,
)
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


_dtc_adapter: DTCAdapter | None = None
_dtc_adapter_lock = asyncio.Lock()


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


async def get_dtc_adapter(settings: Settings = Depends(get_settings)) -> DTCAdapter | None:
    if not settings.dtc_host or not settings.dtc_port:
        return None

    global _dtc_adapter
    if _dtc_adapter is None:
        async with _dtc_adapter_lock:
            if _dtc_adapter is None:
                config = DTCConfig(
                    host=settings.dtc_host,
                    port=settings.dtc_port,
                    client_user_id=settings.dtc_user or "",
                    client_password=settings.dtc_password or "",
                    client_name=settings.dtc_client_name,
                    heartbeat_interval=settings.dtc_heartbeat_interval,
                    default_exchange=settings.dtc_default_exchange,
                )
                _dtc_adapter = DTCAdapter(config)
    return _dtc_adapter


async def get_topstep_adapter(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[TopStepAdapter]:
    if not settings.topstep_client_id or not settings.topstep_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TopStep credentials are not configured",
        )
        _dtc_adapter = DTCAdapter(config)
    return _dtc_adapter


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("shutdown")
async def _shutdown_dtc() -> None:
    global _dtc_adapter
    if _dtc_adapter is not None:
        await _dtc_adapter.close()
        _dtc_adapter = None


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


def _tick_from_tradingview_signal(signal: TradingViewSignal) -> PersistedTick:
    return PersistedTick(
        exchange=signal.exchange,
        symbol=signal.symbol,
        source="tradingview",
        timestamp=signal.timestamp,
        price=signal.price,
        size=signal.size,
        side=signal.direction,
        extra={"strategy": signal.strategy, **signal.metadata},
    )


def _persist_tick_record(tick: PersistedTick) -> None:
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
    if dtc is not None:
        try:
            await dtc.publish_ticks([tick])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to forward TradingView tick to DTC: %s", exc)


async def publish_ticks_to_dtc(dtc: DTCAdapter, ticks: Iterable[PersistedTick]) -> None:
    payload = [
        {
            "exchange": tick.exchange,
            "symbol": tick.symbol,
            "source": tick.source,
            "timestamp": tick.timestamp,
            "price": tick.price,
            "size": tick.size,
            "side": tick.side,
        }
        for tick in ticks
    ]
    if payload:
        await dtc.publish_ticks(payload)


@app.post("/webhooks/tradingview", status_code=202)
async def tradingview_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    signature: str = Header(..., alias="X-Signature"),
    settings: Settings = Depends(get_settings),
    dtc: DTCAdapter | None = Depends(get_dtc_adapter),
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
    tick = _tick_from_tradingview_signal(signal)
    background_tasks.add_task(_persist_tick_record, tick)
    if dtc is not None:
        await publish_ticks_to_dtc(dtc, [tick])
    return {"status": "accepted"}



T = TypeVar("T")

_STREAM_RETRY_INITIAL_DELAY = 0.5
_STREAM_RETRY_MAX_DELAY = 8.0


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


async def _aclose_stream(stream: Any) -> None:
    """Best-effort close helper for async generators returned by connectors."""

    aclose = getattr(stream, "aclose", None)
    if aclose is None:
        return

    try:
        result = aclose()
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001
        logger.debug("Failed to close trade stream cleanly", exc_info=True)


async def _forward_trade_stream(
    websocket: WebSocket,
    connector: BinanceMarketConnector | IBKRMarketConnector,
    stream_symbol: str,
) -> None:
    delay = _STREAM_RETRY_INITIAL_DELAY
    while True:
        stream = connector.stream_trades(stream_symbol)
        try:
            async for trade in stream:
                payload = jsonable_encoder(trade)
                await websocket.send_json(payload)
                delay = _STREAM_RETRY_INITIAL_DELAY
        except RuntimeError as exc:
            if websocket.application_state != WebSocketState.CONNECTED:
                raise WebSocketDisconnect(code=1006) from exc
            raise
        except (asyncio.CancelledError, WebSocketDisconnect):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Trade stream bridge error for %s: %s", stream_symbol, exc
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, _STREAM_RETRY_MAX_DELAY)
        finally:
            await _aclose_stream(stream)


async def _drain_websocket(websocket: WebSocket) -> None:
    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        return


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


@app.websocket("/market-data/stream")
async def stream_market_data(
    websocket: WebSocket,
    symbol: str,
    venue: ExecutionVenue = Query(
        ExecutionVenue.BINANCE_SPOT, description="Market data venue"
    ),
    binance: BinanceMarketConnector = Depends(get_binance_adapter),
    ibkr: IBKRMarketConnector = Depends(get_ibkr_adapter),
) -> None:
    await websocket.accept()

    connector = _resolve_connector(venue, binance=binance, ibkr=ibkr)
    stream_symbol = symbol.upper() if venue == ExecutionVenue.BINANCE_SPOT else symbol

    forward_task = asyncio.create_task(
        _forward_trade_stream(websocket, connector, stream_symbol)
    )
    listener_task = asyncio.create_task(_drain_websocket(websocket))
    tasks = {forward_task, listener_task}

    try:
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        if forward_task in done:
            exc = forward_task.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                logger.exception(
                    "Market data stream failed for %s on %s", symbol, venue
                )
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.close(code=1011)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@app.get(
    "/market-data/topstep/accounts/{account_id}/metrics",
    tags=["topstep"],
)
async def get_topstep_metrics(
    account_id: str,
    adapter: TopStepAdapter = Depends(get_topstep_adapter),
) -> dict[str, Any]:
    try:
        metrics = await adapter.get_account_metrics(account_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch TopStep metrics for %s", account_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TopStep upstream error",
        ) from exc

    return {"account_id": account_id, "metrics": metrics}


@app.get(
    "/market-data/topstep/accounts/{account_id}/performance",
    tags=["topstep"],
)
async def get_topstep_performance(
    account_id: str,
    start: str | None = Query(None, description="Start date (ISO 8601)"),
    end: str | None = Query(None, description="End date (ISO 8601)"),
    adapter: TopStepAdapter = Depends(get_topstep_adapter),
) -> dict[str, Any]:
    try:
        performance = await adapter.get_performance_history(
            account_id,
            start=start,
            end=end,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch TopStep performance for %s", account_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TopStep upstream error",
        ) from exc

    payload: dict[str, Any] = {"account_id": account_id, "performance": performance}
    if start is not None:
        payload["start"] = start
    if end is not None:
        payload["end"] = end
    return payload


@app.get(
    "/market-data/topstep/accounts/{account_id}/risk-rules",
    tags=["topstep"],
)
async def get_topstep_risk_rules(
    account_id: str,
    adapter: TopStepAdapter = Depends(get_topstep_adapter),
) -> dict[str, Any]:
    try:
        risk_rules = await adapter.get_risk_rules(account_id)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch TopStep risk rules for %s", account_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TopStep upstream error",
        ) from exc

    return {"account_id": account_id, "risk_rules": risk_rules}


__all__ = ["app", "get_binance_adapter", "get_ibkr_adapter", "get_topstep_adapter"]
