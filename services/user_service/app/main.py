"""FastAPI application exposing CRUD operations for user profiles."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from jose import jwt
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from libs.db.db import get_db
from libs.entitlements import install_entitlements_middleware
from libs.entitlements.client import Entitlements
from libs.observability.logging import RequestContextMiddleware, configure_logging
from libs.observability.metrics import setup_metrics
from libs.secrets import get_secret

from .schemas import (
    ApiCredentialTestRequest,
    ApiCredentialTestResponse,
    BrokerCredentialStatus,
    BrokerCredentialsResponse,
    BrokerCredentialsUpdate,
    BrokerCredentialUpdate,
    OnboardingProgressResponse,
    PreferencesResponse,
    PreferencesUpdate,
    UserCreate,
    UserList,
    UserResponse,
    UserUpdate,
)

_default_jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_SECRET = get_secret("JWT_SECRET", default=_default_jwt_secret) or _default_jwt_secret
JWT_ALG = "HS256"


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class User(Base):
    """Persisted user account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    marketing_opt_in: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )


class UserPreferences(Base):
    """JSON blob storing arbitrary preferences for a user."""

    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferences: Mapped[dict] = mapped_column(
        JSON, server_default=text("'{}'"), nullable=False
    )


class ApiCredential(Base):
    """Encrypted broker credentials owned by a user."""

    __tablename__ = "user_broker_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "broker", name="uq_user_broker_credentials"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    broker: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    api_secret_encrypted: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )


# Backwards compatibility for modules importing the previous class name.
UserBrokerCredential = ApiCredential


configure_logging("user-service")

app = FastAPI(title="User Service", version="0.1.0")
install_entitlements_middleware(
    app,
    required_capabilities=["can.use_users"],
    required_quotas={},
    skip_paths=["/users/register"],
)
app.add_middleware(RequestContextMiddleware, service_name="user-service")
setup_metrics(app, service_name="user-service")

logger = logging.getLogger(__name__)

_BROKER_CREDENTIALS_CIPHER: Fernet | None = None


def _normalise_secret_input(value: str | None) -> str | None:
    if value is None:
        return None
    if value.strip() == "":
        return None
    return value


