from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_bootstrap_demo_smoke() -> None:
    """Run the bootstrap script against a live stack when available."""

    auth_url = os.getenv("BOOTSTRAP_TEST_AUTH_URL")
    if not auth_url:
        pytest.skip("Bootstrap demo stack not available")

    symbol = os.getenv("BOOTSTRAP_TEST_SYMBOL", "BTCUSDT")
    quantity = os.getenv("BOOTSTRAP_TEST_QUANTITY", "0.1")

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO_ROOT))

    command = [
        sys.executable,
        "-m",
        "scripts.dev.bootstrap_demo",
        symbol,
        quantity,
        "--auth-url",
        auth_url,
        "--user-url",
        os.getenv("BOOTSTRAP_TEST_USER_URL", "http://127.0.0.1:8012"),
        "--algo-url",
        os.getenv("BOOTSTRAP_TEST_ALGO_URL", "http://127.0.0.1:8014"),
        "--order-router-url",
        os.getenv("BOOTSTRAP_TEST_ORDER_ROUTER_URL", "http://127.0.0.1:8013"),
        "--reports-url",
        os.getenv("BOOTSTRAP_TEST_REPORTS_URL", "http://127.0.0.1:8016"),
        "--dashboard-url",
        os.getenv("BOOTSTRAP_TEST_DASHBOARD_URL", "http://127.0.0.1:8022"),
        "--streaming-url",
        os.getenv("BOOTSTRAP_TEST_STREAMING_URL", "http://127.0.0.1:8019"),
        "--billing-url",
        os.getenv("BOOTSTRAP_TEST_BILLING_URL", "http://127.0.0.1:8005"),
        "--alerts-token",
        os.getenv("BOOTSTRAP_TEST_ALERTS_TOKEN", os.getenv("WEB_DASHBOARD_ALERTS_TOKEN", "demo-alerts-token")),
        "--streaming-token",
        os.getenv("BOOTSTRAP_TEST_STREAMING_TOKEN", os.getenv("STREAMING_SERVICE_TOKEN_REPORTS", "reports-token")),
        "--skip-billing-setup",
    ]

    process = subprocess.run(command, capture_output=True, text=True, env=env, check=True)
    summary = json.loads(process.stdout)

    dashboard_url = os.getenv("BOOTSTRAP_TEST_DASHBOARD_URL")
    if dashboard_url:
        response = httpx.get(f"{dashboard_url.rstrip('/')}/alerts", timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        assert any(alert.get("id") == summary["alert"].get("id") for alert in items)
