from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b8c9d0e1f2"
down_revision = "17d54bc596c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("market_data_ohlcv", schema=None) as batch_op:
        batch_op.drop_constraint("uq_ohlcv_bar", type_="unique")
        batch_op.drop_constraint("market_data_ohlcv_pkey", type_="primary")
        batch_op.drop_column("id")
        batch_op.create_primary_key(
            "pk_market_data_ohlcv", ["exchange", "symbol", "interval", "timestamp"]
        )

    op.execute("DROP SEQUENCE IF EXISTS market_data_ohlcv_id_seq")

    with op.batch_alter_table("market_data_ticks", schema=None) as batch_op:
        batch_op.drop_constraint("uq_tick", type_="unique")
        batch_op.drop_constraint("market_data_ticks_pkey", type_="primary")
        batch_op.drop_column("id")
        batch_op.create_primary_key(
            "pk_market_data_ticks", ["exchange", "symbol", "source", "timestamp"]
        )

    op.execute("DROP SEQUENCE IF EXISTS market_data_ticks_id_seq")

    op.execute(
        "SELECT create_hypertable('market_data_ohlcv', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
    )
    op.execute(
        "SELECT create_hypertable('market_data_ticks', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
    )


def downgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS market_data_ohlcv_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS market_data_ticks_id_seq")

    with op.batch_alter_table("market_data_ohlcv", schema=None) as batch_op:
        batch_op.drop_constraint("pk_market_data_ohlcv", type_="primary")
        batch_op.add_column(
            sa.Column(
                "id",
                sa.BigInteger(),
                server_default=sa.text("nextval('market_data_ohlcv_id_seq'::regclass)"),
                nullable=False,
            )
        )
        batch_op.create_primary_key("market_data_ohlcv_pkey", ["id"])
        batch_op.create_unique_constraint(
            "uq_ohlcv_bar", ["exchange", "symbol", "interval", "timestamp"]
        )

    with op.batch_alter_table("market_data_ticks", schema=None) as batch_op:
        batch_op.drop_constraint("pk_market_data_ticks", type_="primary")
        batch_op.add_column(
            sa.Column(
                "id",
                sa.BigInteger(),
                server_default=sa.text("nextval('market_data_ticks_id_seq'::regclass)"),
                nullable=False,
            )
        )
        batch_op.create_primary_key("market_data_ticks_pkey", ["id"])
        batch_op.create_unique_constraint(
            "uq_tick", ["exchange", "symbol", "timestamp", "source"]
        )

    op.execute(
        "ALTER SEQUENCE market_data_ohlcv_id_seq OWNED BY market_data_ohlcv.id"
    )
    op.execute(
        "ALTER SEQUENCE market_data_ticks_id_seq OWNED BY market_data_ticks.id"
    )
