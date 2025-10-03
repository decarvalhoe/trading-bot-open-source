import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from services.reports.app import config as reports_config
from services.reports.app.database import get_engine, reset_engine, session_scope
from services.reports.app.main import app as reports_app
from services.reports.app.tables import Base, ReportBacktest


def _configure_reports_database(tmp_path: Path) -> None:
    db_path = tmp_path / "reports.db"
    os.environ["REPORTS_DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    reports_config.get_settings.cache_clear()
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def reports_client(tmp_path: Path) -> TestClient:
    _configure_reports_database(tmp_path)
    with TestClient(reports_app) as client:
        client.get("/health")
        yield client


def _load_algo_main() -> Any:
    package_root = Path(__file__).resolve().parents[1] / "algo_engine"

    def _load_package(alias: str, path: Path) -> None:
        spec = importlib.util.spec_from_file_location(alias, path / "__init__.py")
        module = importlib.util.module_from_spec(spec)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[alias] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

    _load_package("algo_engine", package_root)
    _load_package("algo_engine.app", package_root / "app")
    _load_package("algo_engine.app.strategies", package_root / "app" / "strategies")

    loader = importlib.machinery.SourceFileLoader(
        "algo_engine.app.main",
        str(package_root / "app" / "main.py"),
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


ALGO_MAIN = _load_algo_main()


def _build_reports_transport(client: TestClient) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        json_payload = None
        if request.content:
            try:
                json_payload = json.loads(request.content.decode())
            except ValueError:
                json_payload = None
        response = client.request(
            request.method,
            request.url.path,
            json=json_payload,
        )
        return httpx.Response(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
        )

    transport = httpx.MockTransport(handler)
    return httpx.Client(base_url=str(client.base_url), transport=transport)


def test_backtest_results_are_published_and_visible(
    reports_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")

    publisher_client = _build_reports_transport(reports_client)
    publisher = ALGO_MAIN.ReportsPublisher(
        client=publisher_client, base_url=str(reports_client.base_url)
    )
    monkeypatch.setattr(ALGO_MAIN, "reports_publisher", publisher, raising=False)

    # Reset strategy repository for isolation
    ALGO_MAIN.strategy_repository.clear()
    ALGO_MAIN.orchestrator.restore_recent_executions([])

    with TestClient(ALGO_MAIN.app) as algo_client:
        create_payload = {
            "name": "Momentum ORB",
            "strategy_type": "orb",
            "parameters": {"symbol": "AAPL"},
            "metadata": {"account": "backtest-account", "report_strategy": "ORB"},
        }
        create_response = algo_client.post("/strategies", json=create_payload)
        assert create_response.status_code == 201
        strategy_id = create_response.json()["id"]

        market_data = [
            {"close": 101},
            {"close": 103},
            {"close": 99},
            {"close": 112},
        ]
        backtest_response = algo_client.post(
            f"/strategies/{strategy_id}/backtest",
            json={"market_data": market_data, "initial_balance": 10_000.0},
        )
        assert backtest_response.status_code == 200

    with session_scope() as session:
        stored = session.query(ReportBacktest).one()
        assert stored.strategy_id == strategy_id
        assert stored.account == "backtest-account"
        assert stored.symbol == "AAPL"
        assert (
            pytest.approx(stored.total_return, rel=1e-6) == backtest_response.json()["total_return"]
        )

    daily = reports_client.get("/reports/daily").json()
    assert any(entry["account"] == "backtest-account" for entry in daily)

    performance = reports_client.get("/reports/performance").json()
    assert any(entry["account"] == "backtest-account" for entry in performance)

    report = reports_client.get("/reports/AAPL").json()
    assert report["daily"]["strategies"][0]["strategy"] == "ORB"

    publisher.close()
