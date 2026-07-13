from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session
from flask_login import login_required, current_user
from sqlalchemy import or_, text
from app.models import (
    db, Company, User, Sale, SaleItem, Return, Exchange, ExchangeItem, ReturnItem,
    Cheque, ChequeDeposit, Customer, Supplier, Product, Expense, Warehouse, Promotion,
    InventoryTransaction, CustomerFeedback, HeldBill, SerialNumber, CustomerPayment,
    AuditLog, Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem,
    PurchaseOrder, PurchaseOrderItem, Setting
)
from app import csrf
from app.utils.permissions import require_permission
from app.utils.company import get_current_company, get_user_companies, set_current_company
from app.utils.security import (
    require_super_admin, 
    require_company_admin,
    require_company_context,
    get_company_id,
    verify_resource_access
)
from datetime import datetime

companies_bp = Blueprint('companies', __name__, template_folder='../../templates')

@companies_bp.route('/companies')
@login_required
def companies():
    """List all companies - SUPER ADMIN ONLY."""
    # SECURITY: Only super admin can manage companies
    if not (current_user.role and current_user.role.lower() == 'super admin'):
        return jsonify({'error': 'Only Super Admin can manage companies'}), 403
    
    all_companies = Company.query.all()
    return render_template('companies/companies.html', companies=all_companies)

@companies_bp.route('/api/companies')
@csrf.exempt
@login_required
def get_companies():
    """Get companies - SUPER ADMIN ONLY for management interface."""
    # SECURITY: Only super admin can manage companies
    if not (current_user.role and current_user.role.lower() == 'super admin'):
        return jsonify({'error': 'Only Super Admin can manage companies'}), 403
    
    all_companies = Company.query.all()
    
    result = []
    for company in all_companies:
        result.append({
            'id': company.id,
            'name': company.name,
            'business_name': company.business_name,
            'address': company.address,
            'phone': company.phone,
            'email': company.email,
            'is_active': company.is_active
        })
    
    return jsonify(result)

@companies_bp.route('/api/companies/<int:company_id>')
@csrf.exempt
@login_required
def get_company(company_id):
    """Get single company details - SUPER ADMIN ONLY."""
    # SECURITY: Only super admin can manage companies
    if not (current_user.role and current_user.role.lower() == 'super admin'):
        return jsonify({'error': 'Only Super Admin can manage companies'}), 403
    
    company = Company.query.get_or_404(company_id)
    
    return jsonify({
        'id': company.id,
        'name': company.name,
        'business_name': company.business_name,
        'address': company.address,
        'phone': company.phone,
        'email': company.email,
        'tax_id': company.tax_id,
        'is_active': company.is_active,
        'default_currency': company.default_currency,
        'timezone': company.timezone
    })

@companies_bp.route('/api/companies', methods=['POST'])
@login_required
@require_super_admin
def create_company():
    """Create a new company. Super Admin only."""
    data = request.get_json()
    
    if not data or 'name' not in data:
        return jsonify({'error': 'Company name is required'}), 400
    
    # Check if company name already exists
    existing = Company.query.filter_by(name=data['name']).first()
    if existing:
        return jsonify({'error': 'Company with this name already exists'}), 400
    
    try:
        company = Company(
            name=data['name'],
            business_name=data.get('business_name'),
            address=data.get('address'),
            phone=data.get('phone'),
            email=data.get('email'),
            tax_id=data.get('tax_id'),
            default_currency=data.get('default_currency', 'LKR'),
            timezone=data.get('timezone', 'Asia/Colombo')
        )
        
        db.session.add(company)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'company_id': company.id,
            'message': 'Company created successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@companies_bp.route('/api/companies/<int:company_id>', methods=['PUT'])
@login_required
@require_super_admin
def update_company(company_id):
    """Update an existing company. Super Admin only."""
    company = Company.query.get_or_404(company_id)
    data = request.get_json()
    
    try:
        if 'name' in data:
            # Check uniqueness
            existing = Company.query.filter(Company.name == data['name'], Company.id != company_id).first()
            if existing:
                return jsonify({'error': 'Company name already exists'}), 400
            company.name = data['name']
        
        company.business_name = data.get('business_name', company.business_name)
        company.address = data.get('address', company.address)
        company.phone = data.get('phone', company.phone)
        company.email = data.get('email', company.email)
        company.tax_id = data.get('tax_id', company.tax_id)
        company.default_currency = data.get('default_currency', company.default_currency)
        company.timezone = data.get('timezone', company.timezone)
        
        if 'is_active' in data:
            company.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Company updated successfully'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@companies_bp.route('/api/companies/<int:company_id>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_super_admin
