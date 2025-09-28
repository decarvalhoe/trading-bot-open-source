"""FastAPI application exposing social features."""
from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from infra import AuditBase, Leaderboard, SocialBase
from libs.db.db import engine, get_db
from libs.entitlements.fastapi import install_entitlements_middleware

from .dependencies import (
    get_actor_id,
    get_optional_actor_id,
    require_follow_capability,
    require_profile_capability,
)
from .schemas import (
    ActivityCreate,
    ActivityOut,
    FollowRequest,
    LeaderboardOut,
    LeaderboardUpsert,
    ProfileOut,
    ProfileUpdate,
)
from .service import (
    create_activity,
    fetch_activity_feed,
    fetch_profile,
    toggle_follow,
    upsert_leaderboard,
    upsert_profile,
)

app = FastAPI(title="Social Service", version="0.1.0")

SocialBase.metadata.create_all(bind=engine)
AuditBase.metadata.create_all(bind=engine)

install_entitlements_middleware(app)

router = APIRouter(prefix="/social", tags=["social"])


@router.put("/profiles/me", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_profile_capability),
):
    profile = upsert_profile(db, actor_id=actor_id, payload=payload)
    return ProfileOut.model_validate(profile)


@router.get("/profiles/{user_id}", response_model=ProfileOut)
def get_profile(
    user_id: str,
    db: Session = Depends(get_db),
    actor_id: str | None = Depends(get_optional_actor_id),
):
    profile = fetch_profile(db, user_id=user_id, viewer_id=actor_id)
    return ProfileOut.model_validate(profile)


@router.post("/follows", response_model=dict)
def follow_action(
    payload: FollowRequest,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_follow_capability),
):
    changed = toggle_follow(db, actor_id=actor_id, payload=payload)
    return {"changed": changed}


@router.post("/activities", response_model=ActivityOut, status_code=201)
def log_activity(
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_profile_capability),
):
    activity = create_activity(db, actor_id=actor_id, payload=payload)
    return ActivityOut.model_validate(activity)


@router.get("/activities", response_model=list[ActivityOut])
def activity_feed(
    db: Session = Depends(get_db),
    actor_id: str | None = Depends(get_optional_actor_id),
    limit: int = Query(20, ge=1, le=100),
):
    activities = fetch_activity_feed(db, viewer_id=actor_id, limit=limit)
    return [ActivityOut.model_validate(act) for act in activities]


@router.put("/leaderboards/{slug}", response_model=LeaderboardOut)
def upsert_board(
    slug: str,
    payload: LeaderboardUpsert,
    db: Session = Depends(get_db),
    actor_id: str = Depends(get_actor_id),
    _: object = Depends(require_profile_capability),
):
    board = upsert_leaderboard(db, slug=slug, payload=payload, actor_id=actor_id)
    return LeaderboardOut.model_validate(board)


@router.get("/leaderboards/{slug}", response_model=LeaderboardOut)
def get_board(slug: str, db: Session = Depends(get_db)):
    board = db.scalar(select(Leaderboard).where(Leaderboard.slug == slug))
    if not board:
        raise HTTPException(status_code=404, detail="Leaderboard not found")
    return LeaderboardOut.model_validate(board)


app.include_router(router)


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
