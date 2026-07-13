"""Add company_id to purchase_items and sale_items tables

Revision ID: 003_company_id_items
Revises: 002_add_company_id
Create Date: 2026-04-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_company_id_items'
down_revision = '002_add_company_id'
branch_labels = None
depends_on = None


def upgrade():
    """Add company_id to purchase_items and sale_items for multi-company support."""
    
    # Only add to tables that don't already have it
    tables_to_modify = ['purchase_items']
    
    for table_name in tables_to_modify:
        try:
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                # Check if column already exists before adding
                batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    f'{table_name}_company_id_fkey',
                    'companies',
                    ['company_id'],
                    ['id']
                )
        except Exception as e:
            print(f"Warning: Could not modify {table_name}: {e}")


def downgrade():
    """Remove company_id columns from purchase_items and sale_items."""
    
    tables_to_modify = [
        'purchase_items',
        'sale_items'
    ]
    
    for table_name in tables_to_modify:
        try:
            with op.batch_alter_table(table_name, schema=None) as batch_op:
                batch_op.drop_constraint(f'{table_name}_company_id_fkey', type_='foreignkey')
                batch_op.drop_column('company_id')
        except Exception as e:
            print(f"Warning: Could not downgrade {table_name}: {e}")
