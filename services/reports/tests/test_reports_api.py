from __future__ import annotations

import importlib
import os
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from services.reports.app import config
from services.reports.app.database import get_engine, reset_engine, session_scope
from services.reports.app.main import app
from services.reports.app.tables import Base, ReportDaily, ReportIntraday, ReportSnapshot
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
            ]
        )


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
        assert round(default_account["max_drawdown"], 2) == 1.2

        swing_account = next(item for item in payload if item["account"] == "swing")
        assert swing_account["observation_count"] == 1
        assert swing_account["volatility"] == 0.0
        assert swing_account["sharpe_ratio"] == 0.0

        filtered = client.get("/reports/performance", params={"account": "unknown"})
        assert filtered.status_code == 200
        assert filtered.json() == []
