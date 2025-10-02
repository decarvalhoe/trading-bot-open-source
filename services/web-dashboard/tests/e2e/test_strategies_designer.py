import json

import pytest
from httpx import Response

pytestmark = pytest.mark.asyncio

respx = pytest.importorskip("respx")
playwright_async = pytest.importorskip("playwright.async_api")
Page = playwright_async.Page
expect = playwright_async.expect


async def test_strategy_designer_saves_strategy(page: Page, dashboard_base_url: str):
    with respx.mock(assert_all_called=False) as mock:
        algo_route = mock.post("http://algo-engine:8000/strategies/import").mock(
            return_value=Response(200, json={"id": "strat-001", "status": "imported"})
        )

        await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

        await expect(page.get_by_role("heading", name="Éditeur visuel")).to_be_visible()

        await page.get_by_label("Nom de la stratégie").fill("Swing Setup")

        await page.get_by_test_id("palette-item-condition").drag_to(
            page.get_by_test_id("designer-conditions-dropzone")
        )
        await page.get_by_test_id("palette-item-indicator").drag_to(
            page.get_by_test_id("designer-dropzone-condition").first
        )
        await page.get_by_role("button", name="Ajouter Action d'exécution").click()

        async with page.expect_request("**/strategies/save") as request_info:
            await page.get_by_role("button", name="Enregistrer la stratégie").click()

        request = await request_info.value
        payload = json.loads(request.post_data or "{}")
        assert payload["name"] == "Swing Setup"
        assert payload["format"] == "yaml"
        assert "rules" in payload["code"]

        await expect(page.get_by_text("Stratégie enregistrée avec succès.")).to_be_visible()
        assert algo_route.called
