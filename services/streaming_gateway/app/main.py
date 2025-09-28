"""Entry point for the streaming gateway FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

from .config import get_settings
from .rate_limit import RateLimiter, rate_limit_middleware
from .routers import oauth, overlays, sessions, tradingview, websocket

configure_logging("streaming-gateway")

settings = get_settings()

app = FastAPI(title="Streaming Gateway", version="0.1.0")
install_entitlements_middleware(app, required_capabilities=["can.stream"])
app.add_middleware(RequestContextMiddleware, service_name="streaming-gateway")
setup_metrics(app, service_name="streaming-gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
app.middleware("http")(rate_limit_middleware)

app.include_router(oauth.router)
app.include_router(overlays.router)
app.include_router(sessions.router)
app.include_router(tradingview.router)
app.include_router(websocket.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
