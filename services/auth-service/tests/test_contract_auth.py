import importlib.util
import secrets
import sys
import time
from pathlib import Path
from typing import Generator
from types import ModuleType

import pyotp
import pytest
from schemathesis import openapi
from sqlalchemy import select

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

MFATotp = helpers.MFATotp
TokenPair = helpers.TokenPair
TOTPSetup = helpers.TOTPSetup
User = helpers.User
app = helpers.app
get_db = helpers.get_db
totp_now = helpers.totp_now


@pytest.fixture()
def api_schema(session_factory) -> Generator:
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    schema = openapi.from_asgi("/openapi.json", app)
    try:
        yield schema
    finally:
        app.dependency_overrides.clear()


def test_openapi_document_is_valid(api_schema):
    api_schema.validate()
    paths = api_schema.raw_schema.get("paths", {})
    assert "/auth/register" in paths
    assert "/auth/login" in paths
    assert "/auth/totp/enable" in paths


def test_contract_flows_cover_totp_cycle(client, session_factory, api_schema):
    email = f"contract-{secrets.token_hex(4)}@example.com"
    password = "Passw0rd!"

    register_payload = {"email": email, "password": password}
    register_response = client.post("/auth/register", json=register_payload)
    assert register_response.status_code == 201

    login_payload = {"email": email, "password": password}
    first_login = client.post("/auth/login", json=login_payload)
    assert first_login.status_code == 200
    tokens = TokenPair.model_validate(first_login.json())

    setup_response = client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert setup_response.status_code == 200
    totp_setup = TOTPSetup.model_validate(setup_response.json())

    invalid_enable = client.post(
        "/auth/totp/enable",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
        params={"code": "000000"},
    )
    assert invalid_enable.status_code == 400

    valid_code = pyotp.TOTP(totp_setup.secret).now()
    enable_response = client.post(
        "/auth/totp/enable",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
        params={"code": valid_code},
    )
    assert enable_response.status_code == 200

    missing_totp = client.post("/auth/login", json=login_payload)
    assert missing_totp.status_code == 401

    timed_code = pyotp.TOTP(totp_setup.secret).now()
    login_with_totp = client.post(
        "/auth/login",
        json={"email": email, "password": password, "totp": timed_code},
    )
    assert login_with_totp.status_code == 200
    tokens = TokenPair.model_validate(login_with_totp.json())

    regenerate = client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
    )
    assert regenerate.status_code == 200
    regenerated = TOTPSetup.model_validate(regenerate.json())
    assert regenerated.secret != totp_setup.secret

    stale_code = pyotp.TOTP(totp_setup.secret).now()
    login_with_old_secret = client.post(
        "/auth/login",
        json={"email": email, "password": password, "totp": stale_code},
    )
    assert login_with_old_secret.status_code == 401

    fresh_code = pyotp.TOTP(regenerated.secret).now()
    reenable = client.post(
        "/auth/totp/enable",
        headers={"Authorization": f"Bearer {tokens.access_token}"},
        params={"code": fresh_code},
    )
    assert reenable.status_code == 200

    time.sleep(0.1)
    final_code = totp_now(regenerated.secret).now()
    final_login = client.post(
        "/auth/login",
        json={"email": email, "password": password, "totp": final_code},
    )
    assert final_login.status_code == 200
    TokenPair.model_validate(final_login.json())

    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        totp_row = session.get(MFATotp, user.id)
        assert totp_row is not None
        assert totp_row.enabled is True
        assert totp_row.secret == regenerated.secret
