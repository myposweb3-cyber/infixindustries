"""Inventory batch creation and allocation helpers."""

from datetime import datetime
from sqlalchemy import case

from app.models import db, InventoryBatch, InventoryBatchAllocation, Setting


def get_batch_policy(company_id):
    """Return FIFO or FEFO policy for a company; FIFO is the safe default."""
    setting = Setting.query.filter_by(
        company_id=company_id,
        setting_category='inventory',
        setting_key='batch_allocation_policy'
    ).first()
    value = (setting.setting_value if setting else '') or 'FIFO'
    return value.strip().upper() if value.strip().upper() in {'FIFO', 'FEFO'} else 'FIFO'


def create_purchase_batch(purchase, purchase_item, company_id, batch_code=None, expiry_date=None):
    """Create one supplier-specific batch for a received purchase item."""
    quantity = max(0.0, float(purchase_item.quantity or 0))
    batch = InventoryBatch(
        product_id=purchase_item.product_id,
        supplier_id=purchase.supplier_id,
        purchase_id=purchase.id,
        purchase_item_id=purchase_item.id,
        batch_code=batch_code or f'PUR-{purchase.id}-ITEM-{purchase_item.id}',
        received_at=purchase.date or datetime.utcnow(),
        expiry_date=expiry_date,
        unit_cost=float(purchase_item.cost_price or 0),
        quantity_received=quantity,
        quantity_remaining=quantity,
        status='active' if quantity > 0 else 'depleted',
        company_id=company_id,
    )
    db.session.add(batch)
    return batch


def _ordered_batches(product_id, company_id, policy):
    query = InventoryBatch.query.filter(
        InventoryBatch.product_id == product_id,
        InventoryBatch.company_id == company_id,
        InventoryBatch.quantity_remaining > 0,
        InventoryBatch.status == 'active',
    )
    if policy == 'FEFO':
        # Non-expiring stock is allocated after dated stock.
        return query.order_by(
            case((InventoryBatch.expiry_date.is_(None), 1), else_=0),
            InventoryBatch.expiry_date.asc(),
            InventoryBatch.received_at.asc(),
            InventoryBatch.id.asc(),
        ).with_for_update().all()
    return query.order_by(
        InventoryBatch.received_at.asc(), InventoryBatch.id.asc()
    ).with_for_update().all()


def allocate_batches(product_id, quantity, company_id, sale_id=None, sale_item_id=None, allocation_type='sale', policy=None):
    """Consume quantity from batches and return allocation rows.

    Empty results mean the product is a legacy/untracked item. Callers should
    retain the existing product-stock movement for those items.
    """
    remaining = max(0.0, float(quantity or 0))
    if remaining <= 0:
        return []
    policy = policy or get_batch_policy(company_id)
    batches = _ordered_batches(product_id, company_id, policy)
    # Legacy products may have stock that predates batch tracking. Allocate all
    # available tracked stock and leave any remainder untracked rather than
    # blocking a valid sale whose product-level stock is sufficient.
    available = sum(float(batch.quantity_remaining or 0) for batch in batches)
    remaining = min(remaining, available)

    allocations = []
    for batch in batches:
        if remaining <= 1e-9:
            break
        allocated = min(float(batch.quantity_remaining or 0), remaining)
        batch.quantity_remaining -= allocated
        if batch.quantity_remaining <= 1e-9:
            batch.quantity_remaining = 0.0
            batch.status = 'depleted'
        allocation = InventoryBatchAllocation(
            batch_id=batch.id,
            product_id=product_id,
            sale_id=sale_id,
            sale_item_id=sale_item_id,
            quantity=allocated,
            unit_cost=float(batch.unit_cost or 0),
            allocation_type=allocation_type,
            company_id=company_id,
        )
        db.session.add(allocation)
        allocations.append(allocation)
        remaining -= allocated
    return allocations


def restore_batches(product_id, quantity, company_id, return_id=None):
    """Restore returned quantity to the most recently consumed matching batches."""
    remaining = max(0.0, float(quantity or 0))
    if remaining <= 0:
        return []
    batches = InventoryBatch.query.filter(
        InventoryBatch.product_id == product_id,
        InventoryBatch.company_id == company_id,
    ).order_by(InventoryBatch.received_at.desc(), InventoryBatch.id.desc()).with_for_update().all()
    restored = []
    for batch in batches:
        if remaining <= 1e-9:
            break
        capacity = max(0.0, float(batch.quantity_received or 0) - float(batch.quantity_remaining or 0))
        amount = min(capacity, remaining)
        if amount <= 0:
            continue
        batch.quantity_remaining += amount
        batch.status = 'active'
        allocation = InventoryBatchAllocation(
            batch_id=batch.id,
            product_id=product_id,
            return_id=return_id,
            quantity=amount,
            unit_cost=float(batch.unit_cost or 0),
            allocation_type='return',
            company_id=company_id,
        )
        db.session.add(allocation)
        restored.append(allocation)
        remaining -= amount
    return restored
