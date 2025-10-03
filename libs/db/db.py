"""Database helpers shared across services."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from libs.env import DEFAULT_POSTGRES_DSN_NATIVE


def _resolve_database_url() -> str:
    """Return the configured database URL or fall back to localhost."""

    for env_var in ("DATABASE_URL", "POSTGRES_DSN"):
        value = os.getenv(env_var)
        if value:
            return value
    return DEFAULT_POSTGRES_DSN_NATIVE


DB_URL = _resolve_database_url()

engine = create_engine(DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
