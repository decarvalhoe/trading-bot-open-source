"""End-to-end journey covering registration, status checks and backtesting."""

from __future__ import annotations

import json
import os
import re
from uuid import uuid4

import httpx
import pytest

from services.web_dashboard.app.routes import status as status_routes


pytestmark = pytest.mark.asyncio

respx = pytest.importorskip("respx")
playwright_async = pytest.importorskip("playwright.async_api")
Page = playwright_async.Page
expect = playwright_async.expect


async def test_registration_login_status_and_backtest(page: Page, dashboard_base_url: str) -> None:
    """Register through the UI, verify service status and run a backtest."""

    email = f"journey-{uuid4().hex[:8]}@example.com"
    password = "ValidPass123!"

    await page.goto(f"{dashboard_base_url}/account/register", wait_until="networkidle")

    await expect(page.get_by_role("heading", name=re.compile("Inscription", re.I))).to_be_visible()

    await page.get_by_label("Adresse e-mail").fill(email)
    await page.get_by_label("Mot de passe").fill(password)

    async with page.expect_navigation(
        url=re.compile(r"/account/login\?created=1$"), wait_until="networkidle"
    ):
        await page.get_by_role("button", name="Créer mon compte").click()

    await expect(page.get_by_role("heading", name=re.compile("Connexion", re.I))).to_be_visible()

    await page.get_by_label("Adresse e-mail").fill(email)
    await page.get_by_label("Mot de passe").fill(password)

    async with page.expect_response("**/account/login") as login_response_info:
        await page.get_by_role("button", name=re.compile("Se connecter", re.I)).click()

    login_response = await login_response_info.value
    assert login_response.ok

    await expect(
        page.get_by_role("status").filter(has_text=re.compile(email, re.I))
    ).to_be_visible()

    service_definitions = status_routes._service_definitions()

    with respx.mock(assert_all_called=False) as mock:
        for definition in service_definitions:
            base_url = os.getenv(definition["env"], definition["default"])
            health_url = f"{base_url.rstrip('/')}/health"
            mock.get(health_url).mock(return_value=httpx.Response(200, json={"status": "ok"}))

        await page.goto(f"{dashboard_base_url}/status", wait_until="networkidle")

        await expect(page.get_by_role("heading", name="État temps réel")).to_be_visible()

        for definition in service_definitions:
            service_item = page.get_by_role("listitem").filter(has_text=definition["label"]).first
            badge = service_item.locator(".status-list__status")
            await expect(badge).to_contain_text("Opérationnel")
            await expect(badge).to_have_class(re.compile(r"badge--success"))

    initial_metrics = {
        "strategy_id": "strat-1",
        "strategy_name": "ORB",
        "equity_curve": [10_000, 10_500, 11_200],
        "profit_loss": 1_200.0,
        "total_return": 0.12,
        "max_drawdown": 0.04,
        "initial_balance": 10_000.0,
        "metadata": {"symbol": "BTCUSDT", "timeframe": "1h"},
        "ran_at": "2024-04-04T10:00:00Z",
    }
    updated_metrics = {
        **initial_metrics,
        "equity_curve": [10_000, 10_800, 11_800],
        "profit_loss": 1_800.0,
        "total_return": 0.18,
        "max_drawdown": 0.03,
        "metadata": {"symbol": "ETHUSDT", "timeframe": "4h"},
        "ran_at": "2024-04-05T15:30:00Z",
    }

    history_initial = {"items": [initial_metrics], "total": 1, "page": 1, "page_size": 5}
    history_updated = {"items": [updated_metrics], "total": 1, "page": 1, "page_size": 5}

    with respx.mock(assert_all_called=False) as mock:
        mock.post("http://algo-engine:8000/strategies/import").mock(
            return_value=httpx.Response(200, json={"id": "strat-1", "status": "imported"})
        )
        mock.get("http://algo-engine:8000/strategies").mock(
            return_value=httpx.Response(
                200, json={"items": [{"id": "strat-1", "name": "ORB", "strategy_type": "orb"}]}
            )
        )
        mock.get("http://algo-engine:8000/strategies/strat-1/backtest/ui").mock(
            side_effect=[
                httpx.Response(200, json=initial_metrics),
                httpx.Response(200, json=updated_metrics),
            ]
        )
        mock.get("http://algo-engine:8000/strategies/strat-1/backtests").mock(
            side_effect=[
                httpx.Response(200, json=history_initial),
                httpx.Response(200, json=history_updated),
            ]
        )
        mock.post("http://algo-engine:8000/strategies/strat-1/backtest").mock(
            return_value=httpx.Response(200, json=updated_metrics)
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

        async with page.expect_request("**/strategies/save") as save_request_info:
            await page.get_by_role("button", name="Enregistrer la stratégie").click()

        save_request = await save_request_info.value
        payload = json.loads(save_request.post_data or "{}")
        assert payload["name"] == "Swing Setup"
        assert payload["format"] == "yaml"
        assert "rules" in payload["code"]

        await expect(page.get_by_text("Stratégie enregistrée avec succès.")).to_be_visible()

        await page.get_by_label("Actif").fill("ETHUSDT")
        await page.get_by_label("Période").select_option("4h")
        await page.get_by_label("Fenêtre (jours)").fill("45")
        await page.get_by_label("Capital initial").fill("15000")

        async with page.expect_request("**/api/strategies/**/backtest") as backtest_request_info:
            await page.get_by_role("button", name="Lancer le backtest").click()

        backtest_request = await backtest_request_info.value
        payload = json.loads(backtest_request.post_data or "{}")
        assert payload == {
            "symbol": "ETHUSDT",
            "timeframe": "4h",
            "lookback_days": 45,
            "initial_balance": 15000,
        }

        await expect(page.get_by_text("Backtest exécuté avec succès.")).to_be_visible()
        await expect(page.get_by_role("img", name="Équity du backtest")).to_be_visible()
        await expect(page.locator(".backtest-console__history-list li").first).to_contain_text("ETHUSDT")
