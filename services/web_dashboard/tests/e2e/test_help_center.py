import re

import pytest

pytestmark = pytest.mark.asyncio

playwright_async = pytest.importorskip("playwright.async_api")
Page = playwright_async.Page
expect = playwright_async.expect


async def test_help_center_accessible_via_navigation(page: Page, dashboard_base_url: str):
    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    await page.get_by_role("link", name="Aide & formation").click()

    await expect(page).to_have_url(re.compile(r"/help"))
    await expect(page.get_by_role("heading", level=1, name="Aide & formation")).to_be_visible()
    await expect(page.get_by_role("progressbar", name=re.compile("Progression", re.I))).to_be_visible()


async def test_help_center_faq_toggle_is_accessible(page: Page, dashboard_base_url: str):
    await page.goto(f"{dashboard_base_url}/help", wait_until="networkidle")

    faq_button = page.get_by_role(
        "button", name=re.compile("Comment connecter mes clés API broker", re.I)
    )
    await faq_button.click()
    await expect(faq_button).to_have_attribute("aria-expanded", "true")

    await expect(
        page.locator(".help-article__tag", has_text=re.compile("onboarding", re.I))
    ).to_be_visible()
