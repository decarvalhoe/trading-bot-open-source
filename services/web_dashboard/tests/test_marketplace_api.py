from __future__ import annotations

import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

from .utils import load_dashboard_app


@pytest.fixture()
def client() -> TestClient:
    app = load_dashboard_app()
    return TestClient(app)


def test_marketplace_listings_proxy_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, object]] = []
    raw_payload = {
        "items": [
            {
                "id": "123",
                "name": "Alpha Wave",
                "owner": 77,
                "price": "19.95",
                "currency": "eur",
                "description": "  Swing focus  ",
                "performance": "12.34",
                "risk": "1.2",
                "reviews": [{"rating": "4"}, {"rating": 5}],
            }
        ]
    }

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> "DummyAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, params=None, headers=None) -> httpx.Response:
            requests.append({"url": url, "params": params, "headers": headers})
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=raw_payload, request=request)

    data_module = importlib.import_module("web_dashboard.app.data")
    monkeypatch.setattr(data_module.httpx, "AsyncClient", DummyAsyncClient)

    params = {
        "search": "alpha",
        "min_performance": "10",
        "max_risk": "2",
        "max_price": "500",
        "sort": "performance_desc",
    }
    response = client.get("/marketplace/listings", params=params)

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": 123,
            "strategy_name": "Alpha Wave",
            "owner_id": "77",
            "price_cents": 1995,
            "currency": "EUR",
            "description": "Swing focus",
            "performance_score": 12.34,
            "risk_score": 1.2,
            "average_rating": 4.5,
            "reviews_count": 2,
        }
    ]
    assert requests == [
        {
            "url": "http://marketplace:8000/marketplace/listings",
            "params": {
                "search": "alpha",
                "min_performance": 10.0,
                "max_risk": 2.0,
                "max_price": 500.0,
                "sort": "performance_desc",
            },
            "headers": {"Accept": "application/json"},
        }
    ]


def test_marketplace_listings_proxy_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> "FailingAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, params=None, headers=None) -> httpx.Response:
            request = httpx.Request("GET", url)
            raise httpx.ConnectError("unreachable", request=request)

    data_module = importlib.import_module("web_dashboard.app.data")
    monkeypatch.setattr(data_module.httpx, "AsyncClient", FailingAsyncClient)

    response = client.get("/marketplace/listings")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["message"] == "Impossible de contacter le service marketplace."
    assert detail["context"]["url"] == "http://marketplace:8000/marketplace/listings"
    assert "error" in detail["context"]["payload"]


def test_marketplace_reviews_proxy_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    raw_payload = [
        {
            "rating": "4.5",
            "comment": "  Très bien  ",
            "created_at": "2024-01-15T10:30:00",
            "user_id": 42,
        },
        {
            "review_id": "beta",
            "rating": 6,
            "comment": "",
        },
    ]

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> "DummyAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, params=None, headers=None) -> httpx.Response:
            calls.append({"url": url, "params": params, "headers": headers})
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=raw_payload, request=request)

    data_module = importlib.import_module("web_dashboard.app.data")
    monkeypatch.setattr(data_module.httpx, "AsyncClient", DummyAsyncClient)

    response = client.get("/marketplace/listings/456/reviews")

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": "review-456-0",
            "listing_id": 456,
            "rating": 4.5,
            "comment": "Très bien",
            "created_at": "2024-01-15T10:30:00+00:00",
            "reviewer_id": "42",
        },
        {
            "id": "beta",
            "listing_id": 456,
            "rating": 5.0,
            "comment": None,
            "created_at": "1970-01-01T00:00:00+00:00",
            "reviewer_id": None,
        },
    ]
    assert calls == [
        {
            "url": "http://marketplace:8000/marketplace/listings/456/reviews",
            "params": None,
            "headers": {"Accept": "application/json"},
        }
    ]


def test_marketplace_reviews_proxy_error_from_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ErroringAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> "ErroringAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, *, params=None, headers=None) -> httpx.Response:
            request = httpx.Request("GET", url)
            payload = {"detail": "Listing introuvable"}
            return httpx.Response(404, json=payload, request=request)

    data_module = importlib.import_module("web_dashboard.app.data")
    monkeypatch.setattr(data_module.httpx, "AsyncClient", ErroringAsyncClient)

    response = client.get("/marketplace/listings/999/reviews")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message"] == "Listing introuvable"
    assert detail["context"]["status_code"] == 404
    assert detail["context"]["url"] == "http://marketplace:8000/marketplace/listings/999/reviews"
