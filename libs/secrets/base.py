"""Common types for secret management providers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


class SecretProvider(Protocol):
    """Interface implemented by all secret providers."""

    name: str

    def get_secret(self, key: str) -> str | None:
        """Return the secret value for ``key``.

        Providers should return ``None`` when the secret cannot be located
        instead of raising an exception. Transient errors can still bubble up to
        help callers troubleshoot configuration issues.
        """


@dataclass(slots=True)
class SecretResolution:
    """Represents how a secret was resolved."""

    key: str
    provider: str
    value: str | None
    metadata: Mapping[str, str] | None = None


__all__ = ["SecretProvider", "SecretResolution"]
