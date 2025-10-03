import os
import urllib.parse
from datetime import datetime, timezone
from typing import Iterable

from fastapi import Depends, FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError
from sqlalchemy.orm import Session
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from .schemas import (
    LoginRequest,
    RegisterRequest,
    TokenPair,
    Me,
    TOTPSetup,
    TokenRefreshRequest,
)
from .security import (
    hash_password,
    verify_password,
    create_token_pair,
    generate_totp_secret,
    totp_now,
    verify_token,
    validate_password_requirements,
    PASSWORD_REQUIREMENTS_MESSAGE,
)
from .models import User, Role, UserRole, MFATotp
from .deps import get_current_user, require_roles
from libs.db.db import get_db
from libs.entitlements import install_entitlements_middleware
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics

configure_logging("auth-service")


def _auth_path(*segments: str) -> str:
    """Join one or more path segments onto the "/auth" prefix."""

    joined = "/".join(segment.strip("/") for segment in segments if segment)
    return f"/auth/{joined}" if joined else "/auth"


AUTH_SKIP_ENDPOINTS = (
    _auth_path("login"),
    _auth_path("register"),
    _auth_path("refresh"),
    _auth_path("me"),
    _auth_path("totp", "setup"),
    _auth_path("totp", "enable"),
)


DOCS_ENDPOINTS = ("/docs", "/redoc", "/openapi.json")


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return None


