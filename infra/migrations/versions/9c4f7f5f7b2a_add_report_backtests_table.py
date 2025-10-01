"""Add report backtests table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "9c4f7f5f7b2a"
down_revision = "8f7b4a1e5b6c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_backtests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("account", sa.String(length=64), nullable=True),
        sa.Column("initial_balance", sa.Float(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_return", sa.Float(), nullable=False),
        sa.Column("max_drawdown", sa.Float(), nullable=False),
        sa.Column("equity_curve", sa.JSON(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("metrics_path", sa.String(length=512), nullable=True),
        sa.Column("log_path", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(op.f("ix_report_backtests_strategy_id"), "report_backtests", ["strategy_id"])
    op.create_index(op.f("ix_report_backtests_symbol"), "report_backtests", ["symbol"])
    op.create_index(op.f("ix_report_backtests_account"), "report_backtests", ["account"])
    op.alter_column("report_backtests", "trades", server_default=None)
    op.alter_column("report_backtests", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_report_backtests_account"), table_name="report_backtests")
    op.drop_index(op.f("ix_report_backtests_symbol"), table_name="report_backtests")
    op.drop_index(op.f("ix_report_backtests_strategy_id"), table_name="report_backtests")
    op.drop_table("report_backtests")
