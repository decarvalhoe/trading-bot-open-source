"""Pytest fixtures for the order router service tests."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from infra.trading_models import Execution as ExecutionModel, Order as OrderModel, TradingBase

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_package(alias: str, path: Path) -> None:
    """Load a namespace package from an arbitrary path."""
    sys.modules.pop(alias, None)
    spec = importlib.util.spec_from_file_location(alias, path / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[alias] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]


def _load_main_module() -> object:
    """Import the FastAPI application module under a stable alias."""
    _load_package("order_router", PACKAGE_ROOT)
    _load_package("order_router.app", PACKAGE_ROOT / "app")
    _load_package("order_router.app.brokers", PACKAGE_ROOT / "app" / "brokers")
    sys.modules.pop("order_router.app.main", None)
    spec = importlib.util.spec_from_file_location(
        "order_router.app.main", PACKAGE_ROOT / "app" / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["order_router.app.main"] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


@pytest.fixture(scope="session")
def db_module(tmp_path_factory: pytest.TempPathFactory):
    """Configure a dedicated SQLite database for the test session."""
    db_path = tmp_path_factory.mktemp("order_router_db") / "test.sqlite"
    os.environ.setdefault("ENTITLEMENTS_BYPASS", "1")
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"

    module = importlib.import_module("libs.db.db")
    module = importlib.reload(module)
    TradingBase.metadata.create_all(module.engine)
    yield module
    TradingBase.metadata.drop_all(module.engine)
    module.engine.dispose()


@pytest.fixture(scope="session")
def app_module(db_module) -> object:  # type: ignore[override]
    """Load the FastAPI application once for the test session."""
    return _load_main_module()


@pytest.fixture(scope="session")
def app(app_module) -> object:  # type: ignore[override]
    return app_module.app


@pytest.fixture(scope="session")
def router(app_module) -> object:  # type: ignore[override]
    return app_module.router


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(db_module) -> Generator[Session, None, None]:
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_database(db_module, router) -> Generator[None, None, None]:
    """Ensure each test starts from an empty persistence layer."""
    session = db_module.SessionLocal()
    try:
        session.query(ExecutionModel).delete()
        session.query(OrderModel).delete()
        session.commit()
    finally:
        session.close()

    router.update_state(mode="paper", limit=1_000_000.0)
    router._state.notional_routed = 0.0  # type: ignore[attr-defined]
    router.set_stop_loss("default", 50_000.0)

    yield

    session = db_module.SessionLocal()
    try:
        session.query(ExecutionModel).delete()
        session.query(OrderModel).delete()
        session.commit()
    finally:
        session.close()