def _parse_env_list(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default
    parsed = [item.strip() for item in value.split(",") if item.strip()]
    return parsed or default


def _parse_env_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _normalise_root_path(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    if not cleaned or cleaned == "/":
        return ""
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned


def _normalise_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return path


def _extend_with_root_path(paths: Iterable[str], root_path: str) -> tuple[str, ...]:
    normalised = []
    seen: set[str] = set()
    for path in paths:
        cleaned = _normalise_path(path)
        if cleaned not in seen:
            normalised.append(cleaned)
            seen.add(cleaned)
        if root_path:
            prefixed = _normalise_path(f"{root_path.rstrip('/')}{cleaned}")
            if prefixed not in seen:
                normalised.append(prefixed)
                seen.add(prefixed)
    return tuple(normalised)


enable_docs = _parse_env_bool(_first_env("AUTH_SERVICE_ENABLE_DOCS", "ENABLE_DOCS"), True)
docs_url = "/docs" if enable_docs else None
redoc_url = "/redoc" if enable_docs else None
openapi_url = "/openapi.json" if enable_docs else None


root_path = _normalise_root_path(_first_env("AUTH_SERVICE_ROOT_PATH", "ROOT_PATH"))


app = FastAPI(
    title="Auth Service",
    version="0.1.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
    root_path=root_path or "",
)
install_entitlements_middleware(
    app,
    required_capabilities=["can.use_auth"],
    required_quotas={"quota.active_algos": 1},
    skip_paths=(
        _extend_with_root_path(AUTH_SKIP_ENDPOINTS, root_path)
        + (_extend_with_root_path(DOCS_ENDPOINTS, root_path) if enable_docs else ())
    ),
)
app.add_middleware(RequestContextMiddleware, service_name="auth-service")
setup_metrics(app, service_name="auth-service")


cors_allow_origins = _parse_env_list(
    _first_env("AUTH_SERVICE_ALLOWED_ORIGINS", "ALLOWED_ORIGINS"),
    ["http://localhost:3000", "http://localhost:8022"],
)
cors_allow_methods = _parse_env_list(
    _first_env("AUTH_SERVICE_ALLOWED_METHODS", "ALLOWED_METHODS"),
    ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
cors_allow_headers = _parse_env_list(
    _first_env("AUTH_SERVICE_ALLOWED_HEADERS", "ALLOWED_HEADERS"),
    ["Authorization", "Content-Type"],
)
cors_allow_credentials = _parse_env_bool(
    _first_env("AUTH_SERVICE_ALLOW_CREDENTIALS", "ALLOW_CREDENTIALS"),
    True,
)

session_secret = _first_env("AUTH_SERVICE_SESSION_SECRET", "SESSION_SECRET")
if not session_secret:
    session_secret = os.getenv("JWT_SECRET", "dev-session-secret")

session_cookie_name = _first_env(
    "AUTH_SERVICE_SESSION_COOKIE_NAME",
    "SESSION_COOKIE_NAME",
) or "session"
session_cookie_domain = _first_env(
    "AUTH_SERVICE_SESSION_COOKIE_DOMAIN",
    "SESSION_COOKIE_DOMAIN",
)
session_cookie_path = _first_env(
    "AUTH_SERVICE_SESSION_COOKIE_PATH",
    "SESSION_COOKIE_PATH",
) or (root_path or "/")
session_same_site = (
    _first_env(
        "AUTH_SERVICE_SESSION_COOKIE_SAMESITE",
        "SESSION_COOKIE_SAMESITE",
    )
    or "none"
).lower()
if session_same_site not in {"lax", "strict", "none"}:
    session_same_site = "none"
session_https_only = _parse_env_bool(
    _first_env(
        "AUTH_SERVICE_SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_SECURE",
    ),
    False,
)
session_max_age_env = _first_env(
    "AUTH_SERVICE_SESSION_MAX_AGE",
    "SESSION_MAX_AGE",
)
session_max_age: int | None
try:
    session_max_age = int(session_max_age_env) if session_max_age_env else None
except ValueError:
    session_max_age = None

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    session_cookie=session_cookie_name,
    domain=session_cookie_domain,
    path=session_cookie_path,
    same_site=session_same_site,
    https_only=session_https_only,
    max_age=session_max_age,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_methods=cors_allow_methods,
    allow_headers=cors_allow_headers,
    allow_credentials=cors_allow_credentials,
)


@app.get("/health")
def health():
    return {"status": "ok"}

def _ensure_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@app.post("/auth/register", response_model=Me, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    valid, message = validate_password_requirements(payload.password)
    if not valid:
        raise HTTPException(status_code=400, detail=message or PASSWORD_REQUIREMENTS_MESSAGE)
    now = datetime.now(timezone.utc)
    u = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        created_at=now,
        updated_at=now,
    )
    db.add(u); db.commit(); db.refresh(u)

    role = db.scalar(select(Role).where(Role.name == "user"))
    if not role:
        role = Role(name="user")
        db.add(role); db.commit(); db.refresh(role)

    db.add(UserRole(user_id=u.id, role_id=role.id)); db.commit()
    return Me(
        id=u.id,
        email=u.email,
        roles=["user"],
        created_at=_ensure_timezone(u.created_at),
        updated_at=_ensure_timezone(u.updated_at),
    )

@app.post("/auth/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == payload.email))
    if not u or not verify_password(payload.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    totp_row = db.get(MFATotp, u.id)
    if totp_row and totp_row.enabled:
        if not payload.totp or not totp_now(totp_row.secret).verify(payload.totp):
            raise HTTPException(status_code=401, detail="Invalid or missing TOTP")

    roles = [r.name for r in db.execute(
        select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == u.id)
    ).scalars().all()]

    access, refresh = create_token_pair(u.id, roles)
    return TokenPair(access_token=access, refresh_token=refresh)


@app.post("/auth/refresh", response_model=TokenPair)
def refresh(
    payload: TokenRefreshRequest | None = None,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    token = None
    if payload and payload.refresh_token:
        token = payload.refresh_token
    elif authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            token = credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token required")

    try:
        decoded = verify_token(token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    sub = decoded.get("sub")
    if not isinstance(sub, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    u = db.get(User, sub)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    roles = [
        r.name
        for r in db.execute(
            select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == sub)
        ).scalars().all()
    ]

    access, refresh_token = create_token_pair(sub, roles)
    return TokenPair(access_token=access, refresh_token=refresh_token)

@app.get("/auth/me", response_model=Me)
def me(payload=Depends(get_current_user), db: Session = Depends(get_db)):
    sub = payload.get("sub")
    if not isinstance(sub, int):
        raise HTTPException(status_code=401, detail="Invalid token")
    u = db.get(User, sub)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    roles = [r.name for r in db.execute(
        select(Role).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == sub)
    ).scalars().all()]
    return Me(
        id=u.id,
        email=u.email,
        roles=roles,
        created_at=_ensure_timezone(u.created_at),
        updated_at=_ensure_timezone(u.updated_at),
    )

@app.post("/auth/totp/setup", response_model=TOTPSetup, dependencies=[Depends(require_roles("admin","user"))])
def totp_setup(payload=Depends(get_current_user), db: Session = Depends(get_db)):
    sub = payload.get("sub")
    if not isinstance(sub, int):
        raise HTTPException(status_code=401, detail="Invalid token")
    secret = generate_totp_secret()
    row = db.get(MFATotp, sub)
    if row:
        row.secret = secret
    else:
        row = MFATotp(user_id=sub, secret=secret, enabled=False)
        db.add(row)
    db.commit()

    label = f"TradingBot:{sub}"
    issuer = "TradingBot"
    otpauth = f"otpauth://totp/{urllib.parse.quote(label)}?secret={secret}&issuer={urllib.parse.quote(issuer)}"
    return TOTPSetup(secret=secret, otpauth_url=otpauth)

@app.post("/auth/totp/enable")
def totp_enable(code: str, payload=Depends(get_current_user), db: Session = Depends(get_db)):
    sub = payload.get("sub")
    if not isinstance(sub, int):
        raise HTTPException(status_code=401, detail="Invalid token")
    row = db.get(MFATotp, sub)
    if not row:
        raise HTTPException(status_code=400, detail="No TOTP setup")
    if not totp_now(row.secret).verify(code):
        raise HTTPException(status_code=400, detail="Invalid TOTP")
    row.enabled = True
    db.commit()
    return {"enabled": True}
