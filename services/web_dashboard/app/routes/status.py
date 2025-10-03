"""Status page for the web dashboard."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, status as http_status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..config import default_service_url

router = APIRouter(tags=["Status"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

AUTH_BASE_URL = (
    os.getenv("AUTH_BASE_URL")
    or os.getenv("WEB_DASHBOARD_AUTH_SERVICE_URL")
    or os.getenv("AUTH_SERVICE_URL")
    or default_service_url(
        "http://auth_service:8000", native_port=8011, trailing_slash=False
    )
)
REPORTS_BASE_URL = (
    os.getenv("REPORTS_BASE_URL")
    or os.getenv("WEB_DASHBOARD_REPORTS_BASE_URL")
    or default_service_url("http://reports:8000", native_port=8016, trailing_slash=False)
)
ALGO_BASE_URL = (
    os.getenv("ALGO_ENGINE_BASE_URL")
    or os.getenv("WEB_DASHBOARD_ALGO_ENGINE_URL")
    or default_service_url("http://algo_engine:8000", native_port=8014, trailing_slash=False)
)
ROUTER_BASE_URL = (
    os.getenv("ORDER_ROUTER_BASE_URL")
    or os.getenv("WEB_DASHBOARD_ORDER_ROUTER_BASE_URL")
    or default_service_url("http://order_router:8000", native_port=8013, trailing_slash=False)
)
MARKET_BASE_URL = (
    os.getenv("MARKET_DATA_BASE_URL")
    or os.getenv("WEB_DASHBOARD_MARKETPLACE_URL")
    or default_service_url("http://market_data:8000", native_port=8015, trailing_slash=False)
)
STATUS_TIMEOUT = float(os.getenv("WEB_DASHBOARD_STATUS_TIMEOUT", "5.0"))


async def _check_service(url: str) -> tuple[bool, int | None]:
    """Return ``(True, status_code)`` when the provided health endpoint answers successfully."""

    try:
        async with httpx.AsyncClient(timeout=STATUS_TIMEOUT) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return False, None
    return response.status_code == http_status.HTTP_200_OK, response.status_code


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
    status_codes: dict[str, int | None] = {}
    for name, url in targets.items():
        is_up, status_code = await _check_service(url)
        results[name] = is_up
        status_codes[name] = status_code

    context = {"request": request, "services": results, "targets": targets, "status_codes": status_codes}
    return templates.TemplateResponse("misc/status.html", context)
