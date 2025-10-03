"""Status page for the web dashboard."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, status as http_status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Status"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

AUTH_BASE_URL = (
    os.getenv("AUTH_BASE_URL")
    or os.getenv("AUTH_SERVICE_URL")
    or "http://auth_service:8000"
)
REPORTS_BASE_URL = os.getenv("REPORTS_BASE_URL", "http://reports:8000")
ALGO_BASE_URL = os.getenv("ALGO_ENGINE_BASE_URL", "http://algo_engine:8000")
ROUTER_BASE_URL = os.getenv("ORDER_ROUTER_BASE_URL", "http://order_router:8000")
MARKET_BASE_URL = os.getenv("MARKET_DATA_BASE_URL", "http://market_data:8000")
STATUS_TIMEOUT = float(os.getenv("WEB_DASHBOARD_STATUS_TIMEOUT", "5.0"))


async def _check_service(url: str) -> bool:
    """Return ``True`` when the provided health endpoint answers successfully."""

    try:
        async with httpx.AsyncClient(timeout=STATUS_TIMEOUT) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return False
    return response.status_code == http_status.HTTP_200_OK


@router.get("/status", response_class=HTMLResponse, name="render_status_page")
async def status_page(request: Request) -> HTMLResponse:
    """Display a minimal status page for core services."""

    targets = {
        "auth": f"{AUTH_BASE_URL.rstrip('/')}/health",
        "reports": f"{REPORTS_BASE_URL.rstrip('/')}/health",
        "algo": f"{ALGO_BASE_URL.rstrip('/')}/health",
        "router": f"{ROUTER_BASE_URL.rstrip('/')}/health",
        "market": f"{MARKET_BASE_URL.rstrip('/')}/health",
    }

    results: dict[str, bool] = {}
    for name, url in targets.items():
        results[name] = await _check_service(url)

    context = {"request": request, "services": results, "targets": targets}
    return templates.TemplateResponse("misc/status.html", context)
