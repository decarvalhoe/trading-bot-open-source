import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

CURRENT_DIR = Path(__file__).resolve().parent

HELPERS_NAME = "auth_service_test_helpers"
HELPERS_PATH = CURRENT_DIR / "_helpers.py"


def _load_helpers(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[arg-type]
    return module


helpers = _load_helpers(HELPERS_NAME, HELPERS_PATH)

Base = helpers.Base
app = helpers.app
get_db = helpers.get_db
main = helpers.main


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield TestingSessionLocal
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_password_hashing(monkeypatch):
    def _hash(password: str) -> str:
        return f"hashed::{password}"

    def _verify(password: str, hashed: str) -> bool:
        return hashed == f"hashed::{password}"

    monkeypatch.setattr(main, "hash_password", _hash)
    monkeypatch.setattr(main, "verify_password", _verify)
