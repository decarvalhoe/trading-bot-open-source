from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

from sqlalchemy import select

_service_root = Path(__file__).resolve().parents[1]
_package_name = "auth_service_app"
_repo_root = _service_root.parents[1]

if str(_repo_root) not in sys.path:
    sys.path.append(str(_repo_root))

if _package_name not in sys.modules:
    _package_spec = importlib.util.spec_from_file_location(
        _package_name,
        _service_root / "app" / "__init__.py",
        submodule_search_locations=[str(_service_root / "app")],
    )
    assert _package_spec and _package_spec.loader
    _package_module = importlib.util.module_from_spec(_package_spec)
    sys.modules[_package_name] = _package_module
    _package_spec.loader.exec_module(_package_module)  # type: ignore[arg-type]

main = importlib.import_module(f"{_package_name}.main")
models = importlib.import_module(f"{_package_name}.models")
schemas = importlib.import_module(f"{_package_name}.schemas")
security = importlib.import_module(f"{_package_name}.security")
get_db = importlib.import_module("libs.db.db").get_db

app = main.app  # type: ignore[attr-defined]
Base = models.Base
MFATotp = models.MFATotp
Role = models.Role
User = models.User
UserRole = models.UserRole

totp_now = security.totp_now
TokenPair = schemas.TokenPair
LoginRequest = schemas.LoginRequest
RegisterRequest = schemas.RegisterRequest
TOTPSetup = schemas.TOTPSetup
Me = schemas.Me


def create_user_with_role(session, email: str = "user@example.com", password: str = "secret") -> User:
    user = User(email=email, password_hash=main.hash_password(password))
    session.add(user)

    role = session.scalar(select(Role).where(Role.name == "user"))
    if not role:
        role = Role(name="user")
        session.add(role)
        session.flush()

    session.add(UserRole(user_id=user.id, role_id=role.id))
    session.commit()
    session.refresh(user)
    return user
