import json

import pytest
from httpx import Response

pytestmark = pytest.mark.asyncio

respx = pytest.importorskip("respx")
playwright_async = pytest.importorskip("playwright.async_api")
Page = playwright_async.Page
expect = playwright_async.expect


async def test_strategy_backtest_console_runs_backtest(page: Page, dashboard_base_url: str):
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
            return_value=Response(
                200,
                json={"items": [{"id": "strat-1", "name": "ORB", "strategy_type": "orb"}]},
            )
        )
        mock.get("http://algo-engine:8000/strategies/strat-1/backtest/ui").mock(
            side_effect=[Response(200, json=initial_metrics), Response(200, json=updated_metrics)]
        )
        mock.get("http://algo-engine:8000/strategies/strat-1/backtests").mock(
            side_effect=[Response(200, json=history_initial), Response(200, json=history_updated)]
        )
        mock.post("http://algo-engine:8000/strategies/strat-1/backtest").mock(
            return_value=Response(200, json=updated_metrics)
        )

        await page.goto(f"{dashboard_base_url}/strategies", wait_until="networkidle")

        await expect(page.get_by_role("heading", name="Backtests")).to_be_visible()

        await page.get_by_label("Actif").fill("ETHUSDT")
        await page.get_by_label("Période").select_option("4h")
        await page.get_by_label("Fenêtre (jours)").fill("45")
        await page.get_by_label("Capital initial").fill("15000")

        async with page.expect_request("**/api/strategies/**/backtest") as request_info:
            await page.get_by_role("button", name="Lancer le backtest").click()

        request = await request_info.value
        payload = json.loads(request.post_data or "{}")
        assert payload["symbol"] == "ETHUSDT"
        assert payload["timeframe"] == "4h"
        assert payload["lookback_days"] == 45
        assert payload["initial_balance"] == 15000

        await expect(page.get_by_text("Backtest exécuté avec succès.")).to_be_visible()
        await expect(page.get_by_role("img", name="Équity du backtest")).to_be_visible()
        await expect(page.locator(".backtest-console__history-list li").first).to_contain_text(
            "ETHUSDT"
        )
