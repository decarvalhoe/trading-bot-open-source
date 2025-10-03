"""Add trading orders and executions tables.

Revision ID: 8595db87b446
Revises: 0005_user_profile_fields
Create Date: 2025-09-29 03:32:52.611831

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "8595db87b446"
down_revision = "0005_user_profile_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_orders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("external_order_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("stop_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_order_id"),
    )
    op.create_index(
        "ix_trading_orders_account_created_at",
        "trading_orders",
        ["account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_orders_account_id"),
        "trading_orders",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_orders_correlation_id"),
        "trading_orders",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_orders_symbol"),
        "trading_orders",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_trading_orders_symbol_created_at",
        "trading_orders",
        ["symbol", "created_at"],
        unique=False,
    )
    op.create_table(
        "trading_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("external_execution_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("fees", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("liquidity", sa.String(length=16), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["order_id"], ["trading_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_execution_id"),
    )
    op.create_index(
        "ix_trading_executions_account_executed_at",
        "trading_executions",
        ["account_id", "executed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_executions_account_id"),
        "trading_executions",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_executions_correlation_id"),
        "trading_executions",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_executions_order_id"),
        "trading_executions",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_executions_symbol"),
        "trading_executions",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        "ix_trading_executions_symbol_executed_at",
        "trading_executions",
        ["symbol", "executed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trading_executions_symbol_executed_at",
        table_name="trading_executions",
    )
    op.drop_index(
        op.f("ix_trading_executions_symbol"),
        table_name="trading_executions",
    )
    op.drop_index(
        op.f("ix_trading_executions_order_id"),
        table_name="trading_executions",
    )
    op.drop_index(
        op.f("ix_trading_executions_correlation_id"),
        table_name="trading_executions",
    )
    op.drop_index(
        op.f("ix_trading_executions_account_id"),
        table_name="trading_executions",
    )
    op.drop_index(
        "ix_trading_executions_account_executed_at",
        table_name="trading_executions",
    )
    op.drop_table("trading_executions")
    op.drop_index(
        "ix_trading_orders_symbol_created_at",
        table_name="trading_orders",
    )
    op.drop_index(op.f("ix_trading_orders_symbol"), table_name="trading_orders")
    op.drop_index(
        op.f("ix_trading_orders_correlation_id"),
        table_name="trading_orders",
    )
    op.drop_index(op.f("ix_trading_orders_account_id"), table_name="trading_orders")
    op.drop_index(
        "ix_trading_orders_account_created_at",
        table_name="trading_orders",
    )
    op.drop_table("trading_orders")
