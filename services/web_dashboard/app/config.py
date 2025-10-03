"""Shared configuration helpers for the web dashboard service."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def is_native_environment() -> bool:
    """Return ``True`` when the stack runs in native (host) mode."""

    return os.getenv("ENVIRONMENT", "").strip().lower() == "native"


def _ensure_trailing_slash(value: str, *, trailing_slash: bool) -> str:
    """Normalise trailing slashes according to the desired style."""

    trimmed = value.rstrip("/")
    if trailing_slash:
        return f"{trimmed}/"
    return trimmed


def default_service_url(
    container_url: str,
    *,
    native_port: int,
    trailing_slash: bool = True,
) -> str:
    """Return a sane service URL depending on the current environment.

    Parameters
    ----------
    container_url:
        Default URL used when the stack runs inside Docker.
    native_port:
        Host port exposed by the docker-compose stack. When the environment is
        marked as ``native`` we point the dashboard to ``http://localhost:<port>``.
    trailing_slash:
        Whether the returned URL should keep a trailing slash.
    """

    if is_native_environment():
        return _ensure_trailing_slash(
            f"http://localhost:{native_port}", trailing_slash=trailing_slash
        )
    return _ensure_trailing_slash(container_url, trailing_slash=trailing_slash)
