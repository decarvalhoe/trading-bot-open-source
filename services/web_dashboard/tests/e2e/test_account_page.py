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

        await context.route("**/account/session", _mock_session)
        await context.route("**/account/login", _mock_login)

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
