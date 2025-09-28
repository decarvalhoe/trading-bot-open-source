"""Utilities for encrypting and persisting OAuth tokens."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken


@dataclass
class OAuthToken:
    """Represents an OAuth access/refresh token pair."""

    user_id: str
    provider: str
    access_token: str
    refresh_token: Optional[str]
    scopes: list[str]
    expires_at: Optional[float]


class EncryptedTokenStore:
    """Very small encrypted store backed by memory."""

    def __init__(self, encryption_key: str) -> None:
        if not encryption_key:
            encryption_key = base64.urlsafe_b64encode(Fernet.generate_key())
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode("utf-8")
        # Ensure a correct fernet key length
        if len(encryption_key) != 44:
            encryption_key = base64.urlsafe_b64encode(encryption_key[:32].ljust(32, b"0"))
        self._fernet = Fernet(encryption_key)
        self._tokens: Dict[tuple[str, str], bytes] = {}

    def save(self, token: OAuthToken) -> None:
        key = (token.user_id, token.provider)
        payload = json.dumps(token.__dict__).encode("utf-8")
        self._tokens[key] = self._fernet.encrypt(payload)

    def get(self, user_id: str, provider: str) -> Optional[OAuthToken]:
        encrypted = self._tokens.get((user_id, provider))
        if not encrypted:
            return None
        try:
            payload = self._fernet.decrypt(encrypted)
        except InvalidToken:
            return None
        data = json.loads(payload)
        return OAuthToken(**data)

    def revoke(self, user_id: str, provider: str) -> None:
        self._tokens.pop((user_id, provider), None)


_store: Optional[EncryptedTokenStore] = None


def init_store(encryption_key: str) -> EncryptedTokenStore:
    global _store
    if _store is None:
        _store = EncryptedTokenStore(encryption_key=encryption_key)
    return _store


def get_store() -> EncryptedTokenStore:
    if _store is None:
        raise RuntimeError("Token store accessed before initialization")
    return _store
