"""Environment helpers for resolving connection URLs.

These utilities centralize how services derive connection strings so we can
support both Docker-based development and native execution on the host
machine. The helpers look at specific environment variables first and then
fall back to shared defaults that adapt when ``ENVIRONMENT=native``.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

DEFAULT_POSTGRES_DSN_DOCKER = "postgresql+psycopg2://trading:trading@postgres:5432/trading"
DEFAULT_POSTGRES_DSN_NATIVE = "postgresql+psycopg2://trading:trading@localhost:5432/trading"

DEFAULT_REDIS_URL_DOCKER = "redis://redis:6379/0"
DEFAULT_REDIS_URL_NATIVE = "redis://localhost:6379/0"

DEFAULT_RABBITMQ_URL_DOCKER = "amqp://guest:guest@rabbitmq:5672//"
DEFAULT_RABBITMQ_URL_NATIVE = "amqp://guest:guest@localhost:5672//"


def get_environment(default: str = "dev") -> str:
    """Return the active environment name.

    The value is read from the ``ENVIRONMENT`` variable if present and
    normalized to lowercase. When the variable is missing ``default`` is
    returned.
    """

    return os.getenv("ENVIRONMENT", default).strip().lower()


def is_native_environment(env: str | None = None) -> bool:
    """Return ``True`` when the environment corresponds to ``native``."""

    env_name = env if env is not None else get_environment()
    return env_name.lower() == "native"


def _choose_native_aware_default(docker_default: str, native_default: str) -> str:
    """Select the appropriate default based on the active environment."""

    if is_native_environment():
        return native_default
    return docker_default


def get_database_url(*, env_var: str | None = None) -> str:
    """Return the database URL for the current environment.

    ``env_var`` allows callers to prioritise a service specific variable while
    still falling back to ``DATABASE_URL`` or ``POSTGRES_DSN`` when available.
    When none of these variables are defined a sensible default is returned
    that points to the Docker network or ``localhost`` for native execution.
    """

    env_vars: list[str | None] = []
    if env_var:
        env_vars.append(env_var)
    env_vars.extend(["DATABASE_URL", "POSTGRES_DSN"])
    for variable in env_vars:
        if not variable:
            continue
        value = os.getenv(variable)
        if value:
            return value
    return _choose_native_aware_default(
        DEFAULT_POSTGRES_DSN_DOCKER, DEFAULT_POSTGRES_DSN_NATIVE
    )


def _replace_redis_database(url: str, database: int) -> str:
    """Return ``url`` with its database component replaced by ``database``."""

    parsed = urlsplit(url)
    new_path = f"/{database}"
    return urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))


def get_redis_url(*, env_var: str | None = None, database: int | None = None) -> str:
    """Return the Redis URL honouring service specific overrides.

    ``env_var`` can be provided for service-specific configuration. If neither
    it nor ``REDIS_URL`` is set, an environment aware default is used. When the
    URL comes from defaults the ``database`` parameter can adjust the DB index
    while preserving the host and credentials.
    """

    env_vars: list[str | None] = []
    if env_var:
        env_vars.append(env_var)
    env_vars.append("REDIS_URL")
    for variable in env_vars:
        if not variable:
            continue
        value = os.getenv(variable)
        if value:
            return value

    base_url = _choose_native_aware_default(
        DEFAULT_REDIS_URL_DOCKER, DEFAULT_REDIS_URL_NATIVE
    )
    if database is None:
        return base_url
    return _replace_redis_database(base_url, database)


def get_rabbitmq_url(*, env_var: str | None = None) -> str:
    """Return the RabbitMQ connection URL for the active environment."""

    env_vars: list[str | None] = []
    if env_var:
        env_vars.append(env_var)
    env_vars.append("RABBITMQ_URL")
    for variable in env_vars:
        if not variable:
            continue
        value = os.getenv(variable)
        if value:
            return value

    return _choose_native_aware_default(
        DEFAULT_RABBITMQ_URL_DOCKER, DEFAULT_RABBITMQ_URL_NATIVE
    )


__all__ = [
    "DEFAULT_POSTGRES_DSN_DOCKER",
    "DEFAULT_POSTGRES_DSN_NATIVE",
    "DEFAULT_REDIS_URL_DOCKER",
    "DEFAULT_REDIS_URL_NATIVE",
    "DEFAULT_RABBITMQ_URL_DOCKER",
    "DEFAULT_RABBITMQ_URL_NATIVE",
    "get_database_url",
    "get_environment",
    "get_redis_url",
    "get_rabbitmq_url",
    "is_native_environment",
]
