"""OAuth2 flows for Twitch, YouTube and Discord."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import Settings
from ..deps import get_current_user_id, get_settings_dependency, get_token_store_dependency
from ..state import state_store
from ..token_store import EncryptedTokenStore, OAuthToken

router = APIRouter(prefix="/auth", tags=["oauth"])


@dataclass
class ProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    scopes: List[str]
    extra_params: Dict[str, str]

    def authorization_url(self, settings: Settings, state: str) -> str:
        redirect_uri = f"{settings.public_base_url}/auth/{self.name}/callback"
        params = {
            "client_id": getattr(settings, f"{self.name}_client_id"),
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            **self.extra_params,
        }
        return f"{self.authorize_url}?{urlencode(params)}"


PROVIDERS: Dict[str, ProviderConfig] = {
    "twitch": ProviderConfig(
        name="twitch",
        authorize_url="https://id.twitch.tv/oauth2/authorize",
        token_url="https://id.twitch.tv/oauth2/token",
        scopes=["user:read:email", "channel:manage:broadcast"],
        extra_params={"force_verify": "true"},
    ),
    "youtube": ProviderConfig(
        name="youtube",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=[
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube",
        ],
        extra_params={"access_type": "offline", "prompt": "consent"},
    ),
    "discord": ProviderConfig(
        name="discord",
        authorize_url="https://discord.com/api/oauth2/authorize",
        token_url="https://discord.com/api/oauth2/token",
        scopes=["identify", "bot", "applications.commands.update"],
        extra_params={"response_type": "code"},
    ),
}
@router.get("/{provider}/start")
async def oauth_start(
    provider: str,
    settings: Settings = Depends(get_settings_dependency),
) -> Dict[str, str]:
    provider_cfg = PROVIDERS.get(provider)
    if not provider_cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported provider")
    client_id = getattr(settings, f"{provider}_client_id", "")
    if not client_id:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Provider not configured")
    state = state_store.issue(provider)
    url = provider_cfg.authorization_url(settings, state)
    return {"authorization_url": url, "state": state}


async def _exchange_code(
    provider_cfg: ProviderConfig,
    settings: Settings,
    code: str,
) -> Dict[str, str]:
    redirect_uri = f"{settings.public_base_url}/auth/{provider_cfg.name}/callback"
    client_id = getattr(settings, f"{provider_cfg.name}_client_id")
    client_secret = getattr(settings, f"{provider_cfg.name}_client_secret")
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(provider_cfg.token_url, data=data)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.json()


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    scope: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user_id),
    settings: Settings = Depends(get_settings_dependency),
    store: EncryptedTokenStore = Depends(get_token_store_dependency),
) -> Dict[str, str]:
    provider_cfg = PROVIDERS.get(provider)
    if not provider_cfg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported provider")
    if not state_store.validate(provider, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    tokens = await _exchange_code(provider_cfg, settings, code)
    granted_scopes = scope.split(" ") if scope else provider_cfg.scopes
    store.save(
        OAuthToken(
            user_id=user_id,
            provider=provider,
            access_token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            scopes=granted_scopes,
            expires_at=tokens.get("expires_in"),
        )
    )
    return {"status": "connected", "provider": provider}
