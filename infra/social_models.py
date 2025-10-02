"""SQLAlchemy models for social features (profiles, follows, leaderboards)."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Profile(Base):
    """Public profile for a strategy creator or investor."""

    __tablename__ = "social_profiles"

    id: int = Column(Integer, primary_key=True)
    user_id: str = Column(String(64), nullable=False, unique=True, index=True)
    display_name: str = Column(String(128), nullable=False)
    bio: Optional[str] = Column(Text)
    avatar_url: Optional[str] = Column(String(255))
    is_public: bool = Column(Boolean, nullable=False, default=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    activities = relationship("Activity", back_populates="profile", cascade="all, delete-orphan")


class Follow(Base):
    """Following relationship between two profiles."""

    __tablename__ = "social_follows"

    id: int = Column(Integer, primary_key=True)
    follower_id: str = Column(String(64), nullable=False, index=True)
    followee_id: str = Column(String(64), nullable=False, index=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("follower_id", "followee_id", name="uq_social_follow"),)


class Activity(Base):
    """Activity item displayed in feeds."""

    __tablename__ = "social_activities"

    id: int = Column(Integer, primary_key=True)
    profile_id: int = Column(
        Integer,
        ForeignKey("social_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    activity_type: str = Column(String(64), nullable=False)
    data: Dict[str, object] = Column(JSON, nullable=False, default=dict)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile = relationship("Profile", back_populates="activities")


class Leaderboard(Base):
    """Leaderboard snapshots used for discovery."""

    __tablename__ = "social_leaderboards"

    id: int = Column(Integer, primary_key=True)
    slug: str = Column(String(64), nullable=False, unique=True)
    title: str = Column(String(128), nullable=False)
    metric: str = Column(String(64), nullable=False)
    period: str = Column(String(32), nullable=False, default="all")
    data: Dict[str, object] = Column(JSON, nullable=False, default=dict)
    generated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["Base", "Profile", "Follow", "Activity", "Leaderboard"]
