"""Status page for the web dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

import httpx
from fastapi import APIRouter, status as http_status

from ..config import default_service_url
router = APIRouter(tags=["Status"])

STATUS_TIMEOUT = float(os.getenv("WEB_DASHBOARD_STATUS_TIMEOUT", "5.0"))


STATUS_CODES: dict[int | None, str] = {
    http_status.HTTP_503_SERVICE_UNAVAILABLE: "HTTP 503 - Indisponible",
    http_status.HTTP_500_INTERNAL_SERVER_ERROR: "HTTP 500 - Erreur interne",
    http_status.HTTP_502_BAD_GATEWAY: "HTTP 502 - Mauvaise passerelle",
    http_status.HTTP_504_GATEWAY_TIMEOUT: "HTTP 504 - Délai d'attente dépassé",
    None: "Impossible de contacter le service",
}


ServiceDefinition = dict[str, Any]


def _service_definitions() -> list[ServiceDefinition]:
    """Return the service definitions displayed on the status page."""

    return [
        {
            "name": "auth",
            "env": "WEB_DASHBOARD_AUTH_SERVICE_URL",
            "default": default_service_url("auth_service"),
            "label": "Service d'authentification",
            "description": "Gestion des comptes utilisateurs et des sessions.",
        },
        {
            "name": "reports",
            "env": "WEB_DASHBOARD_REPORTS_BASE_URL",
            "default": default_service_url("reports"),
            "label": "Service de rapports",
            "description": "Génère les rapports de performance et d'exécution.",
        },
        {
            "name": "algo",
            "env": "WEB_DASHBOARD_ALGO_ENGINE_URL",
            "default": default_service_url("algo_engine"),
            "label": "Moteur d'algorithmes",
            "description": "Exécute les stratégies quantitatives en continu.",
        },
        {
            "name": "router",
            "env": "WEB_DASHBOARD_ORDER_ROUTER_BASE_URL",
            "default": default_service_url("order_router"),
            "label": "Routeur d'ordres",
            "description": "Distribue les ordres vers les places de marché.",
        },
        {
            "name": "market",
            "env": "WEB_DASHBOARD_MARKETPLACE_URL",
            "default": default_service_url("marketplace"),
            "label": "Service marketplace",
            "description": "Fournit les données de marché et la vitrine produits.",
        },
    ]


async def _check_service(url: str) -> tuple[bool, int | None]:
    """Return the availability flag and status code for a health endpoint."""

    try:
        async with httpx.AsyncClient(timeout=STATUS_TIMEOUT) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return False, None
    return response.status_code == http_status.HTTP_200_OK, response.status_code


def _service_status_label(is_up: bool) -> str:
    return "Opérationnel" if is_up else "Incident"


def _service_badge_variant(is_up: bool) -> str:
    return "success" if is_up else "critical"


def _service_indicator(is_up: bool) -> str:
    return "up" if is_up else "down"


def _service_detail(status_code: int | None) -> str | None:
    if status_code == http_status.HTTP_200_OK:
        return None
    if status_code in STATUS_CODES:
        return STATUS_CODES[status_code]
    if status_code is None:
        return STATUS_CODES[None]
    return f"HTTP {status_code} - Réponse inattendue"


@router.get("/status/overview", name="status_overview")
async def status_overview() -> dict[str, Any]:
    """Return the aggregated health status for core services."""

    services: list[dict[str, Any]] = []
    for service in _service_definitions():
        base_url = os.getenv(service["env"], service["default"])
        health_url = f"{base_url.rstrip('/')}/health"
        is_up, status_code = await _check_service(health_url)
        services.append(
            {
                "name": service["name"],
                "label": service["label"],
                "description": service["description"],
                "health_url": health_url,
                "status": _service_indicator(is_up),
                "status_label": _service_status_label(is_up),
                "badge_variant": _service_badge_variant(is_up),
                "status_code": status_code,
                "detail": _service_detail(status_code),
            }
        )

    return {
        "services": services,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status_codes": STATUS_CODES,
    }
