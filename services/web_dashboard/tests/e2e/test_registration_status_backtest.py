"""End-to-end scenario covering registration, status checks and backtesting."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest
from jose import jwt

pytestmark = pytest.mark.asyncio

respx = pytest.importorskip("respx")
playwright_async = pytest.importorskip("playwright.async_api")
expect = playwright_async.expect

TEST_JWT_SECRET = "test-onboarding-secret"


def _service_token() -> str:
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode({"sub": "auth-service", "iat": now}, TEST_JWT_SECRET, algorithm="HS256")


async def _register_user_in_user_service(user_service_base_url: str, email: str) -> int:
    async with httpx.AsyncClient(base_url=user_service_base_url) as client:
        response = await client.post(
            "/users/register",
            headers={"Authorization": f"Bearer {_service_token()}"},
            json={
                "email": email,
                "first_name": "Status",
                "last_name": "Trader",
                "phone": None,
            },
        )
    response.raise_for_status()
    payload = response.json()
    return int(payload["id"])


async def test_registration_status_backtest(
    dashboard_base_url: str,
    user_service_base_url: str,
    auth_service_base_url: str,
) -> None:
    """Walk through registration, status inspection and a simulated backtest."""

    email = f"status-{uuid4().hex[:8]}@example.com"
    password = "ValidPass123!"

    async with playwright_async.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(locale="fr-FR", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(f"{dashboard_base_url}/account/register", wait_until="networkidle")

            await page.get_by_label("Adresse e-mail").fill(email)
            await page.get_by_label("Mot de passe").fill(password)

            async with page.expect_navigation(url=re.compile(r"/account/login")):
                await page.get_by_role("button", name=re.compile("Créer mon compte", re.I)).click()

            assert "created=1" in page.url

            await page.get_by_label("Adresse e-mail").fill(email)
            await page.get_by_label("Mot de passe").fill(password)

            async with page.expect_response("**/account/login") as login_response_info:
                await page.get_by_role("button", name=re.compile("Se connecter", re.I)).click()

            login_response = await login_response_info.value
            assert login_response.ok

            await expect(
                page.get_by_role("status").filter(has_text=re.compile("Connecté en tant que", re.I))
            ).to_contain_text(email)

            await _register_user_in_user_service(user_service_base_url, email)

            with respx.mock(assert_all_called=False) as mock:
                health_endpoints = {
                    f"{auth_service_base_url.rstrip('/')}/health",
                    "http://reports:8000/health",
                    "http://algo_engine:8000/health",
                    "http://algo-engine:8000/health",
                    "http://order_router:8000/health",
                    "http://order-router:8000/health",
                    "http://market_data:8000/health",
                    "http://market-data:8000/health",
                }
                for url in health_endpoints:
                    mock.get(url).mock(return_value=httpx.Response(200, json={"status": "ok"}))

                algo_import_route = mock.post("http://algo-engine:8000/strategies/import").mock(
                    return_value=httpx.Response(200, json={"id": "strat-001", "status": "imported"})
                )

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

                history_initial = {
                    "items": [initial_metrics],
                    "total": 1,
                    "page": 1,
                    "page_size": 5,
                }
                history_updated = {
                    "items": [updated_metrics],
                    "total": 1,
                    "page": 1,
                    "page_size": 5,
                }

                mock.get("http://algo-engine:8000/strategies").mock(
                    return_value=httpx.Response(
                        200,
                        json={"items": [{"id": "strat-1", "name": "ORB", "strategy_type": "orb"}]},
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

                await page.goto(f"{dashboard_base_url}/status", wait_until="networkidle")

                await expect(
                    page.get_by_role("heading", name="Surveillance des services")
                ).to_be_visible()
                await expect(
                    page.get_by_role("heading", name="État temps réel")
                ).to_be_visible()
                await expect(page.get_by_text("Service d'authentification")).to_be_visible()
                await expect(page.get_by_text("Service de rapports")).to_be_visible()
                await expect(page.locator(".badge--success").first).to_be_visible()

                await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

                await expect(page.get_by_role("heading", name="Éditeur visuel")).to_be_visible()
                await page.get_by_test_id("preset-apply-momentum_breakout").click()
                await expect(
                    page.get_by_text("Modèle « Cassure momentum » chargé.")
                ).to_be_visible()

                strategy_name = "Stratégie Status"
                await page.get_by_label("Nom de la stratégie").fill(strategy_name)

                async with page.expect_request("**/strategies/save") as save_request_info:
                    await page.get_by_role("button", name="Enregistrer la stratégie").click()

                save_request = await save_request_info.value
                payload = json.loads(save_request.post_data or "{}")
                assert payload.get("name") == strategy_name
                assert algo_import_route.called
                await expect(
                    page.get_by_text("Stratégie enregistrée avec succès.")
                ).to_be_visible()

                await expect(page.get_by_role("heading", name="Backtests")).to_be_visible()

                await page.get_by_label("Actif").fill("ETHUSDT")
                await page.get_by_label("Période").select_option("4h")
                await page.get_by_label("Fenêtre (jours)").fill("45")
                await page.get_by_label("Capital initial").fill("15000")

                async with page.expect_request("**/api/strategies/**/backtest") as backtest_request_info:
                    await page.get_by_role("button", name="Lancer le backtest").click()

                backtest_request = await backtest_request_info.value
                backtest_payload = json.loads(backtest_request.post_data or "{}")
                assert backtest_payload == {
                    "symbol": "ETHUSDT",
                    "timeframe": "4h",
                    "lookback_days": 45,
                    "initial_balance": 15000,
                }

                await expect(page.get_by_text("Backtest exécuté avec succès.")).to_be_visible()
                await expect(page.get_by_role("img", name="Équity du backtest")).to_be_visible()
                await expect(page.locator(".backtest-console__history-list li").first).to_contain_text(
                    "ETHUSDT"
                )
        finally:
            await context.close()
            await browser.close()
