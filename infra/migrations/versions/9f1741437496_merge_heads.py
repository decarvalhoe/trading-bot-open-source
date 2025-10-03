"""Merge heads

Revision ID: 9f1741437496
Revises: 17d54bc596c1, 2a0f9a0cb742
Create Date: 2025-10-03 06:05:24.366119

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "9f1741437496"
down_revision = ('17d54bc596c1', '2a0f9a0cb742')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
