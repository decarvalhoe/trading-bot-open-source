from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b8c9d0e1f2"
down_revision = "17d54bc596c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = set(inspector.get_table_names())

    if "market_data_ohlcv" in table_names:
        ohlcv_columns = {col["name"] for col in inspector.get_columns("market_data_ohlcv")}
        ohlcv_unique = {uc["name"] for uc in inspector.get_unique_constraints("market_data_ohlcv")}
        ohlcv_pk = inspector.get_pk_constraint("market_data_ohlcv")

        with op.batch_alter_table("market_data_ohlcv", schema=None) as batch_op:
            if "uq_ohlcv_bar" in ohlcv_unique:
                batch_op.drop_constraint("uq_ohlcv_bar", type_="unique")

            needs_primary_key = False
            if ohlcv_pk and ohlcv_pk.get("name") == "market_data_ohlcv_pkey":
                batch_op.drop_constraint("market_data_ohlcv_pkey", type_="primary")
                needs_primary_key = True

            if "id" in ohlcv_columns:
                batch_op.drop_column("id")
                needs_primary_key = True

            if needs_primary_key:
                batch_op.create_primary_key(
                    "pk_market_data_ohlcv",
                    ["exchange", "symbol", "interval", "timestamp"],
                )

        op.execute("DROP SEQUENCE IF EXISTS market_data_ohlcv_id_seq")

    if "market_data_ticks" in table_names:
        ticks_columns = {col["name"] for col in inspector.get_columns("market_data_ticks")}
        ticks_unique = {uc["name"] for uc in inspector.get_unique_constraints("market_data_ticks")}
        ticks_pk = inspector.get_pk_constraint("market_data_ticks")

        with op.batch_alter_table("market_data_ticks", schema=None) as batch_op:
            if "uq_tick" in ticks_unique:
                batch_op.drop_constraint("uq_tick", type_="unique")

            needs_primary_key = False
            if ticks_pk and ticks_pk.get("name") == "market_data_ticks_pkey":
                batch_op.drop_constraint("market_data_ticks_pkey", type_="primary")
                needs_primary_key = True

            if "id" in ticks_columns:
                batch_op.drop_column("id")
                needs_primary_key = True

            if needs_primary_key:
                batch_op.create_primary_key(
                    "pk_market_data_ticks",
                    ["exchange", "symbol", "source", "timestamp"],
                )

        op.execute("DROP SEQUENCE IF EXISTS market_data_ticks_id_seq")

    if "market_data_ohlcv" in table_names:
        op.execute(
            "SELECT create_hypertable('market_data_ohlcv', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);"
        )

    if "market_data_ticks" in table_names:
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
