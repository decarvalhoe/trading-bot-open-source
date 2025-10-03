"""End-to-end tests covering the account page user interactions."""

import pytest

pytestmark = pytest.mark.asyncio

playwright_async = pytest.importorskip("playwright.async_api")
Page = playwright_async.Page
expect = playwright_async.expect

BROWSER_PROJECTS = [
    pytest.param("chromium", id="chromium"),
    pytest.param("firefox", id="firefox"),
]


@pytest.mark.parametrize("browser_name", BROWSER_PROJECTS)
async def test_account_login_form_validation(
    page: Page, browser_name: str, dashboard_base_url: str
):
    """The login form should surface HTML validation feedback before accepting inputs."""

    await page.goto(f"{dashboard_base_url}/account", wait_until="networkidle")

    await expect(page.get_by_role("heading", level=2, name="Connexion")).to_be_visible()

    email_input = page.get_by_label("Adresse e-mail")
    password_input = page.get_by_label("Mot de passe")
    submit_button = page.get_by_role("button", name="Se connecter")

    assert await email_input.evaluate("el.required")
    assert await password_input.evaluate("el.required")

    await email_input.fill("")
    await password_input.fill("")
    await submit_button.click()

    assert await email_input.evaluate("el.validity.valueMissing")
    assert await password_input.evaluate("el.validity.valueMissing")
    await expect(email_input).to_be_focused()

    await email_input.fill("trader@example.com")
    await password_input.fill("Sup3rSecret!")

    assert await email_input.evaluate("el.checkValidity()")
    assert await password_input.evaluate("el.checkValidity()")
