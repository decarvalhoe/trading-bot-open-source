"""Account-related routes for the web dashboard."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Account"])

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

AUTH_BASE_URL = (
    os.getenv("AUTH_BASE_URL")
    or os.getenv("AUTH_SERVICE_URL")
    or "http://auth_service:8000"
)
AUTH_TIMEOUT = float(os.getenv("WEB_DASHBOARD_AUTH_SERVICE_TIMEOUT", "10.0"))


@router.get(
    "/account/register",
    response_class=HTMLResponse,
    name="render_account_register",
)
async def register_form(request: Request) -> HTMLResponse:
    """Render the account registration page."""

    context = {
        "request": request,
        "created": request.query_params.get("created"),
        "error": request.query_params.get("error"),
    }
    return templates.TemplateResponse("account/register.html", context)


@router.post(
    "/account/register",
    name="submit_account_registration",
)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    """Proxy the registration request to the authentication service."""

    register_url = f"{AUTH_BASE_URL.rstrip('/')}/auth/register"
    try:
        async with httpx.AsyncClient(timeout=AUTH_TIMEOUT) as client:
            response = await client.post(
                register_url,
                json={"email": email, "password": password},
            )
    except httpx.HTTPError:
        target = request.url_for("render_account_register").include_query_params(
            error="network"
        )
        return RedirectResponse(str(target), status_code=status.HTTP_303_SEE_OTHER)

    if response.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED):
        login_target = request.url_for("render_account_login").include_query_params(
            created="1"
        )
        return RedirectResponse(str(login_target), status_code=status.HTTP_303_SEE_OTHER)

    target = request.url_for("render_account_register").include_query_params(
        error=str(response.status_code)
    )
    return RedirectResponse(str(target), status_code=status.HTTP_303_SEE_OTHER)
