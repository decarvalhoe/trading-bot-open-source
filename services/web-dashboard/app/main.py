"""Minimal dashboard service for monitoring trading activity."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .data import load_dashboard_context, load_portfolio_history


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Web Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

STREAMING_BASE_URL = os.getenv("WEB_DASHBOARD_STREAMING_BASE_URL", "http://localhost:8001/")
STREAMING_ROOM_ID = os.getenv("WEB_DASHBOARD_STREAMING_ROOM_ID", "public-room")
STREAMING_VIEWER_ID = os.getenv("WEB_DASHBOARD_STREAMING_VIEWER_ID", "demo-viewer")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Simple health endpoint."""

    return {"status": "ok"}


@app.get("/portfolios")
def list_portfolios() -> dict[str, object]:
    """Return a snapshot of portfolios."""

    context = load_dashboard_context()
    return {"items": context.portfolios}


@app.get("/portfolios/history")
def portfolio_history() -> dict[str, object]:
    """Return historical valuation series for each portfolio."""

    history = load_portfolio_history()
    return {
        "items": [series.model_dump(mode="json") for series in history],
        "granularity": "daily",
    }


@app.get("/transactions")
def list_transactions() -> dict[str, object]:
    """Return recent transactions."""

    context = load_dashboard_context()
    return {"items": context.transactions}


@app.get("/alerts")
def list_alerts() -> dict[str, object]:
    """Return currently active alerts."""

    context = load_dashboard_context()
    return {"items": context.alerts}


@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard(request: Request) -> HTMLResponse:
    """Render an HTML dashboard that surfaces key trading signals."""

    context = load_dashboard_context()
    handshake_url = urljoin(STREAMING_BASE_URL, f"rooms/{STREAMING_ROOM_ID}/connection")
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "context": context,
            "streaming": {
                "handshake_url": handshake_url,
                "room_id": STREAMING_ROOM_ID,
                "viewer_id": STREAMING_VIEWER_ID,
            },
        },
    )


@app.get("/")
def root_redirect(request: Request) -> HTMLResponse:
    """Serve the dashboard at the root path for convenience."""

    return render_dashboard(request)

