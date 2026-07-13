from flask import Blueprint, request, jsonify
from flask_login import login_required
from app.models import db, Warehouse
from app.utils.permissions import require_permission
from app.utils.security import get_company_id
from sqlalchemy import or_
from flask_wtf.csrf import CSRFProtect
from app import csrf

warehouse_api_bp = Blueprint('warehouse_api', __name__)

# Apply CSRF exemption to all warehouse API routes
@csrf.exempt
@warehouse_api_bp.route('/api/warehouses', methods=['GET'])
@login_required
@require_permission('can_access_warehouse')
def get_warehouses():
    company_id = get_company_id()
    warehouses = Warehouse.query.filter(
        Warehouse.company_id == company_id
    ).all()
    return jsonify([
        {
            'id': w.id,
            'name': w.name,
            'location': w.location,
            'description': w.description,
            'created_at': w.created_at.strftime('%Y-%m-%d %H:%M:%S') if w.created_at else None
        } for w in warehouses
    ])

@csrf.exempt
@warehouse_api_bp.route('/api/warehouses', methods=['POST'])
@login_required
@require_permission('can_access_warehouse')
def create_warehouse():
    company_id = get_company_id()
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Warehouse name is required'}), 400
    if Warehouse.query.filter(
        Warehouse.name == data['name'],
        Warehouse.company_id == company_id
    ).first():
        return jsonify({'error': 'Warehouse with this name already exists'}), 400
    warehouse = Warehouse(
        name=data['name'],
        location=data.get('location'),
        description=data.get('description'),
        company_id=company_id
    )
    db.session.add(warehouse)
    db.session.commit()
    return jsonify({'success': True, 'warehouse_id': warehouse.id, 'message': 'Warehouse created successfully'})

@csrf.exempt
@warehouse_api_bp.route('/api/warehouses/<int:warehouse_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_warehouse')
def delete_warehouse(warehouse_id):
    company_id = get_company_id()
    warehouse = Warehouse.query.filter(
        Warehouse.id == warehouse_id,
        Warehouse.company_id == company_id
    ).first()
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404
    db.session.delete(warehouse)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Warehouse deleted successfully'})

@csrf.exempt
@warehouse_api_bp.route('/api/warehouses/<int:warehouse_id>', methods=['PUT'])
@login_required
@require_permission('can_access_warehouse')
def update_warehouse(warehouse_id):
    company_id = get_company_id()
    warehouse = Warehouse.query.filter(
        Warehouse.id == warehouse_id,
        Warehouse.company_id == company_id
    ).first()
    if not warehouse:
        return jsonify({'error': 'Warehouse not found'}), 404
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    if 'name' in data:
        if Warehouse.query.filter(
            Warehouse.name == data['name'],
            Warehouse.id != warehouse_id,
            Warehouse.company_id == company_id
        ).first():
            return jsonify({'error': 'Warehouse with this name already exists'}), 400
        warehouse.name = data['name']
    if 'location' in data:
        warehouse.location = data['location']
    if 'description' in data:
        warehouse.description = data['description']
    db.session.commit()
    return jsonify({'success': True, 'message': 'Warehouse updated successfully'})
