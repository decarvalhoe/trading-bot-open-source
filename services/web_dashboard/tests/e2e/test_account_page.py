"""End-to-end tests covering the account page user interactions."""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest

pytestmark = pytest.mark.asyncio

playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

BROWSER_PROJECTS = [
    pytest.param("chromium", {"width": 1440, "height": 900}, id="chromium-desktop"),
    pytest.param("firefox", {"width": 1280, "height": 800}, id="firefox-desktop"),
]

ANONYMOUS_SESSION: Dict[str, Any] = {"authenticated": False, "user": None}
LOGIN_RESPONSE: Dict[str, Any] = {
    "authenticated": True,
    "user": {
        "id": "42",
        "email": "trader@example.com",
        "scopes": ["dashboard:read"],
    },
}

BROKER_CREDENTIALS_EMPTY: Dict[str, Any] = {"credentials": []}
BROKER_CREDENTIALS_INITIAL: Dict[str, Any] = {
    "credentials": [
        {
            "broker": "binance",
            "has_api_key": True,
            "has_api_secret": True,
            "api_key_masked": "••••1234",
            "api_secret_masked": "••••9876",
            "updated_at": "2024-05-01T10:00:00Z",
        },
        {
            "broker": "ibkr",
            "has_api_key": False,
            "has_api_secret": False,
            "api_key_masked": None,
            "api_secret_masked": None,
            "updated_at": None,
        },
    ]
}
BROKER_CREDENTIALS_UPDATED: Dict[str, Any] = {
    "credentials": [
        {
            "broker": "binance",
            "has_api_key": True,
            "has_api_secret": True,
            "api_key_masked": "••••1234",
            "api_secret_masked": "••••0000",
            "updated_at": "2024-05-01T11:30:00Z",
        },
        {
            "broker": "ibkr",
            "has_api_key": False,
            "has_api_secret": True,
            "api_key_masked": None,
            "api_secret_masked": "••••ABCD",
            "updated_at": "2024-05-01T11:31:00Z",
        },
    ]
}


@pytest.mark.parametrize("project_name,viewport", BROWSER_PROJECTS)
async def test_account_login_form_validation(
    project_name: str, viewport: Dict[str, int], dashboard_base_url: str
):
    """The login form should display validation feedback and accept valid credentials."""

    async with playwright_async.async_playwright() as playwright:
        browser_type = getattr(playwright, project_name)
        browser = await browser_type.launch()
        context = await browser.new_context(locale="fr-FR", viewport=viewport)

        async def _mock_session(route, request):
            if request.method == "GET":
                await route.fulfill(
                    status=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(ANONYMOUS_SESSION),
                )
            else:  # pragma: no cover - other verbs are unused but forwarded
                await route.continue_()

        async def _mock_login(route, request):
            if request.method == "POST":
                await route.fulfill(
                    status=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(LOGIN_RESPONSE),
                )
            else:  # pragma: no cover - safeguard for unexpected verbs
                await route.continue_()

        async def _mock_broker_credentials(route, request):
            if request.method == "GET":
                await route.fulfill(
                    status=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(BROKER_CREDENTIALS_EMPTY),
                )
            else:  # pragma: no cover - other verbs unused in this scenario
                await route.continue_()

        await context.route("**/account/session", _mock_session)
        await context.route("**/account/login", _mock_login)
        await context.route("**/api/account/broker-credentials", _mock_broker_credentials)

        page = await context.new_page()

        try:
            await page.goto(f"{dashboard_base_url}/account", wait_until="networkidle")

            await expect(page.get_by_role("heading", level=2, name="Connexion")).to_be_visible()

            email_input = page.get_by_label("Adresse e-mail")
            password_input = page.get_by_label("Mot de passe")
            submit_button = page.get_by_role("button", name="Se connecter")

            assert await email_input.evaluate("element => element.required")
            assert await password_input.evaluate("element => element.required")

            await email_input.fill("")
            await password_input.fill("")
            await submit_button.click()

            assert await email_input.evaluate("element => element.validity.valueMissing")
            assert await password_input.evaluate("element => element.validity.valueMissing")
            await expect(email_input).to_be_focused()

            await email_input.fill("trader@example.com")
            await password_input.fill("Sup3rSecret!")

            assert await email_input.evaluate("element => element.checkValidity()")
            assert await password_input.evaluate("element => element.checkValidity()")

            async with page.expect_response("**/account/login") as login_response:
                await submit_button.click()
            response = await login_response.value
            assert response.ok

            await expect(page.get_by_role("status")).to_contain_text("trader@example.com")
        finally:
            await context.close()
            await browser.close()


@pytest.mark.parametrize("project_name,viewport", BROWSER_PROJECTS)
async def test_account_broker_credentials_form_flow(
    project_name: str, viewport: Dict[str, int], dashboard_base_url: str
):
    """Authenticated users can consulter and mettre à jour leurs clés broker."""

    captured_updates: list[Dict[str, Any]] = []

    async with playwright_async.async_playwright() as playwright:
        browser_type = getattr(playwright, project_name)
        browser = await browser_type.launch()
        context = await browser.new_context(locale="fr-FR", viewport=viewport)

        async def _mock_session(route, request):
            if request.method == "GET":
                await route.fulfill(
                    status=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(LOGIN_RESPONSE),
                )
            else:  # pragma: no cover - defensive guard
                await route.continue_()

        async def _mock_broker(route, request):
            if request.method == "GET":
                await route.fulfill(
                    status=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(BROKER_CREDENTIALS_INITIAL),
                )
            elif request.method == "PUT":
                captured_updates.append(await request.post_data_json())
                await route.fulfill(
                    status=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(BROKER_CREDENTIALS_UPDATED),
                )
            else:  # pragma: no cover - unexpected verb
                await route.continue_()

        await context.route("**/account/session", _mock_session)
        await context.route("**/api/account/broker-credentials", _mock_broker)

        page = await context.new_page()

        try:
            await page.goto(f"{dashboard_base_url}/account", wait_until="networkidle")

            await expect(page.get_by_role("heading", level=2, name="Connexion")).to_be_visible()
            await expect(page.get_by_text("Clé enregistrée : ••••1234")).to_be_visible()

            binance_api_key = page.get_by_label("Clé API (Binance)")
            binance_secret = page.get_by_label("Secret API (Binance)")
            ibkr_secret = page.get_by_label("Mot de passe API (IBKR)")

            await expect(binance_api_key).to_have_value("")
            await expect(binance_secret).to_have_value("")

            await binance_secret.fill("binance-secret-0000")
            await ibkr_secret.fill("ibkr-super-secret")

            async with page.expect_response(
                lambda response: response.request.method == "PUT"
                and "/api/account/broker-credentials" in response.url
            ) as update_response:
                await page.get_by_role("button", name="Sauvegarder les identifiants").click()

            response = await update_response.value
            assert response.ok

            assert captured_updates, "Le payload de mise à jour broker devrait être capturé"
            assert captured_updates[0] == {
                "credentials": [
                    {"broker": "binance", "api_secret": "binance-secret-0000"},
                    {"broker": "ibkr", "api_secret": "ibkr-super-secret"},
                ]
            }

            await expect(page.get_by_text("Identifiants broker mis à jour.")).to_be_visible()
            await expect(binance_secret).to_have_value("")
            await expect(ibkr_secret).to_have_value("")
            await expect(page.get_by_text("Secret enregistré : ••••0000")).to_be_visible()
            await expect(page.get_by_text("Secret enregistré : ••••ABCD")).to_be_visible()
        finally:
            await context.close()
            await browser.close()
