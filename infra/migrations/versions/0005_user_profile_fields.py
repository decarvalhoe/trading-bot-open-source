"""Remove legacy profile columns from the auth_user table."""

from __future__ import annotations

from typing import Iterable

from alembic import op
import sqlalchemy as sa

revision = "0005_user_profile_fields"
down_revision = "0004_auth_user_timestamps"
branch_labels = None
depends_on = None

_TABLE_NAME = "auth_user"
_PROFILE_COLUMNS: tuple[tuple[str, sa.TypeEngine, dict[str, object]], ...] = (
    ("first_name", sa.String(length=150), {}),
    ("last_name", sa.String(length=150), {}),
    ("phone", sa.String(length=64), {}),
    (
        "marketing_opt_in",
        sa.Boolean(),
        {"nullable": False, "server_default": sa.text("false")},
    ),
)


def _table_exists(connection, table_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = :table_name
            )
            """
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar())


def _existing_columns(connection, table_name: str) -> set[str]:
    result = connection.execute(
        sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row[0] for row in result}


def _drop_columns_if_exist(columns: Iterable[str]) -> None:
    connection = op.get_bind()
    if not _table_exists(connection, _TABLE_NAME):
        return

    existing = _existing_columns(connection, _TABLE_NAME)
    for column in columns:
        if column in existing:
            op.execute(
                sa.text(
                    f'ALTER TABLE "{_TABLE_NAME}" DROP COLUMN IF EXISTS "{column}"'
                )
            )


def _add_columns_if_missing(
    columns: Iterable[tuple[str, sa.TypeEngine, dict[str, object]]]
) -> None:
    connection = op.get_bind()
    if not _table_exists(connection, _TABLE_NAME):
        return

    existing = _existing_columns(connection, _TABLE_NAME)
    for name, column_type, kwargs in columns:
        if name in existing:
            continue

        column = sa.Column(name, column_type, **kwargs)
        op.add_column(_TABLE_NAME, column)
        # When a server_default was provided, drop it immediately to mimic the
        # behaviour of legacy schemas that did not persist defaults.
        if kwargs.get("server_default") is not None:
            op.execute(
                sa.text(
                    f'ALTER TABLE "{_TABLE_NAME}" ALTER COLUMN "{name}" DROP DEFAULT'
                )
            )


def upgrade() -> None:
    _drop_columns_if_exist(name for name, *_ in _PROFILE_COLUMNS)


def downgrade() -> None:
    _add_columns_if_missing(_PROFILE_COLUMNS)
