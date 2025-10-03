from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient

import os

os.environ.setdefault("TRADINGVIEW_HMAC_SECRET", "test-secret")

from services.market_data.app.main import (  # noqa: E402
    app,
    get_topstep_adapter,
)


class TopStepAdapterFake:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, method: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((method, args, kwargs))

    async def get_account_metrics(self, account_id: str) -> dict[str, Any]:
        self._record("get_account_metrics", account_id)
        return {"balance": 1000, "account": account_id}

    async def get_performance_history(
        self,
        account_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        self._record("get_performance_history", account_id, start, end)
        return {"points": [start, end]}

    async def get_risk_rules(self, account_id: str) -> dict[str, Any]:
        self._record("get_risk_rules", account_id)
        return {"max_drawdown": 100}


def _override_dependency(fake: TopStepAdapterFake) -> None:
    async def dependency() -> AsyncIterator[TopStepAdapterFake]:
        yield fake

    app.dependency_overrides[get_topstep_adapter] = dependency


def test_topstep_metrics_endpoint_returns_payload() -> None:
    fake = TopStepAdapterFake()
    _override_dependency(fake)
    client = TestClient(app)
    try:
        response = client.get("/market-data/topstep/accounts/acct-1/metrics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["balance"] == 1000
    assert fake.calls[0][0] == "get_account_metrics"


def test_topstep_performance_endpoint_passes_query_params() -> None:
    fake = TopStepAdapterFake()
    _override_dependency(fake)
    client = TestClient(app)
    try:
        response = client.get(
            "/market-data/topstep/accounts/acct-2/performance",
            params={"start": "2024-01-01", "end": "2024-02-01"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["performance"]["points"] == ["2024-01-01", "2024-02-01"]
    assert fake.calls[0][1][1:] == ("2024-01-01", "2024-02-01")


def test_topstep_risk_rules_endpoint_handles_upstream_errors() -> None:
    class FailingAdapter(TopStepAdapterFake):
        async def get_risk_rules(self, account_id: str) -> dict[str, Any]:
            raise HTTPException(status_code=404, detail="not found")

    fake = FailingAdapter()

    async def dependency() -> AsyncIterator[FailingAdapter]:
        yield fake

    app.dependency_overrides[get_topstep_adapter] = dependency

    client = TestClient(app)
    try:
        response = client.get("/market-data/topstep/accounts/acct-3/risk-rules")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "not found"
