from datetime import datetime
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required
from app.models import db, Product, InventoryTransaction, StockCount, StockCountItem
from app.utils.permissions import require_permission
from app.utils.security import get_company_id

stock_counts_bp = Blueprint('stock_counts', __name__)

def company_query(query, model):
    company_id = get_company_id()
    return query.filter(model.company_id == company_id) if company_id and hasattr(model, 'company_id') else query

def serialize_count(count):
    return {'id': count.id, 'status': count.status, 'created_at': count.created_at.isoformat(), 'completed_at': count.completed_at.isoformat() if count.completed_at else None, 'notes': count.notes or '', 'items': [{'id': item.id, 'product_id': item.product_id, 'product_name': item.product.name, 'system_quantity': item.system_quantity, 'counted_quantity': item.counted_quantity, 'variance': item.variance, 'reason': item.reason or ''} for item in count.items]}

@stock_counts_bp.route('/inventory/stock-count')
@login_required
@require_permission('can_view_inventory')
def stock_count_page():
    return render_template('inventory/stock_count.html')

@stock_counts_bp.route('/api/inventory/stock-counts', methods=['GET'])
@login_required
@require_permission('can_view_inventory')
def list_counts():
    counts = company_query(StockCount.query, StockCount).order_by(StockCount.created_at.desc()).limit(50).all()
    return jsonify({'counts': [serialize_count(count) for count in counts]})

@stock_counts_bp.route('/api/inventory/stock-counts', methods=['POST'])
@login_required
@require_permission('can_edit_inventory')
def create_count():
    data = request.get_json(silent=True) or {}
    company_id = get_company_id()
    products_query = company_query(Product.query, Product)
    if data.get('warehouse_id'):
        products_query = products_query.filter(Product.warehouse_id == int(data['warehouse_id']))
    products = products_query.order_by(Product.name.asc()).all()
    count = StockCount(company_id=company_id, warehouse_id=data.get('warehouse_id'), created_by_id=current_user.id, notes=(data.get('notes') or '').strip())
    db.session.add(count)
    db.session.flush()
    for product in products:
        db.session.add(StockCountItem(stock_count_id=count.id, product_id=product.id, system_quantity=float(product.stock or 0), counted_quantity=float(product.stock or 0), variance=0.0))
    db.session.commit()
    return jsonify({'success': True, 'count': serialize_count(count)}), 201

@stock_counts_bp.route('/api/inventory/stock-counts/<int:count_id>', methods=['PUT'])
@login_required
@require_permission('can_edit_inventory')
def update_count(count_id):
    count = company_query(StockCount.query, StockCount).filter_by(id=count_id, status='open').first()
    if not count:
        return jsonify({'error': 'Open stock count not found'}), 404
    data = request.get_json(silent=True) or {}
    for entry in data.get('items', []):
        item = next((line for line in count.items if line.id == int(entry.get('id', 0))), None)
        if not item:
            continue
        try:
            counted = float(entry.get('counted_quantity'))
            if counted < 0: raise ValueError
        except (TypeError, ValueError):
            return jsonify({'error': f'Invalid counted quantity for {item.product.name}'}), 400
        item.counted_quantity = counted
        item.variance = counted - item.system_quantity
        item.reason = (entry.get('reason') or '').strip()
    db.session.commit()
    return jsonify({'success': True, 'count': serialize_count(count)})

@stock_counts_bp.route('/api/inventory/stock-counts/<int:count_id>/complete', methods=['POST'])
@login_required
@require_permission('can_edit_inventory')
def complete_count(count_id):
    count = company_query(StockCount.query, StockCount).filter_by(id=count_id, status='open').first()
    if not count:
        return jsonify({'error': 'Open stock count not found'}), 404
    for item in count.items:
        if item.variance and not item.reason:
            return jsonify({'error': f'Reason required for variance in {item.product.name}'}), 400
    for item in count.items:
        if not item.variance:
            continue
        product = item.product
        previous = float(product.stock or 0)
        product.stock = item.counted_quantity
        product.last_updated = datetime.utcnow()
        db.session.add(InventoryTransaction(product_id=product.id, transaction_type='adjustment', quantity=item.variance, previous_stock=previous, new_stock=item.counted_quantity, reference_id=count.id, notes=f'Stock count #{count.id}: {item.reason}', company_id=count.company_id))
    count.status = 'completed'
    count.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'count': serialize_count(count)})

@stock_counts_bp.route('/api/inventory/valuation')
@login_required
@require_permission('can_view_inventory')
def valuation():
    products = company_query(Product.query, Product).all()
    total_cost = sum(float(p.stock or 0) * float(p.cost_price or 0) for p in products)
    total_retail = sum(float(p.stock or 0) * float(p.price or 0) for p in products)
    return jsonify({'product_count': len(products), 'total_units': round(sum(float(p.stock or 0) for p in products), 2), 'cost_value': round(total_cost, 2), 'retail_value': round(total_retail, 2), 'potential_margin': round(total_retail - total_cost, 2)})
