"""Ensure strategy identifiers use textual primary keys."""

from __future__ import annotations

import importlib

import sqlalchemy as sa
from alembic import op

base_migration = importlib.import_module(
    "infra.migrations.versions.0a9b90ff8c8f_convert_strategy_ids_to_strings"
)

revision = "4d3f2c1f5b1a"
down_revision = "0a9b90ff8c8f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind is None:
        return

    dialect = bind.dialect.name
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if base_migration.STRATEGY_TABLE not in table_names:
        return

    if dialect == "sqlite":
        base_migration._backfill_metadata(bind)
        return

    for table in (base_migration.STRATEGY_TABLE, *base_migration.RELATED_TABLES):
        if table in table_names:
            base_migration._drop_strategy_foreign_keys(bind, table)

    id_converted = base_migration._ensure_string_column(
        bind, dialect, base_migration.STRATEGY_TABLE, "id"
    )
    derived_converted = base_migration._ensure_string_column(
        bind, dialect, base_migration.STRATEGY_TABLE, "derived_from"
    )

    versions_has_fk = False
    if "strategy_versions" in table_names:
        versions_has_fk = base_migration._ensure_string_column(
            bind, dialect, "strategy_versions", "strategy_id"
        )
        base_migration._ensure_string_column(
            bind, dialect, "strategy_versions", "derived_from"
        )

    executions_has_fk = False
    if "strategy_executions" in table_names:
        executions_has_fk = base_migration._ensure_string_column(
            bind, dialect, "strategy_executions", "strategy_id"
        )

    backtests_has_fk = False
    if "strategy_backtests" in table_names:
        backtests_has_fk = base_migration._ensure_string_column(
            bind, dialect, "strategy_backtests", "strategy_id"
        )

    if derived_converted:
        op.create_foreign_key(
            "fk_strategies_derived_from",
            source_table=base_migration.STRATEGY_TABLE,
            referent_table=base_migration.STRATEGY_TABLE,
            local_cols=["derived_from"],
            remote_cols=["id"],
            ondelete="SET NULL",
        )

    if versions_has_fk:
        base_migration._recreate_foreign_keys("strategy_versions")
    if executions_has_fk:
        base_migration._recreate_foreign_keys("strategy_executions")
    if backtests_has_fk:
        base_migration._recreate_foreign_keys("strategy_backtests")

    if id_converted:
        base_migration._backfill_metadata(bind)
    else:
        # Ensure metadata is backfilled even if conversion already occurred.
        base_migration._backfill_metadata(bind)


def downgrade() -> None:
    raise NotImplementedError("Downgrade not supported for identifier migration")
