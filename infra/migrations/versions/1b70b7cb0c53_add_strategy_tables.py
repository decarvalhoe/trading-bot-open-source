"""Create strategy management tables"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "1b70b7cb0c53"
down_revision = "9c4f7f5f7b2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_format", sa.String(length=16), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default=sa.text("'PENDING'")
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_backtest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
    )
    op.create_index(
        op.f("ix_strategies_strategy_type"), "strategies", ["strategy_type"], unique=False
    )
    op.create_index(op.f("ix_strategies_enabled"), "strategies", ["enabled"], unique=False)
    op.create_index(op.f("ix_strategies_status"), "strategies", ["status"], unique=False)

    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_format", sa.String(length=16), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE", name="fk_versions_strategy"
        ),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_versions_strategy_version"),
    )
    op.create_index(
        op.f("ix_strategy_versions_strategy_id"),
        "strategy_versions",
        ["strategy_id"],
        unique=False,
    )

    op.create_table(
        "strategy_executions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("venue", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("filled_quantity", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="CASCADE", name="fk_exec_strategy"
        ),
    )
    op.create_index(
        op.f("ix_strategy_executions_strategy_id"),
        "strategy_executions",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_executions_strategy_submitted_at",
        "strategy_executions",
        ["strategy_id", "submitted_at"],
        unique=False,
    )

    op.alter_column("strategies", "version", server_default=None)
    op.alter_column("strategies", "enabled", server_default=None)
    op.alter_column("strategies", "status", server_default=None)
    op.alter_column("strategies", "created_at", server_default=None)
    op.alter_column("strategies", "updated_at", server_default=None)
    op.alter_column("strategy_versions", "created_at", server_default=None)
    op.alter_column("strategy_executions", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_executions_strategy_submitted_at",
        table_name="strategy_executions",
    )
    op.drop_index(op.f("ix_strategy_executions_strategy_id"), table_name="strategy_executions")
    op.drop_table("strategy_executions")

    op.drop_index(op.f("ix_strategy_versions_strategy_id"), table_name="strategy_versions")
    op.drop_table("strategy_versions")

    op.drop_index(op.f("ix_strategies_status"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_enabled"), table_name="strategies")
    op.drop_index(op.f("ix_strategies_strategy_type"), table_name="strategies")
    op.drop_table("strategies")
