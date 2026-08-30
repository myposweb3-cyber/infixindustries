"""Merge the existing migration branches into one head.

Revision ID: 007_merge_existing_heads
Revises: 003_merge_migrations, 006_add_inventory_batches, deprecated_add_company_id
"""

revision = '007_merge_existing_heads'
down_revision = (
    '003_merge_migrations',
    '006_add_inventory_batches',
    'deprecated_add_company_id',
)
branch_labels = None
depends_on = None


def upgrade():
    # This revision only joins existing branches; all schema work is performed
    # by the parent revisions.
    pass


def downgrade():
    # The merge has no schema operations to reverse.
    pass
