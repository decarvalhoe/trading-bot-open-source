from __future__ import annotations

import os
import sys
import types
from importlib import util

from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from infra.audit_models import Base as AuditBase
from infra.entitlements_models import Base as EntitlementsBase
from infra.marketplace_models import Base as MarketplaceBase
from infra.social_models import Base as SocialBase
from infra.screener_models import ScreenerBase
from infra.trading_models import TradingBase
from infra.strategy_models import StrategyBase

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception as e:  # pragma: no cover - logging configuration is optional
        import logging
        logging.warning(f"Error configuring logging: {e}")


def _resolve_database_url() -> str:
    for env_var in ("ALEMBIC_DATABASE_URL", "DATABASE_URL"):
        value = os.getenv(env_var)
        if value:
            config.set_main_option("sqlalchemy.url", value)
            return value

    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url

    raise RuntimeError(
        "Database URL must be provided via ALEMBIC_DATABASE_URL or DATABASE_URL."
    )


def _ensure_package_hierarchy(module_name: str, module_path: Path) -> None:
    parts = module_name.split(".")
    for depth in range(1, len(parts)):
        package_name = ".".join(parts[:depth])
        if package_name in sys.modules:
            continue

        package = types.ModuleType(package_name)
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    if len(parts) > 1:
        parent_name = ".".join(parts[:-1])
        package = sys.modules[parent_name]
        package_paths = getattr(package, "__path__", [])
        path_str = str(module_path.parent)
        if path_str not in package_paths:
            package_paths = list(package_paths)
            package_paths.append(path_str)
            package.__path__ = package_paths  # type: ignore[attr-defined]


def _load_module_from_path(module_name: str, relative_path: str):
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / relative_path
    if not module_path.exists():
        raise FileNotFoundError(f"Cannot find module file at {module_path}.")

    _ensure_package_hierarchy(module_name, module_path)

    spec = util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module {module_name} from {module_path}.")

    module = util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _collect_target_metadata() -> tuple[MetaData, ...]:
    metadata = [
        AuditBase.metadata,
        EntitlementsBase.metadata,
        MarketplaceBase.metadata,
        SocialBase.metadata,
        ScreenerBase.metadata,
        TradingBase.metadata,
        StrategyBase.metadata,
    ]

    service_modules = [
        (
            "alembic.autoload.auth_service.app.models",
            "services/auth-service/app/models.py",
            (),
        ),
        (
            "alembic.autoload.user_service.app.main",
            "services/user-service/app/main.py",
            (
                (
                    "alembic.autoload.user_service.app.schemas",
                    "services/user-service/app/schemas.py",
                ),
            ),
        ),
        (
            "alembic.autoload.market_data.app.tables",
            "services/market_data/app/tables.py",
            (),
        ),
        (
            "alembic.autoload.reports.app.tables",
            "services/reports/app/tables.py",
            (),
        ),
    ]

    for module_name, relative_path, dependencies in service_modules:
        for dependency_name, dependency_path in dependencies:
            _load_module_from_path(dependency_name, dependency_path)

        module = _load_module_from_path(module_name, relative_path)
        base = getattr(module, "Base", None)
        if base is None:
            raise AttributeError(
                f"Module {module_name} does not define a SQLAlchemy Base class."
            )
        metadata.append(base.metadata)

    return tuple(metadata)


def _get_config_section() -> dict[str, str]:
    section = config.get_section(config.config_ini_section)
    if section is None:
        section = {}
    return section


target_metadata = _collect_target_metadata()
database_url = _resolve_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = _get_config_section()
    section["sqlalchemy.url"] = database_url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
