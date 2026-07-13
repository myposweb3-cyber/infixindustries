"""Merge multiple migration heads for multi-company support

This migration merges all the previous independent migration branches
into a single linear history.

Revision ID: 003_merge_migrations
Revises: add_can_view_own_profile_001, add_profile_picture_to_users, 002_add_company_id
Create Date: 2026-04-06 22:56:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_merge_migrations'
down_revision = ('add_can_view_own_profile_001', 'add_profile_picture_to_users', '002_add_company_id')
branch_labels = None
depends_on = None


def upgrade():
    """Merge multiple migration branches - no changes needed."""
    pass


def downgrade():
    """Merge migration downgrade - no changes needed."""
    pass
