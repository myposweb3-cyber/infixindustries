"""Add company_id to purchase_items and settings tables

Revision ID: 005_add_company_id_purchaseitem_settings
Revises: 003_company_id_items
Create Date: 2026-04-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005_add_company_id_purchaseitem_settings'
down_revision = '003_company_id_items'
branch_labels = None
depends_on = None


def upgrade():
    """Add company_id columns for multi-company support."""
    
    # Add company_id to purchase_items if it doesn't exist
    try:
        with op.batch_alter_table('purchase_items', schema=None) as batch_op:
            batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'purchase_items_company_id_fkey',
                'companies',
                ['company_id'],
                ['id']
            )
    except Exception as e:
        print(f"Info: purchase_items.company_id may already exist: {e}")
    
    # Add company_id to settings table
    try:
        with op.batch_alter_table('settings', schema=None) as batch_op:
            batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'settings_company_id_fkey',
                'companies',
                ['company_id'],
                ['id']
            )
            # Update the unique constraint to include company_id
            batch_op.drop_constraint('unique_setting', type_='unique')
            batch_op.create_unique_constraint(
                'unique_setting_per_company',
                ['setting_category', 'setting_key', 'company_id']
            )
    except Exception as e:
        print(f"Info: settings.company_id may already exist: {e}")


def downgrade():
    """Remove company_id columns."""
    
    try:
        with op.batch_alter_table('purchase_items', schema=None) as batch_op:
            batch_op.drop_constraint('purchase_items_company_id_fkey', type_='foreignkey')
            batch_op.drop_column('company_id')
    except Exception as e:
        print(f"Info: Could not downgrade purchase_items: {e}")
    
    try:
        with op.batch_alter_table('settings', schema=None) as batch_op:
            batch_op.drop_constraint('settings_company_id_fkey', type_='foreignkey')
            batch_op.drop_constraint('unique_setting_per_company', type_='unique')
            batch_op.drop_column('company_id')
            batch_op.create_unique_constraint(
                'unique_setting',
                ['setting_category', 'setting_key']
            )
    except Exception as e:
        print(f"Info: Could not downgrade settings: {e}")
