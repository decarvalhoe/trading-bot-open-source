import asyncio
import sys
from pathlib import Path

import pytest
import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.market_data.app.main import app, get_topstep_adapter


class FakeTopStepAdapter:
    def __init__(self) -> None:
        self.closed = False
        self.metrics_requests: list[str] = []
        self.performance_requests: list[tuple[str, dict[str, str | None]]] = []
        self.risk_rule_requests: list[str] = []

    async def get_account_metrics(self, account_id: str) -> dict[str, int]:
        self.metrics_requests.append(account_id)
        return {"balance": 1000}

    async def get_performance_history(
        self,
        account_id: str,
        *,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        self.performance_requests.append(
            (account_id, {"start": start, "end": end})
        )
        return {"trades": []}

    async def get_risk_rules(self, account_id: str) -> dict[str, list[str]]:
        self.risk_rule_requests.append(account_id)
        return {"rules": ["max_daily_loss"]}

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def override_topstep_adapter() -> FakeTopStepAdapter:
    adapter = FakeTopStepAdapter()

    async def dependency():
        try:
            yield adapter
        finally:
            await adapter.aclose()

    app.dependency_overrides[get_topstep_adapter] = dependency
    try:
        yield adapter
    finally:
        app.dependency_overrides.pop(get_topstep_adapter, None)


def test_get_topstep_metrics(
    override_topstep_adapter: FakeTopStepAdapter,
) -> None:
    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/market-data/topstep/accounts/demo/metrics")

        assert response.status_code == 200
        assert response.json() == {
            "account_id": "demo",
            "metrics": {"balance": 1000},
        }
        assert override_topstep_adapter.metrics_requests == ["demo"]
        assert override_topstep_adapter.closed is True

    asyncio.run(_run())


def test_get_topstep_performance(
    override_topstep_adapter: FakeTopStepAdapter,
) -> None:
    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/market-data/topstep/accounts/demo/performance",
                params={"start": "2024-01-01", "end": "2024-01-31"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "account_id": "demo",
            "performance": {"trades": []},
            "start": "2024-01-01",
            "end": "2024-01-31",
        }
        assert override_topstep_adapter.performance_requests == [
            ("demo", {"start": "2024-01-01", "end": "2024-01-31"})
        ]
        assert override_topstep_adapter.closed is True

    asyncio.run(_run())


def test_get_topstep_risk_rules(
    override_topstep_adapter: FakeTopStepAdapter,
) -> None:
    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/market-data/topstep/accounts/demo/risk-rules"
            )

        assert response.status_code == 200
        assert response.json() == {
            "account_id": "demo",
            "risk_rules": {"rules": ["max_daily_loss"]},
        }
        assert override_topstep_adapter.risk_rule_requests == ["demo"]
        assert override_topstep_adapter.closed is True

    asyncio.run(_run())
