from flask import Blueprint, render_template, request, jsonify, flash
from flask_login import login_required
from app.models import db, Supplier, Purchase
from app.utils.permissions import require_permission
from app.utils.security import get_company_id
from sqlalchemy import desc, or_
from app import csrf

suppliers_bp = Blueprint('suppliers', __name__, template_folder='../../templates')

@suppliers_bp.route('/suppliers')
@login_required
@require_permission('can_access_suppliers')
def suppliers():
    """Main suppliers page."""
    return render_template('suppliers/suppliers.html')

@suppliers_bp.route('/api/suppliers', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_suppliers')
def get_suppliers():
    """API endpoint to get suppliers with pagination and filtering."""
    company_id = get_company_id()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search = request.args.get('search', '').strip()

    query = Supplier.query.filter(
        Supplier.company_id == company_id
    )

    if search:
        query = query.filter(
            db.or_(
                Supplier.name.ilike(f'%{search}%'),
                Supplier.phone.ilike(f'%{search}%'),
                Supplier.email.ilike(f'%{search}%'),
                Supplier.contact_person.ilike(f'%{search}%')
            )
        )

    suppliers_list = query.order_by(Supplier.name).paginate(page=page, per_page=per_page)

    result = {
        'suppliers': [],
        'total': suppliers_list.total,
        'pages': suppliers_list.pages,
        'current_page': suppliers_list.page
    }

    for supplier in suppliers_list.items:
        purchase_count = Purchase.query.filter_by(supplier_id=supplier.id).count()
        
        result['suppliers'].append({
            'id': supplier.id,
            'name': supplier.name or '',
            'contact_person': supplier.contact_person or '',
            'phone': supplier.phone or '',
            'email': supplier.email or '',
            'address': supplier.address or '',
            'purchase_count': int(purchase_count)
        })

    return jsonify(result)

@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_suppliers')
def get_supplier(supplier_id):
    """Get single supplier details."""
    company_id = get_company_id()
    supplier = Supplier.query.filter(
        Supplier.id == supplier_id,
        Supplier.company_id == company_id
    ).first()
    
    if not supplier:
        return jsonify({'error': 'Supplier not found'}), 404
    
    purchases = Purchase.query.filter(
        Purchase.supplier_id == supplier.id,
        Purchase.company_id == company_id
    ).order_by(desc(Purchase.date)).limit(10).all()

    return jsonify({
        'id': supplier.id,
        'name': supplier.name,
        'contact_person': supplier.contact_person,
        'phone': supplier.phone,
        'email': supplier.email,
        'address': supplier.address,
        'purchases': [{
            'id': p.id,
            'date': p.date.strftime('%Y-%m-%d') if p.date else None,
            'invoice_number': p.invoice_number,
            'total_amount': p.total_amount,
            'status': p.status
        } for p in purchases]
    })

@suppliers_bp.route('/api/suppliers', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_suppliers')
def create_supplier():
    """Create a new supplier."""
    company_id = get_company_id()
    data = request.get_json()

    if not data or 'name' not in data:
        return jsonify({'error': 'Supplier name is required'}), 400

    existing = Supplier.query.filter(
        Supplier.name == data['name'],
        Supplier.company_id == company_id
    ).first()
    if existing:
        return jsonify({'error': 'Supplier with this name already exists'}), 400

    try:
        supplier = Supplier(
            name=data['name'],
            contact_person=data.get('contact_person'),
            phone=data.get('phone'),
            email=data.get('email'),
            address=data.get('address'),
            company_id=company_id
        )

        db.session.add(supplier)
        db.session.commit()

        return jsonify({
            'success': True,
            'supplier_id': supplier.id,
            'message': 'Supplier created successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@csrf.exempt
@login_required
@require_permission('can_access_suppliers')
def update_supplier(supplier_id):
    """Update a supplier."""
    supplier = Supplier.query.get_or_404(supplier_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        if 'name' in data and data['name'] != supplier.name:
            existing = Supplier.query.filter_by(name=data['name']).first()
            if existing:
                return jsonify({'error': 'Supplier with this name already exists'}), 400
            supplier.name = data['name']

        if 'contact_person' in data:
            supplier.contact_person = data['contact_person']
        if 'phone' in data:
            supplier.phone = data['phone']
        if 'email' in data:
            supplier.email = data['email']
        if 'address' in data:
            supplier.address = data['address']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Supplier updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@suppliers_bp.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_permission('can_access_suppliers')
def delete_supplier(supplier_id):
    """Delete a supplier."""
    supplier = Supplier.query.get_or_404(supplier_id)

    purchase_count = Purchase.query.filter_by(supplier_id=supplier_id).count()
    if purchase_count > 0:
        return jsonify({'error': 'Cannot delete supplier with existing purchases'}), 400

    try:
        db.session.delete(supplier)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Supplier deleted successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
