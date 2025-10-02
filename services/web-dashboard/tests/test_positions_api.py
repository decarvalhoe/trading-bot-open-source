from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from schemas.market import ExecutionStatus, ExecutionVenue, OrderSide
from schemas.order_router import ExecutionReport, PositionCloseResponse, PositionsResponse

from .utils import load_dashboard_app


@pytest.fixture()
def client():
    app = load_dashboard_app()
    return TestClient(app)


def _build_close_response(symbol: str = "ADAUSDT", side: OrderSide = OrderSide.SELL) -> PositionCloseResponse:
    report = ExecutionReport(
        order_id="close-1",
        status=ExecutionStatus.FILLED,
        broker="binance",
        venue=ExecutionVenue.BINANCE_SPOT,
        symbol=symbol,
        side=side,
        quantity=3.0,
        filled_quantity=3.0,
        avg_price=1.5,
        submitted_at=datetime.now(timezone.utc),
    )
    return PositionCloseResponse(order=report, positions=PositionsResponse(items=[], as_of=datetime.now(timezone.utc)))


def test_close_position_endpoint_proxies_order_router(client, monkeypatch):
    responses = []

    class DummyOrderRouterClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def __enter__(self) -> "DummyOrderRouterClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def close_position(self, position_id: str, *, target_quantity: float | None = None) -> PositionCloseResponse:
            responses.append((position_id, target_quantity))
            return _build_close_response(symbol="SOLUSDT")

    monkeypatch.setattr("web_dashboard.app.main.OrderRouterClient", DummyOrderRouterClient)

    payload = {"target_quantity": 1.0}
    response = client.post("/positions/position-alpha/close", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["order"]["symbol"] == "SOLUSDT"
    assert responses == [("position-alpha", 1.0)]


def test_close_position_endpoint_handles_router_errors(client, monkeypatch):
    class FailingOrderRouterClient:
        def __enter__(self) -> "FailingOrderRouterClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def close_position(self, position_id: str, *, target_quantity: float | None = None) -> PositionCloseResponse:
            raise httpx.HTTPError("unreachable")

    monkeypatch.setattr("web_dashboard.app.main.OrderRouterClient", FailingOrderRouterClient)

    response = client.post("/positions/test-id/close")

    assert response.status_code == 502
    assert "routeur" in response.json()["detail"].lower()
