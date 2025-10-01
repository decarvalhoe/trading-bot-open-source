from __future__ import annotations

import importlib
import os
import sys
import types
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from services.reports.app import config
from services.reports.app.database import get_engine, reset_engine, session_scope
from services.reports.app.main import app
from services.reports.app.tables import (
    Base,
    ReportBenchmark,
    ReportDaily,
    ReportIntraday,
    ReportJob,
    ReportJobStatus,
    ReportSnapshot,
)
from schemas.report import StrategyName, TradeOutcome


def _configure_database(tmp_path: Path) -> None:
    db_path = tmp_path / "reports.db"
    os.environ["REPORTS_DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    config.get_settings.cache_clear()
    reset_engine()
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_sample_data() -> None:
    with session_scope() as session:
        session.add_all(
            [
                ReportDaily(
                    symbol="AAPL",
                    session_date=date(2024, 3, 18),
                    account="default",
                    strategy=StrategyName.ORB,
                    entry_price=190.0,
                    target_price=192.0,
                    stop_price=188.5,
                    outcome=TradeOutcome.WIN,
                    pnl=2.0,
                ),
                ReportDaily(
                    symbol="AAPL",
                    session_date=date(2024, 3, 19),
                    account="default",
                    strategy=StrategyName.ORB,
                    entry_price=191.0,
                    target_price=193.0,
                    stop_price=189.5,
                    outcome=TradeOutcome.LOSS,
                    pnl=-1.2,
                ),
                ReportDaily(
                    symbol="AAPL",
                    session_date=date(2024, 3, 20),
                    account="swing",
                    strategy=StrategyName.GAP_FILL,
                    entry_price=192.0,
                    target_price=195.0,
                    stop_price=190.0,
                    outcome=TradeOutcome.WIN,
                    pnl=0.0,
                ),
                ReportIntraday(
                    symbol="AAPL",
                    timestamp=datetime(2024, 3, 19, 9, 30),
                    strategy=StrategyName.IB,
                    entry_price=191.5,
                    target_price=194.0,
                    stop_price=190.0,
                    outcome=TradeOutcome.WIN,
                    pnl=2.5,
                ),
                ReportIntraday(
                    symbol="AAPL",
                    timestamp=datetime(2024, 3, 19, 10, 0),
                    strategy=StrategyName.IB,
                    entry_price=191.7,
                    target_price=194.5,
                    stop_price=190.2,
                    outcome=TradeOutcome.WIN,
                    pnl=2.0,
                ),
                ReportBenchmark(
                    account="default",
                    symbol="SPY",
                    session_date=date(2024, 3, 18),
                    return_value=1.0,
                ),
                ReportBenchmark(
                    account="default",
                    symbol="SPY",
                    session_date=date(2024, 3, 19),
                    return_value=-0.5,
                ),
            ]
        )


def _configure_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "pdf"
    os.environ["REPORTS_STORAGE_PATH"] = str(storage_dir)
    config.get_settings.cache_clear()
    return storage_dir


def _mock_weasyprint(monkeypatch: pytest.MonkeyPatch) -> type:
    class DummyHTML:
        last_rendered = ""

        def __init__(self, string: str):
            DummyHTML.last_rendered = string
            self.string = string

        def write_pdf(self) -> bytes:
            return b"%PDF-FAKE%"

    module = types.SimpleNamespace(HTML=DummyHTML)
    monkeypatch.setitem(sys.modules, "weasyprint", module)
    return DummyHTML


def test_reports_endpoint_computes_metrics(tmp_path: Path) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()

    with TestClient(app) as client:
        response = client.get("/reports/AAPL")
    assert response.status_code == 200
    body = response.json()

    daily_metrics = body["daily"]["strategies"][0]
    assert daily_metrics["strategy"] == "ORB"
    assert round(daily_metrics["probability"], 2) == 0.5
    assert round(daily_metrics["target"], 2) == 192.5
    assert round(daily_metrics["stop"], 2) == 189.0
    assert round(daily_metrics["expectancy"], 2) == 0.4

    intraday_metrics = body["intraday"]["strategies"][0]
    assert intraday_metrics["strategy"] == "IB"
    assert intraday_metrics["probability"] == 1.0
    assert round(intraday_metrics["target"], 2) == 194.25


def test_symbol_summary_endpoint_returns_combined_metrics(tmp_path: Path) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()

    with TestClient(app) as client:
        response = client.get("/symbols/AAPL/summary", params={"limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["report"]["symbol"] == "AAPL"

    risk = payload["risk"]
    assert round(risk["total_pnl"], 2) == 0.8
    assert round(risk["max_drawdown"], 2) == 1.2
    assert risk["incident_count"] == 1
    assert len(risk["recent"]) == 3
    loss_day = next(item for item in risk["recent"] if item["session_date"] == "2024-03-19")
    assert loss_day["incidents"], "Loss day should expose incident metadata"


def test_symbol_summary_returns_404_when_no_data(tmp_path: Path) -> None:
    _configure_database(tmp_path)

    with TestClient(app) as client:
        response = client.get("/symbols/UNKNOWN/summary")

    assert response.status_code == 404


def test_refresh_reports_creates_snapshots(tmp_path: Path) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()

    report_tasks = importlib.reload(importlib.import_module("services.reports.app.tasks"))
    report_tasks.refresh_reports()

    with session_scope() as session:
        snapshots = session.query(ReportSnapshot).all()
        strategies = {snapshot.strategy for snapshot in snapshots}
        count = len(snapshots)

    assert count
    assert strategies == {StrategyName.ORB, StrategyName.IB, StrategyName.GAP_FILL}


def test_daily_risk_report_endpoint(tmp_path: Path) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()

    with TestClient(app) as client:
        response = client.get("/reports/daily")
        assert response.status_code == 200
        payload = response.json()
        assert payload
        summary = payload[0]
        assert {"session_date", "account", "pnl", "max_drawdown", "incidents"} <= set(summary.keys())
        if summary["session_date"] == "2024-03-19":
            assert summary["incidents"], "Expected losing trade to be flagged as incident"

        csv_response = client.get("/reports/daily", params={"export": "csv"})
        assert csv_response.status_code == 200
        assert "session_date" in csv_response.text


def test_portfolio_performance_endpoint(tmp_path: Path) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()

    with TestClient(app) as client:
        response = client.get("/reports/performance")
        assert response.status_code == 200
        payload = response.json()
        assert payload

        default_account = next(item for item in payload if item["account"] == "default")
        assert default_account["start_date"] == "2024-03-18"
        assert default_account["end_date"] == "2024-03-19"
        assert default_account["observation_count"] == 2
        assert default_account["positive_days"] == 1
        assert default_account["negative_days"] == 1
        assert round(default_account["total_return"], 2) == 0.8
        assert round(default_account["volatility"], 2) == 1.6
        assert round(default_account["sharpe_ratio"], 2) == 0.25
        assert round(default_account["sortino_ratio"], 2) == 0.47
        assert round(default_account["alpha"], 2) == -0.13
        assert round(default_account["beta"], 2) == 2.13
        assert round(default_account["tracking_error"], 2) == 0.86
        assert round(default_account["max_drawdown"], 2) == 1.2

        swing_account = next(item for item in payload if item["account"] == "swing")
        assert swing_account["observation_count"] == 1
        assert swing_account["volatility"] == 0.0
        assert swing_account["sharpe_ratio"] == 0.0
        assert swing_account["sortino_ratio"] == 0.0
        assert swing_account["alpha"] == 0.0
        assert swing_account["beta"] == 0.0
        assert swing_account["tracking_error"] == 0.0

        filtered = client.get("/reports/performance", params={"account": "unknown"})
        assert filtered.status_code == 200
        assert filtered.json() == []


def test_render_symbol_report_to_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()
    _configure_storage(tmp_path)
    dummy_html = _mock_weasyprint(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/reports/AAPL/render",
            json={"report_type": "symbol", "timeframe": "both"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-FAKE%"
    assert "Content-Disposition" in response.headers
    stored_path = Path(response.headers["X-Report-Path"])
    assert stored_path.exists()
    assert stored_path.read_bytes() == b"%PDF-FAKE%"
    assert "AAPL" in stored_path.name
    assert dummy_html.last_rendered
    assert "AAPL" in dummy_html.last_rendered
    assert "Daily strategies" in dummy_html.last_rendered


def test_render_daily_risk_report_to_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()
    _configure_storage(tmp_path)
    dummy_html = _mock_weasyprint(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/reports/AAPL/render",
            json={"report_type": "daily", "account": "default", "limit": 10},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-FAKE%"
    assert "Daily risk summary" in dummy_html.last_rendered
    assert "Most recent 10 sessions" in dummy_html.last_rendered


def test_render_report_returns_404_when_no_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_database(tmp_path)
    _configure_storage(tmp_path)
    _mock_weasyprint(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/reports/UNKNOWN/render",
            json={"report_type": "symbol"},
        )

    assert response.status_code == 404


def test_generate_report_endpoint_creates_async_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()
    _configure_storage(tmp_path)

    tasks_module = importlib.reload(importlib.import_module("services.reports.app.tasks"))

    captured: dict[str, object] = {}

    def fake_delay(report_id: str, payload: dict[str, object]) -> None:
        captured["report_id"] = report_id
        captured["payload"] = payload

    monkeypatch.setattr(tasks_module.generate_report_job, "delay", fake_delay)

    with TestClient(app) as client:
        response = client.post(
            "/reports/generate",
            json={
                "symbol": "AAPL",
                "report_type": "symbol",
                "timeframe": "both",
                "mode": "async",
            },
        )

    assert response.status_code == 202
    body = response.json()
    job_id = body["job_id"]
    assert captured["report_id"] == job_id
    assert captured["payload"] == {
        "symbol": "AAPL",
        "options": {
            "report_type": "symbol",
            "timeframe": "both",
            "account": None,
            "limit": None,
            "mode": "async",
        },
    }

    with session_scope() as session:
        job = session.get(ReportJob, job_id)
        assert job is not None
        assert job.status == ReportJobStatus.PENDING
        assert job.parameters["report_type"] == "symbol"
        assert job.file_path is None


def test_generate_report_job_task_updates_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_database(tmp_path)
    _seed_sample_data()
    _configure_storage(tmp_path)
    dummy_html = _mock_weasyprint(monkeypatch)

    tasks_module = importlib.reload(importlib.import_module("services.reports.app.tasks"))

    with session_scope() as session:
        job = ReportJob(
            symbol="AAPL",
            parameters={
                "report_type": "symbol",
                "timeframe": "both",
                "account": None,
                "limit": None,
                "mode": "async",
            },
            status=ReportJobStatus.PENDING,
        )
        session.add(job)
        session.flush()
        job_id = job.id

    payload = {
        "symbol": "AAPL",
        "options": {
            "report_type": "symbol",
            "timeframe": "both",
            "account": None,
            "limit": None,
            "mode": "async",
        },
    }

    result_path = tasks_module.generate_report_job(job_id, payload)

    assert result_path is not None
    assert Path(result_path).exists()
    assert dummy_html.last_rendered

    with session_scope() as session:
        refreshed = session.get(ReportJob, job_id)
        assert refreshed is not None
        assert refreshed.status == ReportJobStatus.SUCCESS
        assert refreshed.file_path == result_path

    with TestClient(app) as client:
        client_get = client.get(f"/reports/jobs/{job_id}")

    assert client_get.status_code == 200
    payload = client_get.json()
    assert payload["status"] == "success"
    assert payload["resource"] == result_path
    assert payload["symbol"] == "AAPL"
