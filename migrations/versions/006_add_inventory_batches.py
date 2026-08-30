"""Add supplier-specific inventory batches and allocation records.

Revision ID: 006_add_inventory_batches
Revises: 005_add_company_id_purchaseitem_settings
"""
from alembic import op
import sqlalchemy as sa

revision = '006_add_inventory_batches'
down_revision = '005_add_company_id_purchaseitem_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'inventory_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('purchase_id', sa.Integer(), sa.ForeignKey('purchases.id'), nullable=True),
        sa.Column('purchase_item_id', sa.Integer(), sa.ForeignKey('purchase_items.id'), nullable=True),
        sa.Column('batch_code', sa.String(length=100), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=False),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('unit_cost', sa.Float(), nullable=False, server_default='0'),
        sa.Column('quantity_received', sa.Float(), nullable=False, server_default='0'),
        sa.Column('quantity_remaining', sa.Float(), nullable=False, server_default='0'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=True),
    )
    op.create_index('ix_inventory_batches_product_id', 'inventory_batches', ['product_id'])
    op.create_index('ix_inventory_batches_supplier_id', 'inventory_batches', ['supplier_id'])
    op.create_index('ix_inventory_batches_purchase_id', 'inventory_batches', ['purchase_id'])
    op.create_index('ix_inventory_batches_purchase_item_id', 'inventory_batches', ['purchase_item_id'])
    op.create_index('ix_inventory_batches_received_at', 'inventory_batches', ['received_at'])
    op.create_index('ix_inventory_batches_expiry_date', 'inventory_batches', ['expiry_date'])
    op.create_index('ix_inventory_batches_company_id', 'inventory_batches', ['company_id'])

    # Preserve existing combined stock as an opening batch. These rows have no
    # supplier because historical stock cannot be reconstructed by supplier.
    op.execute(sa.text("""
        INSERT INTO inventory_batches
            (product_id, supplier_id, batch_code, received_at, unit_cost,
             quantity_received, quantity_remaining, status, company_id)
        SELECT id, supplier_id, 'OPENING-' || id, COALESCE(last_updated, CURRENT_TIMESTAMP),
               COALESCE(cost_price, 0), COALESCE(stock, 0), COALESCE(stock, 0),
               CASE WHEN COALESCE(stock, 0) > 0 THEN 'active' ELSE 'depleted' END,
               company_id
        FROM products
        WHERE COALESCE(stock, 0) > 0
    """))

    op.create_table(
        'inventory_batch_allocations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('inventory_batches.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id'), nullable=True),
        sa.Column('sale_item_id', sa.Integer(), sa.ForeignKey('sale_items.id'), nullable=True),
        sa.Column('return_id', sa.Integer(), sa.ForeignKey('returns.id'), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit_cost', sa.Float(), nullable=False, server_default='0'),
        sa.Column('allocation_type', sa.String(length=20), nullable=False, server_default='sale'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=True),
    )
    op.create_index('ix_inventory_batch_allocations_batch_id', 'inventory_batch_allocations', ['batch_id'])
    op.create_index('ix_inventory_batch_allocations_product_id', 'inventory_batch_allocations', ['product_id'])
    op.create_index('ix_inventory_batch_allocations_sale_id', 'inventory_batch_allocations', ['sale_id'])
    op.create_index('ix_inventory_batch_allocations_return_id', 'inventory_batch_allocations', ['return_id'])
    op.create_index('ix_inventory_batch_allocations_company_id', 'inventory_batch_allocations', ['company_id'])


def downgrade():
    op.drop_table('inventory_batch_allocations')
    op.drop_table('inventory_batches')