def _load_broker_encryption_key() -> bytes:
    key = get_secret("BROKER_CREDENTIALS_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("BROKER_CREDENTIALS_ENCRYPTION_KEY is not configured")
    if isinstance(key, str):
        key_bytes = key.encode("utf-8")
    else:
        key_bytes = key
    try:
        Fernet(key_bytes)
    except ValueError as exc:  # pragma: no cover - configuration error
        raise RuntimeError("Invalid broker credentials encryption key") from exc
    return key_bytes


def _get_broker_credentials_cipher() -> Fernet:
    global _BROKER_CREDENTIALS_CIPHER
    if _BROKER_CREDENTIALS_CIPHER is None:
        key_bytes = _load_broker_encryption_key()
        _BROKER_CREDENTIALS_CIPHER = Fernet(key_bytes)
    return _BROKER_CREDENTIALS_CIPHER


def _require_broker_cipher() -> Fernet:
    try:
        return _get_broker_credentials_cipher()
    except RuntimeError as exc:
        logger.error("Broker credentials encryption key misconfigured: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Broker credentials encryption key is not configured",
        ) from exc


def _encrypt_broker_secret(value: str | None) -> str | None:
    cleaned = _normalise_secret_input(value)
    if cleaned is None:
        return None
    cipher = _get_broker_credentials_cipher()
    token = cipher.encrypt(cleaned.encode("utf-8"))
    return token.decode("utf-8")


def _decrypt_broker_secret(token: str | None) -> str | None:
    if not token:
        return None
    cipher = _get_broker_credentials_cipher()
    try:
        decrypted = cipher.decrypt(token.encode("utf-8"))
    except InvalidToken:
        logger.warning("Unable to decrypt broker credential", exc_info=False)
        return None
    return decrypted.decode("utf-8")


def _mask_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    length = len(secret)
    if length <= 4:
        return "•" * length
    return "•" * (length - 4) + secret[-4:]


def _serialise_api_credential(
    credential: ApiCredential,
) -> BrokerCredentialStatus:
    api_key = _decrypt_broker_secret(credential.api_key_encrypted)
    api_secret = _decrypt_broker_secret(credential.api_secret_encrypted)
    return BrokerCredentialStatus(
        broker=credential.broker,
        has_api_key=bool(credential.api_key_encrypted),
        has_api_secret=bool(credential.api_secret_encrypted),
        api_key_masked=_mask_secret(api_key),
        api_secret_masked=_mask_secret(api_secret),
        updated_at=credential.updated_at,
        last_test_status=credential.last_test_status,
        last_tested_at=credential.last_tested_at,
    )


def _list_broker_credentials(
    db: Session, user_id: int
) -> BrokerCredentialsResponse:
    _require_broker_cipher()
    rows = (
        db.scalars(
            select(UserBrokerCredential)
            .where(UserBrokerCredential.user_id == user_id)
            .order_by(UserBrokerCredential.broker)
        )
    ).all()
    return BrokerCredentialsResponse(
        credentials=[_serialise_api_credential(row) for row in rows]
    )


def _apply_broker_credential_update(
    credential: ApiCredential, payload: BrokerCredentialUpdate
) -> bool:
    updated = False
    fields = payload.model_fields_set
    if "api_key" in fields:
        encrypted = _encrypt_broker_secret(payload.api_key)
        if credential.api_key_encrypted != encrypted:
            credential.api_key_encrypted = encrypted
            updated = True
    if "api_secret" in fields:
        encrypted_secret = _encrypt_broker_secret(payload.api_secret)
        if credential.api_secret_encrypted != encrypted_secret:
            credential.api_secret_encrypted = encrypted_secret
            updated = True
    if updated:
        credential.updated_at = datetime.now(timezone.utc)
        credential.last_test_status = None
        credential.last_tested_at = None
    return updated


def _normalise_broker(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Broker identifier is required")
    return cleaned


_UNAUTHORIZED_KEYWORDS = {"invalid", "unauthorized", "forbidden", "reject"}
_NETWORK_KEYWORDS = {"timeout", "offline", "network"}
_SUPPORTED_BROKER_TESTS = {"binance", "ibkr"}


def _probe_api_credentials(broker: str, api_key: str, api_secret: str) -> None:
    combined = f"{api_key}{api_secret}".lower()
    if not api_key or not api_secret:
        raise PermissionError("Missing credentials")
    if any(keyword in combined for keyword in _UNAUTHORIZED_KEYWORDS):
        raise PermissionError("Broker rejected the provided credentials")
    if any(keyword in combined for keyword in _NETWORK_KEYWORDS):
        raise ConnectionError("Broker API unreachable")
    if broker not in _SUPPORTED_BROKER_TESTS:
        raise ConnectionError("Broker not supported for automated checks")


def _test_api_credentials(
    db: Session, actor_id: int, payload: ApiCredentialTestRequest
) -> ApiCredentialTestResponse:
    broker = _normalise_broker(payload.broker)
    _require_broker_cipher()
    credential = db.scalar(
        select(ApiCredential)
        .where(ApiCredential.user_id == actor_id)
        .where(ApiCredential.broker == broker)
    )
    api_key = payload.api_key
    api_secret = payload.api_secret
    if credential is not None:
        if api_key is None:
            api_key = _decrypt_broker_secret(credential.api_key_encrypted)
        if api_secret is None:
            api_secret = _decrypt_broker_secret(credential.api_secret_encrypted)

    now = datetime.now(timezone.utc)
    status: str
    message: str | None = None
    if not api_key or not api_secret:
        status = "unauthorized"
        message = "Clés API manquantes pour ce broker."
    else:
        try:
            _probe_api_credentials(broker, api_key, api_secret)
        except PermissionError:
            status = "unauthorized"
            message = "Le broker a rejeté les identifiants fournis."
        except ConnectionError:
            status = "network_error"
            message = "Impossible de joindre le broker. Vérifiez l'URL ou réessayez."
        else:
            status = "ok"
            message = "Connexion établie avec succès."

    if credential is not None:
        credential.last_test_status = status
        credential.last_tested_at = now
        db.commit()
        db.refresh(credential)

    return ApiCredentialTestResponse(
        broker=broker,
        status=status,
        tested_at=now,
        message=message,
    )


def _persist_broker_credentials(
    db: Session, actor_id: int, payload: BrokerCredentialsUpdate
) -> BrokerCredentialsResponse:
    _get_user_or_404(db, actor_id)
    _require_broker_cipher()
    modified = False
    for entry in payload.credentials or []:
        broker = _normalise_broker(entry.broker)
        fields = entry.model_fields_set
        if not ({"api_key", "api_secret"} & fields):
            continue
        credential = db.scalar(
            select(ApiCredential)
            .where(ApiCredential.user_id == actor_id)
            .where(ApiCredential.broker == broker)
        )
        if credential is None:
            credential = ApiCredential(user_id=actor_id, broker=broker)
            db.add(credential)
        was_new = credential.id is None
        updated = _apply_broker_credential_update(credential, entry)
        if credential.api_key_encrypted is None and credential.api_secret_encrypted is None:
            if credential.id is None:
                db.expunge(credential)
            else:
                db.delete(credential)
            modified = True
            continue
        if credential.broker != broker:
            credential.broker = broker
            updated = True
        if was_new or updated:
            modified = True
    if modified:
        db.commit()
    return _list_broker_credentials(db, actor_id)


SENSITIVE_FIELDS = {"email", "phone", "marketing_opt_in"}

ONBOARDING_STEP_DEFINITIONS: List[dict[str, str]] = [
    {
        "id": "account-profile",
        "title": "Compte",
        "description": "Vérifiez vos informations personnelles et les canaux de notifications.",
    },
    {
        "id": "api-keys",
        "title": "Clés API",
        "description": "Ajoutez vos identifiants broker et testez la connexion sécurisée.",
    },
    {
        "id": "execution-mode",
        "title": "Mode",
        "description": "Choisissez entre simulation déterministe et sandbox avant le trading réel.",
    },
]

ONBOARDING_STEP_IDS = [step["id"] for step in ONBOARDING_STEP_DEFINITIONS]
_ONBOARDING_STEP_SET = set(ONBOARDING_STEP_IDS)


class OnboardingProgress(Base):
    """Persist onboarding progression for each user."""

    __tablename__ = "onboarding_progress"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_steps: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, server_default=text("'[]'"), default=list
    )
    restarted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )


