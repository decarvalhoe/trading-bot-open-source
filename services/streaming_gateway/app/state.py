"""Simple in-memory store for OAuth state parameters."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Dict, Tuple

_STATE_TTL_SECONDS = 600


@dataclass
class OAuthState:
    """Container storing OAuth state metadata."""

    provider: str
    created_at: float

    def is_expired(self) -> bool:
        return time.time() - self.created_at > _STATE_TTL_SECONDS


class OAuthStateStore:
    """Time bound state storage for OAuth flows."""

    def __init__(self) -> None:
        self._states: Dict[str, OAuthState] = {}

    def issue(self, provider: str) -> str:
        state = secrets.token_urlsafe(32)
        self._states[state] = OAuthState(provider=provider, created_at=time.time())
        self._cleanup()
        return state

    def validate(self, provider: str, state: str) -> bool:
        metadata = self._states.pop(state, None)
        if not metadata:
            return False
        if metadata.provider != provider:
            return False
        return not metadata.is_expired()

    def _cleanup(self) -> None:
        for key, value in list(self._states.items()):
            if value.is_expired():
                self._states.pop(key, None)


state_store = OAuthStateStore()
"""Module level store used by routers."""
