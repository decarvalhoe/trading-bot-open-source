"""End-to-end user journey covering registration to backtest."""

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
                "first_name": "Demo",
                "last_name": "Trader",
                "phone": None,
            },
        )
    response.raise_for_status()
    payload = response.json()
    return int(payload["id"])


async def _register_user_in_auth_service(auth_service_base_url: str, email: str, password: str) -> dict:
    async with httpx.AsyncClient(base_url=auth_service_base_url) as client:
        response = await client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
    response.raise_for_status()
    return response.json()


async def test_demo_user_journey(
    dashboard_base_url: str,
    user_service_base_url: str,
    auth_service_base_url: str,
):
    """Walk through the demo journey from registration to a successful backtest."""

    email = f"demo-{uuid4().hex[:8]}@example.com"
    password = "ValidPass123!"

    auth_payload = await _register_user_in_auth_service(auth_service_base_url, email, password)
    assert auth_payload["email"] == email

    user_id = await _register_user_in_user_service(user_service_base_url, email)

    async with playwright_async.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(locale="fr-FR", viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        try:
            await page.goto(f"{dashboard_base_url}/account", wait_until="networkidle")

            await page.get_by_label("Adresse e-mail").fill(email)
            await page.get_by_label("Mot de passe").fill(password)

            async with page.expect_response("**/account/login") as login_response_info:
                await page.get_by_role("button", name=re.compile("Se connecter", re.I)).click()
            login_response = await login_response_info.value
            assert login_response.ok

            await expect(
                page.get_by_role("status").filter(has_text=re.compile("Connecté en tant que", re.I))
            ).to_contain_text(email)

            await page.goto(
                f"{dashboard_base_url}/dashboard?user_id={user_id}", wait_until="networkidle"
            )

            summary = page.locator("#onboarding-root").get_by_role("status").nth(0)
            await expect(summary).to_have_text(re.compile(r"0 / 3"))

            steps_list = page.get_by_role("list", name="Parcours d'onboarding")

            broker_step = steps_list.get_by_role("listitem").filter(has_text="Connexion broker").nth(0)
            await broker_step.get_by_role("button", name=re.compile("Connexion broker", re.I)).click()
            await expect(summary).to_have_text(re.compile(r"1 / 3"))

            strategy_step = (
                steps_list.get_by_role("listitem").filter(has_text="Créer une stratégie").nth(0)
            )
            await strategy_step.get_by_role("button", name=re.compile("Créer une stratégie", re.I)).click()
            await expect(summary).to_have_text(re.compile(r"2 / 3"))

            backtest_step = (
                steps_list.get_by_role("listitem").filter(has_text="Premier backtest").nth(0)
            )
            await backtest_step.get_by_role("button", name=re.compile("Premier backtest", re.I)).click()
            await expect(summary).to_have_text(re.compile(r"3 / 3"))
            await expect(summary).to_have_text(re.compile("Parcours terminé", re.I))

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

            with respx.mock(assert_all_called=False) as mock:
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

                await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

                await expect(page.get_by_role("heading", name="Backtests")).to_be_visible()

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
                await expect(
                    page.locator(".backtest-console__history-list li").first
                ).to_contain_text("ETHUSDT")
        finally:
            await context.close()
            await browser.close()