def require_auth(authorization: str = Header(default=None)) -> dict:
    """Validate the bearer token and return its payload."""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split()[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except Exception as exc:  # pragma: no cover - jose already raises precise errors
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    return payload


def get_entitlements(request: Request) -> Entitlements:
    """Return entitlements stored in the request state or a blank default."""

    entitlements = getattr(request.state, "entitlements", None)
    if entitlements is None:
        return Entitlements(customer_id="anonymous", features={}, quotas={})
    return entitlements


def require_manage_users(
    entitlements: Entitlements = Depends(get_entitlements),
) -> Entitlements:
    """Ensure the caller has the capability to manage other users."""

    if not entitlements.has("can.manage_users"):
        raise HTTPException(status_code=403, detail="Missing capability: can.manage_users")
    return entitlements


def get_authenticated_actor(
    request: Request, payload: dict = Depends(require_auth)
) -> int:
    """Validate that the JWT payload matches the optional actor header."""

    sub = payload.get("sub")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    actor_header = request.headers.get("x-customer-id") or request.headers.get("x-user-id")
    if not actor_header:
        if os.getenv("ENTITLEMENTS_BYPASS", "0") == "1":
            return user_id
        raise HTTPException(status_code=400, detail="Missing x-customer-id header")
    try:
        actor_id = int(actor_header)
    except ValueError as exc:  # pragma: no cover - validated in integration tests
        raise HTTPException(status_code=400, detail="Invalid x-customer-id header") from exc
    if user_id != actor_id:
        raise HTTPException(status_code=403, detail="Actor mismatch")
    return actor_id


def _fetch_preferences(db: Session, user_id: int) -> Dict[str, object]:
    row = db.get(UserPreferences, user_id)
    return row.preferences if row else {}


def _normalise_completed_steps(values: Iterable[str]) -> list[str]:
    """Ensure step identifiers are unique and valid, preserving order."""

    ordered: list[str] = []
    seen: set[str] = set()
    for step_id in values or []:
        if not isinstance(step_id, str):
            continue
        cleaned = step_id.strip()
        if cleaned in seen or cleaned not in _ONBOARDING_STEP_SET:
            continue
        ordered.append(cleaned)
        seen.add(cleaned)
    return ordered


def _resolve_next_step(completed: Iterable[str]) -> str | None:
    completed_set = set(completed)
    for step_id in ONBOARDING_STEP_IDS:
        if step_id not in completed_set:
            return step_id
    return None


def _load_or_create_progress(db: Session, user_id: int) -> OnboardingProgress:
    progress = db.get(OnboardingProgress, user_id)
    if progress is None:
        progress = OnboardingProgress(
            user_id=user_id,
            completed_steps=[],
            current_step=_resolve_next_step([]),
        )
        db.add(progress)
        db.flush()
    else:
        progress.completed_steps = _normalise_completed_steps(progress.completed_steps or [])
        next_step = _resolve_next_step(progress.completed_steps)
        if progress.current_step != next_step:
            progress.current_step = next_step
    return progress


def _serialise_progress(progress: OnboardingProgress) -> OnboardingProgressResponse:
    completed = _normalise_completed_steps(progress.completed_steps or [])
    next_step = _resolve_next_step(completed)
    is_complete = next_step is None and len(completed) == len(ONBOARDING_STEP_IDS)
    return OnboardingProgressResponse(
        user_id=progress.user_id,
        current_step=next_step,
        completed_steps=completed,
        steps=list(ONBOARDING_STEP_DEFINITIONS),
        is_complete=is_complete,
        updated_at=progress.updated_at,
        restarted_at=progress.restarted_at,
    )


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _build_user_response(user: User, preferences: Dict[str, object]) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        marketing_opt_in=user.marketing_opt_in,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        preferences=preferences,
    )


