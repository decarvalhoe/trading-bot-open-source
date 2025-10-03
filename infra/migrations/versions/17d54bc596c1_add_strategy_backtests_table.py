"""Add strategy backtests table"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "17d54bc596c1"
down_revision = "1b70b7cb0c53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_backtests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=36), nullable=False),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', now())"),
        ),
        sa.Column("initial_balance", sa.Float(), nullable=False),
        sa.Column("profit_loss", sa.Float(), nullable=False),
        sa.Column("total_return", sa.Float(), nullable=False),
        sa.Column("max_drawdown", sa.Float(), nullable=False),
        sa.Column("equity_curve", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="CASCADE",
            name="fk_strategy_backtests_strategy",
        ),
    )
    op.create_index(
        op.f("ix_strategy_backtests_strategy_id"),
        "strategy_backtests",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_strategy_backtests_ran_at"),
        "strategy_backtests",
        ["ran_at"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_backtests_strategy_ran_at",
        "strategy_backtests",
        ["strategy_id", "ran_at"],
        unique=False,
    )
    op.alter_column("strategy_backtests", "ran_at", server_default=None)


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_backtests_strategy_ran_at",
        table_name="strategy_backtests",
    )
    op.drop_index(
        op.f("ix_strategy_backtests_ran_at"),
        table_name="strategy_backtests",
    )
    op.drop_index(
        op.f("ix_strategy_backtests_strategy_id"),
        table_name="strategy_backtests",
    )
    op.drop_table("strategy_backtests")
