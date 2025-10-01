from __future__ import annotations

import asyncio
import hmac
import json
import math
from collections.abc import AsyncIterator
from datetime import datetime, timezone
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
from fastapi.responses import StreamingResponse

from ..adapters import BinanceMarketConnector, IBKRMarketConnector
from .config import Settings, get_settings
from .database import session_scope
from .persistence import persist_ticks
from .schemas import MarketContextSnapshot, MarketStreamEvent, PersistedTick, TradingViewSignal
from providers.limits import PairLimit, build_orderbook, build_quote, get_pair_limit
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


def _build_market_context(limit: PairLimit) -> MarketContextSnapshot:
    quote = build_quote(limit)
    orderbook = build_orderbook(limit)
    total_bid_volume = sum(level.size for level in orderbook.bids)
    total_ask_volume = sum(level.size for level in orderbook.asks)
    total_volume = total_bid_volume + total_ask_volume
    moving_average = quote.mid * 0.995
    indicators = {
        "moving_average": moving_average,
        "moving_average_slow": quote.mid * 0.985,
        "rsi": 50.0 + min(45.0, limit.tick_size * orderbook.depth),
    }
    return MarketContextSnapshot(
        symbol=limit.symbol,
        venue=limit.venue,
        price=quote.mid,
        bid=quote.bid,
        ask=quote.ask,
        spread_bps=quote.spread_bps,
        volume=total_volume,
        total_bid_volume=total_bid_volume,
        total_ask_volume=total_ask_volume,
        indicators=indicators,
        timestamp=quote.timestamp,
    )


def _stream_payload(limit: PairLimit, sequence: int, context: MarketContextSnapshot) -> MarketStreamEvent:
    base_price = context.price
    variation = math.sin(sequence / 5.0) * limit.tick_size
    price = base_price + variation
    bid = price - (limit.tick_size / 2)
    ask = price + (limit.tick_size / 2)
    depth = max(1, limit.depth_levels)
    volume_multiplier = 1.0 + (sequence % depth) / depth
    volume = limit.max_order_size * volume_multiplier
    metadata = {
        "sequence": sequence,
        "moving_average": context.indicators.get("moving_average", context.price),
    }
    return MarketStreamEvent(
        price=price,
        bid=bid,
        ask=ask,
        volume=volume,
        metadata=metadata,
        timestamp=datetime.now(timezone.utc),
    )


async def _event_generator(limit: PairLimit, *, max_events: int | None = None) -> AsyncIterator[str]:
    context = _build_market_context(limit)
    sequence = 0
    emitted = 0
    try:
        while True:
            if max_events is not None and emitted >= max_events:
                break
            event = _stream_payload(limit, sequence, context)
            payload = json.dumps(event.model_dump(mode="json")) + "\n"
            yield payload
            sequence += 1
            emitted += 1
            if max_events is None or emitted < max_events:
                await asyncio.sleep(0.1)
    except asyncio.CancelledError:  # pragma: no cover - cancellation during disconnect
        return


@app.get(
    "/symbols/{symbol}/context",
    response_model=MarketContextSnapshot,
    tags=["context"],
)
async def get_symbol_context(
    symbol: str,
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
) -> MarketContextSnapshot:
    limit = get_pair_limit(venue, symbol.upper())
    if limit is None:
        raise HTTPException(status_code=404, detail="Unsupported trading pair")
    return _build_market_context(limit)


@app.get("/streaming/{symbol}", tags=["streaming"])
async def stream_symbol_updates(
    symbol: str,
    venue: ExecutionVenue = Query(ExecutionVenue.BINANCE_SPOT, description="Market data venue"),
    max_events: int | None = Query(
        default=None,
        ge=1,
        le=1_000,
        description="Optional cap on the number of streamed events",
    ),
) -> StreamingResponse:
    limit = get_pair_limit(venue, symbol.upper())
    if limit is None:
        raise HTTPException(status_code=404, detail="Unsupported trading pair")
    generator = _event_generator(limit, max_events=max_events)
    return StreamingResponse(generator, media_type="application/x-ndjson")


__all__ = ["app", "get_binance_adapter", "get_ibkr_adapter"]
