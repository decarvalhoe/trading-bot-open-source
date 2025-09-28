from __future__ import annotations

import importlib
import os
from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from services.reports.app import config
from services.reports.app.database import get_engine, reset_engine, session_scope
from services.reports.app.main import app
from services.reports.app.tables import Base, Outcome, ReportDaily, ReportIntraday, ReportSnapshot
from schemas.report import StrategyName


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
                    strategy=StrategyName.ORB,
                    entry_price=190.0,
                    target_price=192.0,
                    stop_price=188.5,
                    outcome=Outcome.WIN,
                    pnl=2.0,
                ),
                ReportDaily(
                    symbol="AAPL",
                    session_date=date(2024, 3, 19),
                    strategy=StrategyName.ORB,
                    entry_price=191.0,
                    target_price=193.0,
                    stop_price=189.5,
                    outcome=Outcome.LOSS,
                    pnl=-1.2,
                ),
                ReportIntraday(
                    symbol="AAPL",
                    timestamp=datetime(2024, 3, 19, 9, 30),
                    strategy=StrategyName.IB,
                    entry_price=191.5,
                    target_price=194.0,
                    stop_price=190.0,
                    outcome=Outcome.WIN,
                    pnl=2.5,
                ),
                ReportIntraday(
                    symbol="AAPL",
                    timestamp=datetime(2024, 3, 19, 10, 0),
                    strategy=StrategyName.IB,
                    entry_price=191.7,
                    target_price=194.5,
                    stop_price=190.2,
                    outcome=Outcome.WIN,
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
    assert strategies == {StrategyName.ORB, StrategyName.IB}
