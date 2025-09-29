"""FastAPI application exposing CRUD operations for user profiles."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict

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
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
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

SENSITIVE_FIELDS = {"email", "phone", "marketing_opt_in"}


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

    user_id = int(payload["sub"])
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
    "require_auth",
    "get_entitlements",
]
