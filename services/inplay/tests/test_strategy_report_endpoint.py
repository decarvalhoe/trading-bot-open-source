from __future__ import annotations

from typing import Dict, Tuple
from unittest.mock import patch

import httpx
import pytest

from services.inplay.app.config import Settings
from services.inplay.app.main import create_app
from services.inplay.app.schemas import TickPayload

pytestmark = pytest.mark.anyio


class DummyAsyncClient:
    def __init__(self, responses: Dict[str, Tuple[int, dict[str, object]]]):
        self._responses = responses

    async def __aenter__(self) -> "DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def get(self, url: str, timeout: float | None = None) -> httpx.Response:
        status_code, payload = self._responses.get(url, (404, {}))
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=status_code, json=payload, request=request)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_strategy_report_endpoint_returns_combined_payload() -> None:
    settings = Settings(
        watchlists={"momentum": ["AAPL"]},
        reports_base_url="http://reports.test/",
        market_data_base_url="http://market.test/",
    )
    app = create_app(settings=settings, stream_factory=None)
    state = app.state.inplay_state

    payload = TickPayload(
        symbol="AAPL",
        strategy="ORB",
        entry=190.0,
        target=191.0,
        stop=189.0,
        probability=0.6,
        status="pending",
        session="london",
        watchlists=["momentum"],
    )
    await state.apply_tick(payload)

    responses = {
        "http://reports.test/symbols/AAPL/summary": (
            200,
            {
                "symbol": "AAPL",
                "report": {"symbol": "AAPL", "daily": {}},
                "risk": {"total_pnl": 5.2},
            },
        ),
        "http://market.test/spot/AAPL": (
            200,
            {"symbol": "AAPL", "bid": 189.9, "ask": 190.1},
        ),
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        with patch(
            "services.inplay.app.main.httpx.AsyncClient",
            lambda *args, **kwargs: DummyAsyncClient(responses),
        ):
            response = await client.get("/inplay/setups/AAPL/ORB")

    assert response.status_code == 200
    payload_json = response.json()
    assert payload_json["symbol"] == "AAPL"
    assert payload_json["strategy"] == "ORB"
    assert payload_json["setup"]["report_url"].endswith("/ORB")
    assert payload_json["report"] == {"symbol": "AAPL", "daily": {}}
    assert payload_json["risk"] == {"total_pnl": 5.2}
    assert payload_json["market"] == {"symbol": "AAPL", "bid": 189.9, "ask": 190.1}


async def test_strategy_report_endpoint_returns_404_when_setup_missing() -> None:
    settings = Settings(watchlists={"momentum": ["AAPL"]})
    app = create_app(settings=settings, stream_factory=None)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/inplay/setups/AAPL/ORB")

    assert response.status_code == 404
    assert response.json()["detail"] == "Setup introuvable"
