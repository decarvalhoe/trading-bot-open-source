"""Database helpers for the order router service."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from libs.db.db import SessionLocal


def get_session() -> Iterator[Session]:
    """Yield a scoped SQLAlchemy session for FastAPI dependencies."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
