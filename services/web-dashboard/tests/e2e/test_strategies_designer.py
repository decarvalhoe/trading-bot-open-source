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


async def test_strategy_designer_validation_feedback(page: Page, dashboard_base_url: str):
    await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

    await expect(page.get_by_role("heading", name="Éditeur visuel")).to_be_visible()

    await page.get_by_test_id("palette-item-logic").drag_to(
        page.get_by_test_id("designer-conditions-dropzone")
    )
    logic_dropzone = page.get_by_test_id("designer-dropzone-logic").first

    await page.get_by_test_id("palette-item-condition").drag_to(logic_dropzone)
    condition_dropzone = page.get_by_test_id("designer-dropzone-condition").first

    await page.get_by_test_id("palette-item-indicator_macd").drag_to(condition_dropzone)

    macd_block = page.locator("[data-node-type='indicator_macd']").first
    await macd_block.get_by_label("Période rapide").fill("8")
    await macd_block.get_by_label("Période lente").fill("21")
    await macd_block.get_by_label("Période signal").fill("5")

    await page.get_by_test_id("palette-item-market_cross").drag_to(logic_dropzone)
    cross_dropzone = page.get_by_test_id("designer-dropzone-market_cross").first
    await page.get_by_test_id("palette-item-indicator_bollinger").drag_to(cross_dropzone)
    await page.get_by_test_id("palette-item-indicator_atr").drag_to(cross_dropzone)

    await page.get_by_test_id("palette-item-market_volume").drag_to(logic_dropzone)
    volume_block = page.locator("[data-node-type='market_volume']").first
    await volume_block.get_by_label("Seuil").fill("250000")
    await volume_block.get_by_label("Intervalle").fill("4h")

    actions_dropzone = page.get_by_test_id("designer-actions-dropzone")
    await page.get_by_test_id("palette-item-action").drag_to(actions_dropzone)
    await page.get_by_test_id("palette-item-take_profit").drag_to(actions_dropzone)
    await page.get_by_test_id("palette-item-stop_loss").drag_to(actions_dropzone)
    await page.get_by_test_id("palette-item-alert").drag_to(actions_dropzone)

    take_profit_block = page.locator("[data-node-type='take_profit']").first
    await take_profit_block.get_by_label("Valeur").fill("4.5")
    await take_profit_block.get_by_label("Part de la position").select_option("half")

    stop_loss_block = page.locator("[data-node-type='stop_loss']").first
    await stop_loss_block.get_by_label("Valeur").fill("1.5")
    await stop_loss_block.get_by_label("Activer le trailing stop").check()

    alert_block = page.locator("[data-node-type='alert']").first
    await alert_block.get_by_label("Message").fill("Notifier l'équipe trading")

    validation_panel = page.get_by_test_id("designer-validation")
    await expect(validation_panel.get_by_text("Règle valide")).to_be_visible()
    await expect(validation_panel.locator(".designer-validation__rule")).to_contain_text("MACD")

    await take_profit_block.get_by_label("Valeur").fill("")
    await expect(validation_panel.get_by_text("Erreurs de configuration")).to_be_visible()
    await expect(validation_panel.locator("li")).to_contain_text("Take-profit")


async def test_strategy_designer_applies_preset(page: Page, dashboard_base_url: str):
    await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

    await expect(page.get_by_role("heading", name="Éditeur visuel")).to_be_visible()

    await page.get_by_test_id("preset-apply-momentum_breakout").click()

    await expect(page.get_by_text("Modèle « Cassure momentum » chargé.")).to_be_visible()
    await expect(page.get_by_label("Nom de la stratégie")).to_have_value("Cassure Momentum")
    await expect(page.locator("[data-node-type='condition']").first).to_be_visible()
    await expect(page.locator("[data-node-type='take_profit']").first).to_be_visible()


async def test_strategy_designer_imports_yaml_file(tmp_path, page: Page, dashboard_base_url: str):
    content = """name: Import Test\nrules:\n  - when:\n      field: close\n      operator: gt\n      value: 120\n    signal:\n      steps:\n        - type: order\n          action: buy\n          size: 1\n        - type: stop_loss\n          mode: percent\n          value: 4\n"""
    file_path = tmp_path / "existing-strategy.yaml"
    file_path.write_text(content, encoding="utf-8")

    await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

    await page.get_by_test_id("designer-file-input").set_input_files(str(file_path))

    await expect(page.get_by_text(f"Fichier « {file_path.name} » importé.")).to_be_visible()
    await expect(page.get_by_label("Nom de la stratégie")).to_have_value("Import Test")
    await expect(page.locator("[data-node-type='stop_loss']").first).to_be_visible()
