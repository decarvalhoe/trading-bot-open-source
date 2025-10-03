"""Convert strategy identifiers from integers to strings"""

from __future__ import annotations

import json
from typing import Iterable

import sqlalchemy as sa
from alembic import op

from infra.strategy_models import (
    StrategyBase,
    Strategy,
    StrategyBacktest,
    StrategyExecution,
    StrategyVersion,
)

revision = "0a9b90ff8c8f"
down_revision = "1b70b7cb0c53"
branch_labels = None
depends_on = None


STRATEGY_TABLE = "strategies"
RELATED_TABLES: tuple[str, ...] = (
    "strategy_versions",
    "strategy_executions",
    "strategy_backtests",
)


def _get_column_info(
    bind: sa.engine.Connection, table: str, column: str
) -> dict[str, object] | None:
    inspector = sa.inspect(bind)
    for info in inspector.get_columns(table):
        if info["name"] == column:
            return info
    return None


def _drop_strategy_foreign_keys(bind: sa.engine.Connection, table: str) -> None:
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys(table):
        if fk.get("name") and fk.get("referred_table") == STRATEGY_TABLE:
            op.drop_constraint(fk["name"], table_name=table, type_="foreignkey")


def _alter_to_string(
    table: str,
    column: str,
    *,
    nullable: bool,
    dialect: str,
    using: str | None = None,
) -> None:
    if dialect == "postgresql":
        op.alter_column(
            table,
            column,
            type_=sa.String(length=36),
            existing_type=sa.Integer(),
            existing_nullable=nullable,
            server_default=None,
            postgresql_using=using or f"{column}::text",
        )
    else:
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.alter_column(
                column,
                type_=sa.String(length=36),
                existing_type=sa.Integer(),
                existing_nullable=nullable,
                server_default=None,
            )


def _cast_column_textually(table: str, column: str) -> None:
    op.execute(
        sa.text(
            f"UPDATE {table} "
            f"SET {column} = CAST({column} AS TEXT) "
            f"WHERE {column} IS NOT NULL"
        )
    )


def _backfill_metadata(bind: sa.engine.Connection) -> None:
    metadata = sa.MetaData()
    strategies = sa.Table(STRATEGY_TABLE, metadata, autoload_with=bind)
    session = sa.orm.Session(bind=bind)
    try:
        rows = session.execute(sa.select(strategies.c.id, strategies.c.metadata)).all()
        for identifier, meta in rows:
            value = meta
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = {}
            if not isinstance(value, dict):
                value = {}
            string_id = str(identifier) if identifier is not None else None
            if not string_id:
                continue
            if value.get("strategy_id") != string_id:
                value["strategy_id"] = string_id
                session.execute(
                    strategies.update()
                    .where(strategies.c.id == identifier)
                    .values({"metadata": value})
                )
        session.commit()
    finally:
        session.close()


