"""Domain services for the social API."""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from infra import Activity, Follow, Leaderboard, Profile
from libs.audit import record_audit

from .schemas import ActivityCreate, FollowRequest, LeaderboardUpsert, ProfileUpdate



def upsert_profile(db: Session, *, actor_id: str, payload: ProfileUpdate) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == actor_id))
    created = False
    if not profile:
        profile = Profile(
            user_id=actor_id,
            display_name=payload.display_name,
            bio=payload.bio,
            avatar_url=payload.avatar_url,
            is_public=payload.is_public,
        )
        db.add(profile)
        created = True
    else:
        profile.display_name = payload.display_name
        profile.bio = payload.bio
        profile.avatar_url = payload.avatar_url
        profile.is_public = payload.is_public

    record_audit(
        db,
        service="social",
        action="profile.created" if created else "profile.updated",
        actor_id=actor_id,
        subject_id=actor_id,
        details={"is_public": profile.is_public},
    )
    db.commit()
    db.refresh(profile)
    return profile


def fetch_profile(db: Session, *, user_id: str, viewer_id: Optional[str] = None) -> Profile:
    profile = db.scalar(select(Profile).where(Profile.user_id == user_id))
    if not profile or (not profile.is_public and profile.user_id != viewer_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def toggle_follow(db: Session, *, actor_id: str, payload: FollowRequest) -> bool:
    if actor_id == payload.target_user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")

    target = db.scalar(select(Profile).where(Profile.user_id == payload.target_user_id))
    if not target:
        raise HTTPException(status_code=404, detail="Target profile not found")

    follow = db.scalar(
        select(Follow).where(
            Follow.follower_id == actor_id,
            Follow.followee_id == payload.target_user_id,
        )
    )
    if payload.follow:
        if follow:
            return False
        follow = Follow(follower_id=actor_id, followee_id=payload.target_user_id)
        db.add(follow)
        record_audit(
            db,
            service="social",
            action="profile.followed",
            actor_id=actor_id,
            subject_id=payload.target_user_id,
        )
        create_activity(
            db,
            actor_id=actor_id,
            payload=ActivityCreate(
                activity_type="follow",
                data={"target_user_id": payload.target_user_id},
            ),
        )
        db.commit()
        return True

    if follow:
        db.delete(follow)
        record_audit(
            db,
            service="social",
            action="profile.unfollowed",
            actor_id=actor_id,
            subject_id=payload.target_user_id,
        )
        db.commit()
        return True

    return False


def create_activity(db: Session, *, actor_id: str, payload: ActivityCreate) -> Activity:
    profile = db.scalar(select(Profile).where(Profile.user_id == actor_id))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found for activity")

    activity = Activity(profile=profile, activity_type=payload.activity_type, data=payload.data)
    db.add(activity)
    record_audit(
        db,
        service="social",
        action="activity.logged",
        actor_id=actor_id,
        subject_id=str(profile.id),
        details={"activity_type": payload.activity_type},
    )
    db.commit()
    db.refresh(activity)
    return activity


def fetch_activity_feed(
    db: Session,
    *,
    viewer_id: Optional[str] = None,
    limit: int = 20,
) -> list[Activity]:
    stmt = select(Activity).join(Profile).order_by(Activity.created_at.desc()).limit(limit)
    if viewer_id:
        followee_ids = db.scalars(
            select(Follow.followee_id).where(Follow.follower_id == viewer_id)
        ).all()
        user_ids = set(followee_ids + [viewer_id])
        if user_ids:
            stmt = stmt.where(Profile.user_id.in_(user_ids))
    return db.scalars(stmt).all()


def upsert_leaderboard(db: Session, *, slug: str, payload: LeaderboardUpsert, actor_id: str) -> Leaderboard:
    board = db.scalar(select(Leaderboard).where(Leaderboard.slug == slug))
    created = False
    if not board:
        board = Leaderboard(
            slug=slug,
            title=payload.title,
            metric=payload.metric,
            period=payload.period,
            data=payload.data,
        )
        db.add(board)
        created = True
    else:
        board.title = payload.title
        board.metric = payload.metric
        board.period = payload.period
        board.data = payload.data

    record_audit(
        db,
        service="social",
        action="leaderboard.created" if created else "leaderboard.updated",
        actor_id=actor_id,
        subject_id=slug,
        details={"metric": board.metric, "period": board.period},
    )
    db.commit()
    db.refresh(board)
    return board


def clear_profile_data(db: Session, *, user_id: str) -> None:
    db.execute(delete(Follow).where((Follow.follower_id == user_id) | (Follow.followee_id == user_id)))
    db.execute(delete(Activity).where(Activity.profile_id.in_(select(Profile.id).where(Profile.user_id == user_id))))
    db.execute(delete(Profile).where(Profile.user_id == user_id))
    db.commit()
