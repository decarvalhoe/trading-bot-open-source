from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_market_data"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")

    op.create_table(
        "market_data_ohlcv",
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("quote_volume", sa.Float, nullable=True),
        sa.Column("trades", sa.Integer, nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint(
            "exchange", "symbol", "interval", "timestamp", name="pk_market_data_ohlcv"
        ),
    )
    op.execute(
        "SELECT create_hypertable('market_data_ohlcv', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
    )

    op.create_table(
        "market_data_ticks",
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("size", sa.Float, nullable=True),
        sa.Column("side", sa.String(length=8), nullable=True),
        sa.Column("extra", postgresql.JSONB, nullable=True),
        sa.PrimaryKeyConstraint(
            "exchange", "symbol", "source", "timestamp", name="pk_market_data_ticks"
        ),
    )
    op.execute(
        "SELECT create_hypertable('market_data_ticks', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
    )

    op.create_index(
        "ix_market_data_ticks_symbol_ts",
        "market_data_ticks",
        ["symbol", "timestamp"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_data_ticks_symbol_ts", table_name="market_data_ticks")
    op.drop_table("market_data_ticks")
    op.drop_table("market_data_ohlcv")
