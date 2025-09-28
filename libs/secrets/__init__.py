"""Unified interface for loading application secrets."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Callable, Mapping

from .base import SecretProvider, SecretResolution
from .providers import (
    AWSSecretsManagerProvider,
    DopplerSecretProvider,
    EnvironmentSecretProvider,
    VaultSecretProvider,
)

SecretResolver = Callable[[str, str | None], str | None]


class SecretManager:
    """Resolve secrets from configured providers with optional caching."""

    def __init__(self, provider: SecretProvider, *, cache_enabled: bool = True) -> None:
        self._provider = provider
        self._cache_enabled = cache_enabled
        self._cache: dict[str, str | None] = {}

    @property
    def provider(self) -> SecretProvider:
        return self._provider

    def get(self, key: str, default: str | None = None) -> str | None:
        if self._cache_enabled and key in self._cache:
            return self._cache[key] if self._cache[key] is not None else default

        value = None
        try:
            value = self._provider.get_secret(key)
        except Exception as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(
                f"Unable to resolve secret '{key}' using provider '{self._provider.name}'"
            ) from exc

        if self._cache_enabled:
            self._cache[key] = value

        return value if value is not None else default

    def resolve(self, key: str, default: str | None = None) -> SecretResolution:
        value = self.get(key, default=default)
        return SecretResolution(key=key, provider=self._provider.name, value=value)


def _load_key_mapping() -> Mapping[str, str]:
    raw_mapping = os.environ.get("SECRET_MANAGER_KEY_MAPPING")
    if not raw_mapping:
        return {}
    try:
        parsed = json.loads(raw_mapping)
    except json.JSONDecodeError as exc:  # pragma: no cover - configuration error
        raise RuntimeError("SECRET_MANAGER_KEY_MAPPING must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("SECRET_MANAGER_KEY_MAPPING must be a JSON object")
    return parsed


def _build_provider() -> SecretProvider:
    provider = os.environ.get("SECRET_MANAGER_PROVIDER", "environment").strip().lower()
    mapping = _load_key_mapping()

    if provider in {"env", "environment", "local"}:
        prefix = os.environ.get("SECRET_MANAGER_ENV_PREFIX")
        return EnvironmentSecretProvider(prefix=prefix)
    if provider == "vault":
        url = os.environ.get("VAULT_ADDR")
        token = os.environ.get("VAULT_TOKEN")
        if not url or not token:
            raise RuntimeError("VAULT_ADDR and VAULT_TOKEN must be set for Vault provider")
        mount_point = os.environ.get("VAULT_KV_MOUNT", "secret")
        base_path = os.environ.get("VAULT_SECRET_BASE_PATH", "trading-bot")
        return VaultSecretProvider(
            url=url,
            token=token,
            mount_point=mount_point,
            base_path=base_path,
            key_mapping=mapping,
        )
    if provider in {"doppler", "doppler.com"}:
        token = os.environ.get("DOPPLER_TOKEN")
        config = os.environ.get("DOPPLER_CONFIG")
        project = os.environ.get("DOPPLER_PROJECT")
        if not token or not config or not project:
            raise RuntimeError(
                "DOPPLER_TOKEN, DOPPLER_CONFIG and DOPPLER_PROJECT must be set for the Doppler provider"
            )
        base_url = os.environ.get("DOPPLER_API_URL", "https://api.doppler.com")
        return DopplerSecretProvider(
            token=token,
            config=config,
            project=project,
            base_url=base_url,
            key_mapping=mapping,
        )
    if provider in {"aws", "aws-secrets-manager", "secretsmanager"}:
        region_name = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
        if not region_name:
            raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION must be set for AWS Secrets Manager")
        prefix = os.environ.get("AWS_SECRETS_PREFIX", "")
        profile_name = os.environ.get("AWS_PROFILE")
        return AWSSecretsManagerProvider(
            region_name=region_name,
            prefix=prefix,
            profile_name=profile_name,
            key_mapping=mapping,
        )

    raise RuntimeError(f"Unknown secret manager provider: {provider}")


@lru_cache(maxsize=1)
def get_secret_manager() -> SecretManager:
    return SecretManager(_build_provider())


def get_secret(key: str, default: str | None = None) -> str | None:
    """Convenience wrapper used by services to access secrets."""

    manager = get_secret_manager()
    return manager.get(key, default=default)


__all__ = ["SecretManager", "get_secret_manager", "get_secret"]
