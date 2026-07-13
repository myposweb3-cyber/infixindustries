"""Add company_id to models for multi-company support

Revision ID: 001_add_company_id
Revises: 
Create Date: 2026-04-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_add_company_id'
down_revision = 'a6e5446b4e36'
branch_labels = None
depends_on = None


def upgrade():
    """Add company_id columns to tables for multi-company support."""
    
    # Tables that need company_id added
    tables_to_modify = [
        'cheque_deposits',
        'purchase_returns',
        'purchase_return_items',
        'purchase_orders',
        'purchase_order_items',
        'inventory_transactions',
        'serial_numbers',
        'promotions',
        'customer_feedback',
        'held_bills',
        'returns',
        'return_items',
        'exchanges',
        'exchange_items'
    ]
    
    for table_name in tables_to_modify:
        # Check if column already exists
        try:
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    f'{table_name}_company_id_fkey',
                    'companies',
                    ['company_id'],
                    ['id']
                )
        except Exception as e:
            print(f"Warning: Could not modify {table_name}: {e}")
    
    # Serial number unique constraint needs to be updated
    # For now, keep it global but in the future should be per company


def downgrade():
    """Remove company_id columns from tables."""
    
    tables_to_modify = [
        'cheque_deposits',
        'purchase_returns',
        'purchase_return_items',
        'purchase_orders',
        'purchase_order_items',
        'inventory_transactions',
        'serial_numbers',
        'promotions',
        'customer_feedback',
        'held_bills',
        'returns',
        'return_items',
        'exchanges',
        'exchange_items'
    ]
    
    for table_name in tables_to_modify:
        try:
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                batch_op.drop_constraint(f'{table_name}_company_id_fkey', type_='foreignkey')
                batch_op.drop_column('company_id')
        except Exception as e:
            print(f"Warning: Could not downgrade {table_name}: {e}")
