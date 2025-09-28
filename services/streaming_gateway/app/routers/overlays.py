"""Overlay creation and lookup endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings
from ..deps import get_current_user_id, get_settings_dependency
from ..models import OverlayCreateRequest, OverlayResponse
from ..security import issue_overlay_token
from ..storage import storage

router = APIRouter(prefix="/overlays", tags=["overlays"])


@router.post("", response_model=OverlayResponse, status_code=status.HTTP_201_CREATED)
async def create_overlay(
    payload: OverlayCreateRequest,
    user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings_dependency),
) -> OverlayResponse:
    overlay = storage.create_overlay(user_id, payload)
    token = issue_overlay_token(overlay.overlay_id, settings.overlay_token_secret, settings.overlay_token_ttl_seconds)
    signed_url = f"{settings.public_base_url}/o/{overlay.overlay_id}?token={token}"
    return OverlayResponse(overlayId=overlay.overlay_id, signedUrl=signed_url)


@router.get("/{overlay_id}", response_model=OverlayResponse)
async def get_overlay(
    overlay_id: str,
    user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings_dependency),
) -> OverlayResponse:
    overlay = storage.get_overlay(overlay_id, user_id)
    if not overlay:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overlay not found")
    token = issue_overlay_token(overlay.overlay_id, settings.overlay_token_secret, settings.overlay_token_ttl_seconds)
    signed_url = f"{settings.public_base_url}/o/{overlay.overlay_id}?token={token}"
    return OverlayResponse(overlayId=overlay.overlay_id, signedUrl=signed_url)
