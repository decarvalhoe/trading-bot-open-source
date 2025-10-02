"""Add broker and venue columns to trading orders."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "6efde1f16e9f"
down_revision = "8595db87b446"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trading_orders",
        sa.Column(
            "broker",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column(
        "trading_orders",
        sa.Column(
            "venue",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'sandbox.internal'"),
        ),
    )
    op.create_index(
        op.f("ix_trading_orders_broker"),
        "trading_orders",
        ["broker"],
    )
    op.create_index(
        op.f("ix_trading_orders_venue"),
        "trading_orders",
        ["venue"],
    )
    op.alter_column("trading_orders", "broker", server_default=None)
    op.alter_column("trading_orders", "venue", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_trading_orders_venue"), table_name="trading_orders")
    op.drop_index(op.f("ix_trading_orders_broker"), table_name="trading_orders")
    op.drop_column("trading_orders", "venue")
    op.drop_column("trading_orders", "broker")