def delete_company(company_id):
    """Delete a company. Super Admin only. 
    
    Options:
    - Soft delete (default): Deactivates company, keeps all data
    - Hard delete: Permanently removes company and all related data
    
    Hard delete requires admin password verification.
    """
    company = Company.query.get_or_404(company_id)
    
    # Check if hard delete is requested
    data = request.get_json(silent=True) or {}
    hard_delete = data.get('hard_delete', False)
    password = data.get('password', '')
    
    try:
        if hard_delete:
            # Hard delete requires password verification
            if not password:
                return jsonify({
                    'error': 'Password required for hard delete',
                    'requires_verification': True
                }), 400
            
            # Verify admin password
            if not current_user.check_password(password):
                return jsonify({
                    'error': 'Invalid password',
                    'requires_verification': True
                }), 401
            
            # Hard delete - remove company and all related data
            # This is irreversible
            
            # Get company data IDs
            company_id_val = company.id
            sales_ids = [s[0] for s in db.session.query(Sale.id).filter(Sale.company_id == company_id_val).all()]
            saleitem_ids = [s[0] for s in db.session.query(SaleItem.id).filter(SaleItem.company_id == company_id_val).all()]
            
            # Delete in proper FK order (same as reset function)
            if saleitem_ids:
                db.session.query(ReturnItem).filter(
                    ReturnItem.original_sale_item_id.in_(saleitem_ids)
                ).delete(synchronize_session=False)
                db.session.flush()
            
            if sales_ids:
                db.session.query(Return).filter(
                    or_(
                        Return.original_sale_id.in_(sales_ids),
                        Return.company_id == company_id_val
                    )
                ).delete(synchronize_session=False)
                db.session.flush()
            
            if sales_ids:
                db.session.query(Exchange).filter(
                    or_(
                        Exchange.original_sale_id.in_(sales_ids),
                        Exchange.new_sale_id.in_(sales_ids),
                        Exchange.company_id == company_id_val
                    )
                ).delete(synchronize_session=False)
                db.session.flush()
            
            # Delete ALL cheques for this company
            # Cheques can be linked through:
            # 1. Direct company_id
            # 2. sale_id (sale.company_id)
            # 3. purchase_id (purchase.company_id)
            # 4. customer_id (customer.company_id)
            # 5. supplier_id (supplier.company_id)
            
            # Get IDs for all data in this company
            customer_ids = [c[0] for c in db.session.query(Customer.id).filter(Customer.company_id == company_id_val).all()]
            supplier_ids = [s[0] for s in db.session.query(Supplier.id).filter(Supplier.company_id == company_id_val).all()]
            purchase_ids = [p[0] for p in db.session.query(Purchase.id).filter(Purchase.company_id == company_id_val).all()]
            
            # Delete cheques linked through any of these relationships
            cheques_to_delete = db.session.query(Cheque.id).filter(
                or_(
                    Cheque.company_id == company_id_val,
                    Cheque.sale_id.in_(sales_ids) if sales_ids else False,
                    Cheque.purchase_id.in_(purchase_ids) if purchase_ids else False,
                    Cheque.customer_id.in_(customer_ids) if customer_ids else False,
                    Cheque.supplier_id.in_(supplier_ids) if supplier_ids else False,
                )
            ).all()
            
            # Delete cheques one by one to avoid FK constraint issues
            for cheque_id in cheques_to_delete:
                db.session.query(Cheque).filter(Cheque.id == cheque_id[0]).delete(synchronize_session=False)
            
            if cheques_to_delete:
                db.session.flush()
            
            db.session.query(ChequeDeposit).filter(
                ChequeDeposit.company_id == company_id_val
            ).delete(synchronize_session='fetch')
            db.session.flush()
            
            if saleitem_ids:
                db.session.query(ExchangeItem).filter(
                    ExchangeItem.company_id == company_id_val
                ).delete(synchronize_session=False)
                db.session.flush()
            
            if saleitem_ids:
                db.session.query(SaleItem).filter(
                    SaleItem.company_id == company_id_val
                ).delete(synchronize_session=False)
                db.session.flush()
            
            if sales_ids:
                db.session.query(Sale).filter(
                    Sale.company_id == company_id_val
                ).delete(synchronize_session=False)
                db.session.flush()
            
            # Delete other company data
            
            tables_to_delete = [
                (PurchaseReturnItem, 'PurchaseReturnItem'),
                (PurchaseOrderItem, 'PurchaseOrderItem'),
                (PurchaseItem, 'PurchaseItem'),
                (PurchaseReturn, 'PurchaseReturn'),
                (PurchaseOrder, 'PurchaseOrder'),
                (Purchase, 'Purchase'),
                (InventoryTransaction, 'InventoryTransaction'),
                (CustomerFeedback, 'CustomerFeedback'),
                (HeldBill, 'HeldBill'),
                (Expense, 'Expense'),
                (SerialNumber, 'SerialNumber'),
                (CustomerPayment, 'CustomerPayment'),
                (AuditLog, 'AuditLog'),
                (Promotion, 'Promotion'),
                (Product, 'Product'),
                (Customer, 'Customer'),
                (Supplier, 'Supplier'),
                (Warehouse, 'Warehouse'),
                (Setting, 'Setting'),
            ]
            
            for model_class, table_name in tables_to_delete:
                if hasattr(model_class, 'company_id'):
                    db.session.query(model_class).filter(
                        model_class.company_id == company_id_val
                    ).delete(synchronize_session=False)
                    db.session.flush()
            
            # Finally delete the company itself
            db.session.delete(company)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Company "{company.name}" has been permanently deleted with all its data'
            })
        
        else:
            # Soft delete - just deactivate
            company.is_active = False
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Company "{company.name}" has been deactivated'
            })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@companies_bp.route('/api/companies/switch', methods=['POST'])
