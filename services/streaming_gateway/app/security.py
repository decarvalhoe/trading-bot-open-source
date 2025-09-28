"""Helpers for signing and validating overlay access tokens."""

from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from typing import Any, Dict


def _sign(payload: bytes, secret: bytes) -> str:
    signature = hmac.new(secret, payload, sha256).digest()
    return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")


def issue_overlay_token(overlay_id: str, secret: str, ttl: int) -> str:
    """Create a signed token that expires shortly after issuance."""

    issued_at = int(time.time())
    payload = {
        "overlayId": overlay_id,
        "iat": issued_at,
        "exp": issued_at + ttl,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign(payload_bytes, secret.encode("utf-8"))
    token = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    return f"{token}.{signature}"


def verify_overlay_token(token: str, secret: str) -> Dict[str, Any]:
    """Validate a token issued with :func:`issue_overlay_token`."""

    try:
        encoded_payload, signature = token.split(".")
    except ValueError:
        raise ValueError("Invalid overlay token format") from None
    payload_bytes = base64.urlsafe_b64decode(encoded_payload + "==")
    expected_signature = _sign(payload_bytes, secret.encode("utf-8"))
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Signature mismatch")
    payload = json.loads(payload_bytes)
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    return payload
