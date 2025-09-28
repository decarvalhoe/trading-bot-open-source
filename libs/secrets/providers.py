"""Providers for retrieving secrets from various backends."""
from __future__ import annotations

import json
import os
from typing import Mapping

from .base import SecretProvider


class EnvironmentSecretProvider:
    """Load secrets directly from environment variables."""

    name = "environment"

    def __init__(self, prefix: str | None = None) -> None:
        self._prefix = prefix or ""

    def get_secret(self, key: str) -> str | None:
        env_key = f"{self._prefix}{key}" if self._prefix else key
        return os.environ.get(env_key)


class VaultSecretProvider:
    """Retrieve secrets from HashiCorp Vault using the KV v2 engine."""

    name = "vault"

    def __init__(
        self,
        url: str,
        token: str,
        *,
        mount_point: str = "secret",
        base_path: str = "trading-bot",
        key_mapping: Mapping[str, str] | None = None,
    ) -> None:
        try:  # Import lazily to avoid making hvac a hard dependency.
            import hvac  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "hvac must be installed to use the Vault secret provider"
            ) from exc

        self._client = hvac.Client(url=url, token=token)
        self._exceptions = hvac.exceptions
        self._mount_point = mount_point
        self._base_path = base_path.strip("/")
        self._mapping = dict(key_mapping or {})

    def _resolve_path(self, key: str) -> str:
        return self._mapping.get(key, f"{self._base_path}/{key.lower()}").strip("/")

    def get_secret(self, key: str) -> str | None:
        path = self._resolve_path(key)
        try:
            response = self._client.secrets.kv.v2.read_secret_version(
                mount_point=self._mount_point,
                path=path,
            )
        except self._exceptions.InvalidPath:
            return None
        data = response.get("data", {}).get("data", {})
        if "value" in data:
            return data["value"]
        return data.get(key)


class DopplerSecretProvider:
    """Retrieve secrets from Doppler via its HTTP API."""

    name = "doppler"

    def __init__(
        self,
        token: str,
        *,
        config: str,
        project: str,
        base_url: str = "https://api.doppler.com",
        key_mapping: Mapping[str, str] | None = None,
    ) -> None:
        import requests

        self._requests = requests
        self._token = token
        self._config = config
        self._project = project
        self._base_url = base_url.rstrip("/")
        self._mapping = dict(key_mapping or {})

    def _resolve_key(self, key: str) -> str:
        return self._mapping.get(key, key)

    def get_secret(self, key: str) -> str | None:
        api_key = self._resolve_key(key)
        response = self._requests.get(
            f"{self._base_url}/v3/configs/config/secret",
            params={"project": self._project, "config": self._config, "name": api_key},
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=5,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload.get("secret", {}).get("raw")


class AWSSecretsManagerProvider:
    """Retrieve secrets from AWS Secrets Manager."""

    name = "aws-secrets-manager"

    def __init__(
        self,
        *,
        region_name: str,
        prefix: str = "",
        key_mapping: Mapping[str, str] | None = None,
        profile_name: str | None = None,
    ) -> None:
        try:  # pragma: no cover - optional dependency
            import boto3  # type: ignore
            session = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
            self._client = session.client("secretsmanager", region_name=region_name)
        except Exception as exc:  # pragma: no cover - requires AWS SDK
            raise RuntimeError(
                "boto3 must be installed and configured to use AWS Secrets Manager"
            ) from exc
        self._prefix = prefix
        self._mapping = dict(key_mapping or {})

    def _resolve_secret_id(self, key: str) -> str:
        if key in self._mapping:
            return self._mapping[key]
        return f"{self._prefix}{key}" if self._prefix else key

    def get_secret(self, key: str) -> str | None:
        secret_id = self._resolve_secret_id(key)
        response = self._client.get_secret_value(SecretId=secret_id)
        secret_string = response.get("SecretString")
        if secret_string is None:
            return None
        try:
            data = json.loads(secret_string)
        except json.JSONDecodeError:
            return secret_string
        return data.get(key) or data.get("value")


__all__ = [
    "EnvironmentSecretProvider",
    "VaultSecretProvider",
    "DopplerSecretProvider",
    "AWSSecretsManagerProvider",
]
