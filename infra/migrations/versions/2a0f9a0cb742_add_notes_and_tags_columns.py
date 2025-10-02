"""Add notes and tags columns to trading tables."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "2a0f9a0cb742"
down_revision = "6efde1f16e9f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "trading_orders",
        "notes",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.add_column(
        "trading_orders",
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "trading_executions",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "trading_executions",
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("trading_orders", "tags", server_default=None)
    op.alter_column("trading_executions", "tags", server_default=None)


def downgrade() -> None:
    op.drop_column("trading_executions", "tags")
    op.drop_column("trading_executions", "notes")
    op.drop_column("trading_orders", "tags")
    op.alter_column(
        "trading_orders",
        "notes",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
