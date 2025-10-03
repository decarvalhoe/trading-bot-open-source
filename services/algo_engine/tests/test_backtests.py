from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi.testclient import TestClient


def _build_market_data() -> list[Dict[str, Any]]:
    return [
        {"close": 100.0, "trigger_buy": True},
        {"close": 110.0, "trigger_sell": True},
    ]


def _build_strategy_payload(name: str = "Declarative Test") -> Dict[str, Any]:
    return {
        "name": name,
        "strategy_type": "declarative",
        "parameters": {
            "definition": {
                "rules": [
                    {
                        "when": {
                            "field": "trigger_buy",
                            "operator": "eq",
                            "value": True,
                        },
                        "signal": {"action": "buy", "size": 1},
                    },
                    {
                        "when": {
                            "field": "trigger_sell",
                            "operator": "eq",
                            "value": True,
                        },
                        "signal": {"action": "sell", "size": 1},
                    },
                ]
            }
        },
        "enabled": False,
        "tags": ["test"],
        "metadata": {"symbol": "BTCUSDT"},
    }


def test_create_and_fetch_backtest(main_module: Any, tmp_path: Path) -> None:
    client = TestClient(main_module.app)
    backtester = main_module.backtester
    original_output = backtester.output_dir
    backtester.output_dir = tmp_path
    try:
        create_response = client.post("/strategies", json=_build_strategy_payload())
        assert create_response.status_code == 201
        strategy = create_response.json()
        strategy_id = strategy["id"]

        run_response = client.post(
            "/backtests",
            json={
                "strategy_id": strategy_id,
                "market_data": _build_market_data(),
                "initial_balance": 1_000.0,
                "metadata": {"symbol": "BTCUSDT", "timeframe": "1h"},
            },
        )
        assert run_response.status_code == 201
        payload = run_response.json()
        assert payload["strategy_id"] == strategy_id
        assert isinstance(payload.get("id"), int)
        assert payload.get("profit_loss") == 10.0
        assert payload.get("equity_curve")
        artifacts = payload.get("artifacts")
        assert isinstance(artifacts, list) and artifacts

        backtest_id = payload["id"]
        detail_response = client.get(f"/backtests/{backtest_id}")
        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["id"] == backtest_id
        assert detail_payload["strategy_id"] == strategy_id
        detail_artifacts = detail_payload.get("artifacts")
        assert isinstance(detail_artifacts, list) and detail_artifacts
        metrics_artifact = next(
            (item for item in detail_artifacts if item.get("type") == "metrics"),
            None,
        )
        assert metrics_artifact is not None
        assert isinstance(metrics_artifact.get("content"), dict)
    finally:
        backtester.output_dir = original_output
