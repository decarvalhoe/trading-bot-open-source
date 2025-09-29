from alembic import op
import sqlalchemy as sa


revision = '0004_auth_user_timestamps'
down_revision = '0003_screener'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'),
            nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('NOW()'),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'created_at')
