from alembic import op

revision = "0004_auth_user_timestamps"
down_revision = "0003_screener"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE IF EXISTS auth_user
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        """
    )
    op.execute(
        """
        ALTER TABLE IF EXISTS auth_user
        ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS auth_user DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE IF EXISTS auth_user DROP COLUMN IF EXISTS created_at")
