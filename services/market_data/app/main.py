from __future__ import annotations

import hmac
import json
from hashlib import sha256

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request

from ..adapters import BinanceMarketDataAdapter, IBKRMarketDataAdapter
from .config import Settings, get_settings
from .database import session_scope
from .persistence import persist_ticks
from .schemas import PersistedTick, TradingViewSignal

app = FastAPI(title="Market Data Service", version="0.1.0")


def get_binance_adapter(settings: Settings = Depends(get_settings)) -> BinanceMarketDataAdapter:
    return BinanceMarketDataAdapter(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
    )


def get_ibkr_adapter(settings: Settings = Depends(get_settings)) -> IBKRMarketDataAdapter:
    return IBKRMarketDataAdapter(
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


__all__ = ["app", "get_binance_adapter", "get_ibkr_adapter"]