@csrf.exempt
@login_required
def switch_company():
    """Switch to a different company."""
    data = request.get_json()
    company_id = data.get('company_id')
    
    if not company_id:
        return jsonify({'error': 'Company ID is required'}), 400
    
    # Check if user has access to this company
    user_companies = get_user_companies(current_user.id)
    company_ids = [c.id for c in user_companies]
    
    # Admin and super admin can access any company
    if not (current_user.role and current_user.role.lower() in ['admin', 'super admin']) and company_id not in company_ids:
        return jsonify({'error': 'Access denied to this company'}), 403
    
    # Set the current company in session
    set_current_company(company_id)
    
    company = Company.query.get(company_id)
    
    return jsonify({
        'success': True,
        'message': f'Switched to {company.name}',
        'company': {
            'id': company.id,
            'name': company.name,
            'business_name': company.business_name
        }
    })

@companies_bp.route('/api/companies/<int:company_id>/users')
@login_required
def get_company_users(company_id):
    """Get users associated with a company - SUPER ADMIN ONLY."""
    # SECURITY: Only super admin can manage company users
    if not (current_user.role and current_user.role.lower() == 'super admin'):
        return jsonify({'error': 'Only Super Admin can manage company users'}), 403
    
    try:
        company = Company.query.get_or_404(company_id)
        
        # Get users from association table
        result = []
        if company.users:
            for user in company.users:
                result.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': user.role,
                    'is_admin': True  # Users in the company are admins by association
                })
        
        return jsonify(result)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@companies_bp.route('/api/companies/<int:company_id>/users', methods=['POST'])
@login_required
def add_user_to_company(company_id):
    """Add a user to a company - SUPER ADMIN ONLY."""
    # SECURITY: Only super admin can manage company users
    if not (current_user.role and current_user.role.lower() == 'super admin'):
        return jsonify({'error': 'Only Super Admin can manage company users'}), 403
    
    try:
        company = Company.query.get_or_404(company_id)
        data = request.get_json()
        
        user_id = data.get('user_id')
        is_admin = data.get('is_admin', False)
        
        if not user_id:
            return jsonify({'error': 'User ID is required'}), 400
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # ✅ Super Admin can assign ANY user (including admins) to MULTIPLE companies
        # Users can switch between assigned companies
        if user not in company.users:
            company.users.append(user)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {user.username} added to {company.name}'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@companies_bp.route('/api/companies/<int:company_id>/users/<int:user_id>', methods=['DELETE'])
@login_required
def remove_user_from_company(company_id, user_id):
    """Remove a user from a company - SUPER ADMIN ONLY."""
    # SECURITY: Only super admin can manage company users
    if not (current_user.role and current_user.role.lower() == 'super admin'):
        return jsonify({'error': 'Only Super Admin can manage company users'}), 403
    
    try:
        company = Company.query.get_or_404(company_id)
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if user in company.users:
            company.users.remove(user)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {user.username} removed from {company.name}'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@companies_bp.route('/api/company/current')
@login_required
def get_current_company_info():
    """Get current company info from session."""
    company = get_current_company()
    
    if not company:
        # Get first company user has access to
        user_companies = get_user_companies(current_user.id)
        if user_companies:
            company = user_companies[0]
            set_current_company(company.id)
        else:
            return jsonify({
                'company': None,
                'message': 'No company selected'
            })
    
    return jsonify({
        'company': {
            'id': company.id,
            'name': company.name,
            'business_name': company.business_name,
            'address': company.address,
            'phone': company.phone,
            'email': company.email,
            'default_currency': company.default_currency
        }
    })

