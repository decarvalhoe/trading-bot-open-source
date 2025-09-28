"""Common FastAPI dependencies used across routers."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings
from .token_store import EncryptedTokenStore, get_store, init_store


async def get_current_user_id(x_user_id: str = Header(..., alias="x-user-id")) -> str:
    """Simple dependency fetching the authenticated user id from headers."""

    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-user-id header")
    return x_user_id


def get_settings_dependency() -> Settings:
    return get_settings()


def get_token_store_dependency(settings: Settings = Depends(get_settings_dependency)) -> EncryptedTokenStore:
    try:
        return get_store()
    except RuntimeError:
        return init_store(settings.encryption_key)
