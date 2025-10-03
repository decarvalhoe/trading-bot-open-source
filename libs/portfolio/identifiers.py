"""Encoding helpers for portfolio and position identifiers."""

from __future__ import annotations

import base64
from typing import Tuple

_SEPARATOR = "\0"
_PREFIX_POSITION = "position"
_PREFIX_PORTFOLIO = "portfolio"


def _encode_parts(*parts: str) -> str:
    normalised = [str(part or "").strip() for part in parts]
    raw = _SEPARATOR.join(normalised).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    return encoded.rstrip("=")


def _decode_parts(value: str) -> Tuple[str, ...]:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError("identifier cannot be empty")
    padding = "=" * (-len(cleaned) % 4)
    decoded = base64.urlsafe_b64decode(cleaned + padding).decode("utf-8")
    return tuple(decoded.split(_SEPARATOR))


def encode_position_key(account_id: str, symbol: str) -> str:
    """Return an opaque identifier uniquely mapping an account/symbol pair."""

    if not symbol:
        raise ValueError("symbol is required to encode a position key")
    return _encode_parts(_PREFIX_POSITION, account_id, symbol)


def decode_position_key(identifier: str) -> Tuple[str, str]:
    """Decode a position identifier back into (account_id, symbol)."""

    prefix, account_id, symbol = _decode_parts(identifier)
    if prefix != _PREFIX_POSITION:
        raise ValueError("identifier is not a position key")
    return account_id, symbol


def encode_portfolio_key(account_id: str) -> str:
    """Return an opaque identifier for a portfolio owner."""

    return _encode_parts(_PREFIX_PORTFOLIO, account_id)


def decode_portfolio_key(identifier: str) -> str:
    """Return the account identifier encoded in a portfolio key."""

    prefix, account_id = _decode_parts(identifier)
    if prefix != _PREFIX_PORTFOLIO:
        raise ValueError("identifier is not a portfolio key")
    return account_id


__all__ = [
    "encode_position_key",
    "decode_position_key",
    "encode_portfolio_key",
    "decode_portfolio_key",
]
