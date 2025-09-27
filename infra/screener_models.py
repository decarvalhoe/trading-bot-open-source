"""SQLAlchemy models backing the screener service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class ScreenerBase(DeclarativeBase):
    """Declarative base for screener related tables."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScreenerPreset(ScreenerBase):
    __tablename__ = "screener_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(length=255))
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    snapshots: Mapped[list["ScreenerSnapshot"]] = relationship(back_populates="preset")


class ScreenerSnapshot(ScreenerBase):
    __tablename__ = "screener_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    preset_id: Mapped[int | None] = mapped_column(ForeignKey("screener_presets.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(length=32), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    preset: Mapped[Optional["ScreenerPreset"]] = relationship(back_populates="snapshots")
    results: Mapped[list["ScreenerResult"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class ScreenerResult(ScreenerBase):
    __tablename__ = "screener_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("screener_snapshots.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(length=32), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    snapshot: Mapped[ScreenerSnapshot] = relationship(back_populates="results")


__all__ = [
    "ScreenerBase",
    "ScreenerPreset",
    "ScreenerSnapshot",
    "ScreenerResult",
]
