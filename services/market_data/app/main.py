from __future__ import annotations

import hmac
import json
from hashlib import sha256

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
)

from ..adapters import BinanceMarketConnector, IBKRMarketConnector
from .config import Settings, get_settings
from .database import session_scope
from .persistence import persist_ticks
from .schemas import PersistedTick, TradingViewSignal
from providers.limits import build_orderbook, build_quote, get_pair_limit
from schemas.market import ExecutionVenue, OrderBookSnapshot, Quote
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

configure_logging("market-data")

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


@app.get("/spot/{symbol}", response_model=Quote, tags=["quotes"])
async def get_spot_quote(
    symbol: str,
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
) -> Quote:
    limit = get_pair_limit(venue, symbol.upper())
    if limit is None:
        raise HTTPException(status_code=404, detail="Unsupported trading pair")
    return build_quote(limit)


@app.get("/orderbook/{symbol}", response_model=OrderBookSnapshot, tags=["orderbook"])
async def get_orderbook(
    symbol: str,
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
) -> OrderBookSnapshot:
    limit = get_pair_limit(venue, symbol.upper())
    if limit is None:
        raise HTTPException(status_code=404, detail="Unsupported trading pair")
    return build_orderbook(limit)


__all__ = ["app", "get_binance_adapter", "get_ibkr_adapter"]