def _recreate_foreign_keys(table: str) -> None:
    if table == "strategy_versions":
        op.create_foreign_key(
            "fk_strategy_versions_strategy",
            source_table=table,
            referent_table=STRATEGY_TABLE,
            local_cols=["strategy_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )
    elif table == "strategy_executions":
        op.create_foreign_key(
            "fk_strategy_executions_strategy",
            source_table=table,
            referent_table=STRATEGY_TABLE,
            local_cols=["strategy_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )
    elif table == "strategy_backtests":
        op.create_foreign_key(
            "fk_strategy_backtests_strategy",
            source_table=table,
            referent_table=STRATEGY_TABLE,
            local_cols=["strategy_id"],
            remote_cols=["id"],
            ondelete="CASCADE",
        )


def _ensure_string_column(
    bind: sa.engine.Connection,
    dialect: str,
    table: str,
    column: str,
) -> bool:
    info = _get_column_info(bind, table, column)
    if info is None:
        return False
    if isinstance(info["type"], sa.String):
        return True
    nullable = bool(info.get("nullable", True))
    using_clause = f"{column}::text" if dialect == "postgresql" else None
    _alter_to_string(table, column, nullable=nullable, dialect=dialect, using=using_clause)
    if dialect != "postgresql":
        _cast_column_textually(table, column)
    return True


def upgrade() -> None:
    bind = op.get_bind()
    if bind is None:
        return
    dialect = bind.dialect.name

    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if STRATEGY_TABLE not in table_names:
        return

    if dialect == "sqlite":
        _upgrade_sqlite(bind, table_names)
        _backfill_metadata(bind)
        return

    disable_fk = dialect == "sqlite"
    if disable_fk:
        op.execute(sa.text("PRAGMA foreign_keys=OFF"))

    try:
        # Drop foreign keys referencing strategies to allow column type changes
        _drop_strategy_foreign_keys(bind, STRATEGY_TABLE)
        for related in RELATED_TABLES:
            if related in table_names:
                _drop_strategy_foreign_keys(bind, related)

        # Convert strategy identifiers and lineage references to strings
        id_converted = _ensure_string_column(bind, dialect, STRATEGY_TABLE, "id")
        has_derived_from = _ensure_string_column(bind, dialect, STRATEGY_TABLE, "derived_from")

        # Convert foreign key columns in related tables
        versions_has_fk = False
        if "strategy_versions" in table_names:
            versions_has_fk = _ensure_string_column(bind, dialect, "strategy_versions", "strategy_id")
            _ensure_string_column(bind, dialect, "strategy_versions", "derived_from")

        executions_has_fk = False
        if "strategy_executions" in table_names:
            executions_has_fk = _ensure_string_column(bind, dialect, "strategy_executions", "strategy_id")

        backtests_has_fk = False
        if "strategy_backtests" in table_names:
            backtests_has_fk = _ensure_string_column(bind, dialect, "strategy_backtests", "strategy_id")

        # Recreate foreign keys with the new type definitions
        if has_derived_from:
            op.create_foreign_key(
                "fk_strategies_derived_from",
                source_table=STRATEGY_TABLE,
                referent_table=STRATEGY_TABLE,
                local_cols=["derived_from"],
                remote_cols=["id"],
                ondelete="SET NULL",
            )

        if versions_has_fk:
            _recreate_foreign_keys("strategy_versions")
        if executions_has_fk:
            _recreate_foreign_keys("strategy_executions")
        if backtests_has_fk:
            _recreate_foreign_keys("strategy_backtests")

        # Backfill metadata so existing rows expose string identifiers
        if id_converted:
            _backfill_metadata(bind)
    finally:
        if disable_fk:
            op.execute(sa.text("PRAGMA foreign_keys=ON"))


def _upgrade_sqlite(bind: sa.engine.Connection, table_names: set[str]) -> None:
    def _coerce_json(value: object) -> object:
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode()
            except Exception:
                return None
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    strategy_table = sa.Table(STRATEGY_TABLE, sa.MetaData(), autoload_with=bind)
    strategy_rows = bind.execute(sa.select(strategy_table)).mappings().all()

    def _clean_payload(payload: dict[str, object]) -> dict[str, object]:
        return {key: value for key, value in payload.items() if value is not None}

    version_rows = []
    if "strategy_versions" in table_names:
        versions = sa.Table("strategy_versions", sa.MetaData(), autoload_with=bind)
        version_rows = bind.execute(sa.select(versions)).mappings().all()

    execution_rows = []
    if "strategy_executions" in table_names:
        executions = sa.Table("strategy_executions", sa.MetaData(), autoload_with=bind)
        execution_rows = bind.execute(sa.select(executions)).mappings().all()

    backtest_rows = []
    if "strategy_backtests" in table_names:
        backtests = sa.Table("strategy_backtests", sa.MetaData(), autoload_with=bind)
        backtest_rows = bind.execute(sa.select(backtests)).mappings().all()

    json_columns: dict[str, tuple[str, ...]] = {
        STRATEGY_TABLE: ("parameters", "tags", "metadata", "last_backtest"),
        "strategy_versions": ("parameters", "tags", "metadata"),
        "strategy_executions": ("payload",),
        "strategy_backtests": ("equity_curve", "summary"),
    }

    op.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        StrategyBacktest.__table__.drop(bind=bind, checkfirst=True)
        StrategyExecution.__table__.drop(bind=bind, checkfirst=True)
        StrategyVersion.__table__.drop(bind=bind, checkfirst=True)
        Strategy.__table__.drop(bind=bind, checkfirst=True)

        Strategy.__table__.create(bind=bind)
        StrategyVersion.__table__.create(bind=bind)
        StrategyExecution.__table__.create(bind=bind)
        StrategyBacktest.__table__.create(bind=bind)
        try:
            bind.commit()
        except Exception:
            pass
        existing_tables = {
            row[0]
            for row in bind.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        expected_tables = {
            STRATEGY_TABLE,
            "strategy_versions",
            "strategy_executions",
            "strategy_backtests",
        }
        missing_tables = expected_tables - existing_tables
        if missing_tables:
            raise RuntimeError(
                f"Failed to recreate strategy tables: {', '.join(sorted(missing_tables))}"
            )

        strategy_payloads: list[dict[str, object]] = []
        for row in strategy_rows:
            payload = dict(row)
            identifier = row.get("id")
            if identifier is not None:
                payload["id"] = str(identifier)
            parent = row.get("derived_from")
            if parent is not None:
                payload["derived_from"] = str(parent)
            for column in json_columns.get(STRATEGY_TABLE, ()):  # pragma: no branch
                if column in payload:
                    payload[column] = _coerce_json(payload[column])
                    if (
                        column == "metadata"
                        and isinstance(payload[column], dict)
                        and payload[column].get("strategy_id") is not None
                    ):
                        payload[column]["strategy_id"] = str(payload[column]["strategy_id"])
            payload = _clean_payload(payload)
            strategy_payloads.append(payload)
            bind.execute(sa.insert(Strategy.__table__).values(**payload))

        version_payloads: list[dict[str, object]] = []
        for row in version_rows:
            payload = dict(row)
            identifier = row.get("strategy_id")
            if identifier is not None:
                payload["strategy_id"] = str(identifier)
            parent = row.get("derived_from")
            if parent is not None:
                payload["derived_from"] = str(parent)
            for column in json_columns.get("strategy_versions", ()):  # pragma: no branch
                if column in payload:
                    payload[column] = _coerce_json(payload[column])
                    if (
                        column == "metadata"
                        and isinstance(payload[column], dict)
                        and payload[column].get("strategy_id") is not None
                    ):
                        payload[column]["strategy_id"] = str(payload[column]["strategy_id"])
            payload = _clean_payload(payload)
            version_payloads.append(payload)
            bind.execute(sa.insert(StrategyVersion.__table__).values(**payload))

        execution_payloads: list[dict[str, object]] = []
        for row in execution_rows:
            payload = dict(row)
            identifier = row.get("strategy_id")
            if identifier is not None:
                payload["strategy_id"] = str(identifier)
            for column in json_columns.get("strategy_executions", ()):  # pragma: no branch
                if column in payload:
                    payload[column] = _coerce_json(payload[column])
            payload = _clean_payload(payload)
            execution_payloads.append(payload)
            bind.execute(sa.insert(StrategyExecution.__table__).values(**payload))

        backtest_payloads: list[dict[str, object]] = []
        for row in backtest_rows:
            payload = dict(row)
            identifier = row.get("strategy_id")
            if identifier is not None:
                payload["strategy_id"] = str(identifier)
            for column in json_columns.get("strategy_backtests", ()):  # pragma: no branch
                if column in payload:
                    payload[column] = _coerce_json(payload[column])
            payload = _clean_payload(payload)
            backtest_payloads.append(payload)
            bind.execute(sa.insert(StrategyBacktest.__table__).values(**payload))
        bind.commit()
    finally:
        op.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for identifier migration")
