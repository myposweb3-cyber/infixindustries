"""Add can_view_own_profile permission to users table.

Revision ID: add_can_view_own_profile_001
Revises: 
Create Date: 2026-04-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_can_view_own_profile_001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add the new column if it doesn't exist
    try:
        op.add_column('users', sa.Column('can_view_own_profile', sa.Boolean(), nullable=True, server_default='true'))
    except Exception as e:
        print(f"Column might already exist: {e}")


def downgrade():
    # This would be used to downgrade from this migration
    try:
        op.drop_column('users', 'can_view_own_profile')
    except Exception as e:
        print(f"Error downgrading: {e}")
