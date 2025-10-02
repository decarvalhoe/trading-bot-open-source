import re

import pytest

pytestmark = pytest.mark.asyncio

playwright_async = pytest.importorskip("playwright.async_api")
Page = playwright_async.Page
expect = playwright_async.expect


async def test_strategy_documentation_accessible_via_navigation(page: Page, dashboard_base_url: str):
    await page.goto(f"{dashboard_base_url}/dashboard", wait_until="networkidle")

    await page.get_by_role("link", name="Documentation stratégies").click()

    await expect(page).to_have_url(re.compile(r"/strategies/documentation"))
    await expect(page.get_by_role("heading", level=1, name="Documentation stratégies")).to_be_visible()
    await expect(page.frame_locator("iframe[title='Notebook backtest-sandbox.ipynb']")).to_be_visible()


async def test_strategy_documentation_schema_badge_visible(page: Page, dashboard_base_url: str):
    await page.goto(f"{dashboard_base_url}/strategies/documentation", wait_until="networkidle")

    await expect(page.locator(".docs-schema-badge")).to_contain_text("Schéma déclaratif — version")
    await expect(page.get_by_role("link", name="Consulter la source").first).to_have_attribute(
        "href", re.compile(r"backtest-sandbox\.ipynb")
    )
