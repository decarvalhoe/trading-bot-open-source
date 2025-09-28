"""Minimal dashboard service for monitoring trading activity."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .data import load_dashboard_context


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Web Dashboard", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    """Simple health endpoint."""

    return {"status": "ok"}


@app.get("/portfolios")
def list_portfolios() -> dict[str, object]:
    """Return a snapshot of portfolios."""

    context = load_dashboard_context()
    return {"items": context.portfolios}


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
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "context": context,
        },
    )


@app.get("/")
def root_redirect(request: Request) -> HTMLResponse:
    """Serve the dashboard at the root path for convenience."""

    return render_dashboard(request)