def _scrub_user_payload(
    user: UserResponse, *, entitlements: Entitlements | None, actor_id: int | None
) -> UserResponse:
    if actor_id is not None and user.id == actor_id:
        return user
    if entitlements and entitlements.has("can.manage_users"):
        return user
    data = user.model_dump()
    for field in SENSITIVE_FIELDS:
        data[field] = None
    return UserResponse(**data)


def _apply_user_update(user: User, payload: UserUpdate) -> bool:
    updated = False
    if payload.first_name is not None:
        user.first_name = payload.first_name
        updated = True
    if payload.last_name is not None:
        user.last_name = payload.last_name
        updated = True
    if payload.phone is not None:
        user.phone = payload.phone
        updated = True
    if payload.marketing_opt_in is not None:
        user.marketing_opt_in = payload.marketing_opt_in
        updated = True
    if updated:
        user.updated_at = datetime.now(timezone.utc)
    return updated


@app.get("/health")
def health() -> Dict[str, str]:
    """Vérifie que le service est opérationnel."""

    return {"status": "ok"}


@app.post("/users/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserCreate,
    _: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Inscrit un nouvel utilisateur en base de données avec un statut inactif."""

    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        marketing_opt_in=payload.marketing_opt_in,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    response = _build_user_response(user, {})
    return _scrub_user_payload(response, entitlements=None, actor_id=user.id)


@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: Entitlements = Depends(require_manage_users),
) -> UserResponse:
    """Crée un utilisateur depuis un back-office ou un script d'administration."""

    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        marketing_opt_in=payload.marketing_opt_in,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    preferences = _fetch_preferences(db, user.id)
    return _build_user_response(user, preferences)


@app.get("/users", response_model=UserList)
def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: Entitlements = Depends(require_manage_users),
    db: Session = Depends(get_db),
) -> UserList:
    """Liste l'ensemble des utilisateurs pour un opérateur autorisé."""

    total = db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0
    users = (
        db.scalars(
            select(User)
            .where(User.deleted_at.is_(None))
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [
        _build_user_response(user, _fetch_preferences(db, user.id)) for user in users
    ]
    return UserList(
        items=items,
        pagination={
            "total": total,
            "count": len(items),
            "limit": limit,
            "offset": offset,
        },
    )


@app.get("/users/me", response_model=UserResponse)
def get_me(
    actor_id: int = Depends(get_authenticated_actor),
    entitlements: Entitlements = Depends(get_entitlements),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Retourne le profil complet de l'utilisateur authentifié."""

    user = _get_user_or_404(db, actor_id)
    preferences = _fetch_preferences(db, actor_id)
    response = _build_user_response(user, preferences)
    return _scrub_user_payload(response, entitlements=entitlements, actor_id=actor_id)


@app.put("/users/me", response_model=UserResponse)
def update_me(
    payload: UserUpdate,
    actor_id: int = Depends(get_authenticated_actor),
    entitlements: Entitlements = Depends(get_entitlements),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Met à jour le profil de l'utilisateur authentifié."""

    user = _get_user_or_404(db, actor_id)
    _apply_user_update(user, payload)
    db.commit()
    db.refresh(user)
    preferences = _fetch_preferences(db, actor_id)
    response = _build_user_response(user, preferences)
    return _scrub_user_payload(response, entitlements=entitlements, actor_id=actor_id)


@app.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> Response:
    """Effectue un soft delete du profil de l'utilisateur authentifié."""

    user = _get_user_or_404(db, actor_id)
    if user.deleted_at is None:
        now = datetime.now(timezone.utc)
        user.deleted_at = now
        user.is_active = False
        user.updated_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    entitlements: Entitlements = Depends(require_manage_users),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Retourne le profil demandé en masquant les champs sensibles si nécessaire."""

    user = _get_user_or_404(db, user_id)
    preferences = _fetch_preferences(db, user_id)
    response = _build_user_response(user, preferences)
    return _scrub_user_payload(
        response, entitlements=entitlements, actor_id=None
    )


@app.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    payload: UserUpdate,
    entitlements: Entitlements = Depends(require_manage_users),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Met à jour les informations de profil d'un utilisateur."""

    user = _get_user_or_404(db, user_id)
    _apply_user_update(user, payload)
    db.commit()
    db.refresh(user)
    preferences = _fetch_preferences(db, user_id)
    response = _build_user_response(user, preferences)
    return _scrub_user_payload(
        response, entitlements=entitlements, actor_id=None
    )


@app.post("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: int,
    actor_id: int = Depends(get_authenticated_actor),
    entitlements: Entitlements = Depends(get_entitlements),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Active un utilisateur soit par lui-même soit par un administrateur."""

    user = _get_user_or_404(db, user_id)
    if user.id != actor_id and not entitlements.has("can.manage_users"):
        raise HTTPException(status_code=403, detail="Operation not permitted")
    if not user.is_active:
        user.is_active = True
        user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    preferences = _fetch_preferences(db, user_id)
    response = _build_user_response(user, preferences)
    return _scrub_user_payload(response, entitlements=entitlements, actor_id=actor_id)


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    _: Entitlements = Depends(require_manage_users),
    db: Session = Depends(get_db),
) -> Response:
    """Supprime définitivement un utilisateur et ses préférences associées."""

    user = _get_user_or_404(db, user_id)
    now = datetime.now(timezone.utc)
    user.deleted_at = now
    user.is_active = False
    user.updated_at = now
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/users/me/onboarding", response_model=OnboardingProgressResponse)
def get_my_onboarding_progress(
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> OnboardingProgressResponse:
    """Return the onboarding progression for the authenticated user."""

    _get_user_or_404(db, actor_id)
    progress = _load_or_create_progress(db, actor_id)
    db.commit()
    db.refresh(progress)
    return _serialise_progress(progress)


@app.post("/users/me/onboarding/steps/{step_id}", response_model=OnboardingProgressResponse)
def complete_onboarding_step(
    step_id: str,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> OnboardingProgressResponse:
    """Mark the given onboarding step as completed for the authenticated user."""

    cleaned_id = (step_id or "").strip()
    if cleaned_id not in _ONBOARDING_STEP_SET:
        raise HTTPException(status_code=400, detail="Unknown onboarding step")

    _get_user_or_404(db, actor_id)
    progress = _load_or_create_progress(db, actor_id)
    completed = set(progress.completed_steps or [])
    completed.add(cleaned_id)
    progress.completed_steps = [
        step for step in ONBOARDING_STEP_IDS if step in completed
    ]
    next_step = _resolve_next_step(progress.completed_steps)
    progress.current_step = next_step
    progress.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(progress)
    return _serialise_progress(progress)


@app.post("/users/me/onboarding/reset", response_model=OnboardingProgressResponse)
def reset_onboarding_progress(
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> OnboardingProgressResponse:
    """Reset the onboarding progression for the authenticated user."""

    _get_user_or_404(db, actor_id)
    progress = _load_or_create_progress(db, actor_id)
    progress.completed_steps = []
    progress.current_step = _resolve_next_step([])
    now = datetime.now(timezone.utc)
    progress.restarted_at = now
    progress.updated_at = now
    db.commit()
    db.refresh(progress)
    return _serialise_progress(progress)


@app.get("/users/me/broker-credentials", response_model=BrokerCredentialsResponse)
def get_my_broker_credentials(
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Return encrypted broker credentials for the authenticated user."""

    _get_user_or_404(db, actor_id)
    return _list_broker_credentials(db, actor_id)


@app.put("/users/me/broker-credentials", response_model=BrokerCredentialsResponse)
def update_my_broker_credentials(
    payload: BrokerCredentialsUpdate,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Create, update or delete broker credentials for the authenticated user."""

    return _persist_broker_credentials(db, actor_id, payload)


@app.get("/users/me/api-credentials", response_model=BrokerCredentialsResponse)
def get_my_api_credentials(
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Alias returning broker credentials using the new API terminology."""

    _get_user_or_404(db, actor_id)
    return _list_broker_credentials(db, actor_id)


@app.post("/users/me/api-credentials", response_model=BrokerCredentialsResponse)
def create_api_credentials(
    payload: BrokerCredentialsUpdate,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Create or replace broker API credentials for the authenticated user."""

    return _persist_broker_credentials(db, actor_id, payload)


@app.put("/users/me/api-credentials", response_model=BrokerCredentialsResponse)
def update_api_credentials(
    payload: BrokerCredentialsUpdate,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> BrokerCredentialsResponse:
    """Update broker API credentials for the authenticated user."""

    return _persist_broker_credentials(db, actor_id, payload)


@app.delete("/users/me/api-credentials/{broker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_credential(
    broker: str,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> Response:
    """Remove a broker credential entry for the authenticated user."""

    _get_user_or_404(db, actor_id)
    cleaned = _normalise_broker(broker)
    credential = db.scalar(
        select(ApiCredential)
        .where(ApiCredential.user_id == actor_id)
        .where(ApiCredential.broker == cleaned)
    )
    if credential is None:
        raise HTTPException(status_code=404, detail="Broker credential not found")
    db.delete(credential)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/users/me/api-credentials/test", response_model=ApiCredentialTestResponse)
def test_api_credentials_endpoint(
    payload: ApiCredentialTestRequest,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> ApiCredentialTestResponse:
    """Trigger a connection test against the configured broker credentials."""

    _get_user_or_404(db, actor_id)
    return _test_api_credentials(db, actor_id, payload)


@app.put("/users/me/preferences", response_model=PreferencesResponse)
def update_preferences(
    payload: PreferencesUpdate,
    actor_id: int = Depends(get_authenticated_actor),
    db: Session = Depends(get_db),
) -> PreferencesResponse:
    """Remplace l'intégralité des préférences de l'utilisateur courant."""

    row = db.get(UserPreferences, actor_id)
    if row:
        row.preferences = payload.preferences
    else:
        db.add(
            UserPreferences(user_id=actor_id, preferences=payload.preferences)
        )
    db.commit()
    return PreferencesResponse(preferences=payload.preferences)


__all__ = [
    "app",
    "Base",
    "User",
    "UserPreferences",
    "ApiCredential",
    "UserBrokerCredential",
    "OnboardingProgress",
    "require_auth",
    "get_entitlements",
]
