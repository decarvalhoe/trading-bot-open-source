"""Shared configuration helpers for the web dashboard service."""

from __future__ import annotations

import os

from libs.env import is_native_environment


def _ensure_trailing_slash(value: str, *, trailing_slash: bool) -> str:
    """Normalise trailing slashes according to the desired style."""

    trimmed = value.rstrip("/")
    if trailing_slash:
        return f"{trimmed}/"
    return trimmed


def _native_base_url(*, port: int, scheme: str = "http") -> str:
    """Return the native base URL for the provided ``port``.

    The hostname can be overridden via ``WEB_DASHBOARD_NATIVE_HOST`` when the
    default ``localhost`` resolution is not desirable (e.g. containerised proxy
    setups or Windows/WSL). Empty values fallback to ``localhost`` to avoid
    returning malformed URLs.
    """

    host = os.getenv("WEB_DASHBOARD_NATIVE_HOST", "localhost").strip() or "localhost"
    return f"{scheme}://{host}:{port}"


def default_service_url(
    container_url: str,
    *,
    native_port: int,
    trailing_slash: bool = True,
    native_scheme: str = "http",
) -> str:
    """Return a sane service URL depending on the current environment.

    Parameters
    ----------
    container_url:
        Default URL used when the stack runs inside Docker.
    native_port:
        Host port exposed by the docker-compose stack. When the environment is
        marked as ``native`` we point the dashboard to ``WEB_DASHBOARD_NATIVE_HOST``
        (``localhost`` by default).
    trailing_slash:
        Whether the returned URL should keep a trailing slash.
    native_scheme:
        Scheme used for native URLs. ``http`` works for most localhost setups
        but can be overridden for HTTPS forwarders.

    """

    if is_native_environment():
        return _ensure_trailing_slash(
            _native_base_url(port=native_port, scheme=native_scheme),
            trailing_slash=trailing_slash,
        )
    return _ensure_trailing_slash(container_url, trailing_slash=trailing_slash)
