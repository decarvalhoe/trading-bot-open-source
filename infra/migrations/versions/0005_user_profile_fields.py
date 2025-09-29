"""Replace user profile columns with first/last name and phone."""

from alembic import op
import sqlalchemy as sa

revision = "0005_user_profile_fields"
down_revision = "0004_auth_user_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("first_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=32), nullable=True),
    )
    op.drop_column("users", "display_name")
    op.drop_column("users", "full_name")
    op.drop_column("users", "locale")


def downgrade():
    op.add_column(
        "users",
        sa.Column("locale", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("display_name", sa.String(length=120), nullable=True),
    )
    op.drop_column("users", "phone")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
