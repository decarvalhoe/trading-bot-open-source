"""add user broker credentials table

Revision ID: a2cba7eee9aa
Revises: 4d3f2c1f5b1a, b3e1c2d4e5f6
Create Date: 2025-10-03 11:18:45.120338

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a2cba7eee9aa"
down_revision = ("4d3f2c1f5b1a", "b3e1c2d4e5f6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_broker_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker", sa.String(length=64), nullable=False),
        sa.Column("api_key_encrypted", sa.String(length=1024), nullable=True),
        sa.Column("api_secret_encrypted", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "broker",
            name="uq_user_broker_credentials",
        ),
    )


def downgrade() -> None:
    op.drop_table("user_broker_credentials")
