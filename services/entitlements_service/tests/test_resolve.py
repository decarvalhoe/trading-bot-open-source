from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
import importlib.util
import sys
from pathlib import Path
import types
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from infra import EntitlementsBase, Feature, Plan, PlanFeature, Subscription
from libs.db import db as db_module

MODULE_DIR = Path(__file__).resolve().parents[1]
PACKAGE_NAME = MODULE_DIR.name.replace('-', '_')
PACKAGE_ROOT = f"services.{PACKAGE_NAME}"

if PACKAGE_ROOT not in sys.modules:
    package = types.ModuleType(PACKAGE_ROOT)
    package.__path__ = [str(MODULE_DIR)]
    sys.modules[PACKAGE_ROOT] = package
    app_package = types.ModuleType(f"{PACKAGE_ROOT}.app")
    app_package.__path__ = [str(MODULE_DIR / 'app')]
    sys.modules[f"{PACKAGE_ROOT}.app"] = app_package

spec = importlib.util.spec_from_file_location(f"{PACKAGE_ROOT}.app.main", MODULE_DIR / 'app' / 'main.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
app = module.app


@pytest.fixture(autouse=True)
def setup_db():
    EntitlementsBase.metadata.create_all(bind=db_module.engine)
    try:
        yield
    finally:
        EntitlementsBase.metadata.drop_all(bind=db_module.engine)


@pytest.fixture
def session() -> Session:
    with db_module.SessionLocal() as session:
        yield session


def seed_plan(session: Session):
    plan = Plan(code="pro", name="Pro", stripe_price_id="price_pro")
    feature_cap = Feature(code="can.use_ibkr", name="Use IBKR", kind="capability")
    feature_quota = Feature(code="quota.active_algos", name="Active algos", kind="quota")
    session.add_all([plan, feature_cap, feature_quota])
    session.flush()
    session.add_all(
        [
            PlanFeature(plan_id=plan.id, feature_id=feature_cap.id),
            PlanFeature(plan_id=plan.id, feature_id=feature_quota.id, limit=10),
        ]
    )
    session.add(Subscription(customer_id="cus_321", plan_id=plan.id, status="active"))
    session.commit()


def test_resolve_entitlements(session: Session):
    seed_plan(session)
    client = TestClient(app)

    response = client.get("/entitlements/resolve", params={"customer_id": "cus_321"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["capabilities"]["can.use_ibkr"] is True
    assert payload["quotas"]["quota.active_algos"] == 10


def test_resolve_empty_when_missing_subscription():
    client = TestClient(app)
    response = client.get("/entitlements/resolve", params={"customer_id": "unknown"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["capabilities"] == {}
    assert payload["quotas"] == {}
