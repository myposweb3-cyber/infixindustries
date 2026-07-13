from flask import Blueprint, render_template, request, jsonify, flash, current_app
from flask_login import login_required, current_user
from app.models import db, Customer, Sale, SaleItem, Product, Setting, Return, CustomerPayment, Cheque
from app.utils.permissions import require_permission
from app.utils.security import get_company_id, require_company_context
from app.utils.audit import log_create, log_update, log_delete, log_audit
from datetime import datetime, timedelta
from sqlalchemy import func, desc, or_

customers_bp = Blueprint('customers', __name__, template_folder='../../templates')

def get_customer_secure(customer_id):
    """Get a customer with company_id verification (security check)."""
    company_id = get_company_id()
    customer_query = Customer.query.filter_by(id=customer_id)
    if company_id and hasattr(Customer, 'company_id'):
        customer_query = customer_query.filter(Customer.company_id == company_id)
    return customer_query.first()

@customers_bp.route('/customers')
@login_required
@require_company_context
@require_permission('can_access_customers')
def customers():
    """Main customers page."""
    return render_template('customers/customers.html')

@customers_bp.route('/api/customers')
@login_required
@require_company_context
def get_customers():
    """API endpoint to get customers with pagination and filtering."""
    company_id = get_company_id()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort_by', 'name').strip()
    show_inactive_param = request.args.get('show_inactive', 'false')
    
    # Parse the show_inactive parameter correctly
    # jQuery sends: true (as string 'true') or false (as string 'false')
    show_inactive = (show_inactive_param.lower() == 'true')

    query = Customer.query.filter(
        Customer.company_id == company_id
    )

    # Apply status filter
    if hasattr(Customer, 'is_active'):
        if not show_inactive:
            # Default: show only ACTIVE customers
            query = query.filter(Customer.is_active == True)
        # else: show ALL customers (no filter)
    
    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.phone.ilike(f'%{search}%'),
                Customer.email.ilike(f'%{search}%')
            )
        )

    # Apply sorting
    if sort_by == 'total_purchases':
        query = query.order_by(desc(Customer.total_purchases))
    elif sort_by == 'last_purchase_date':
        query = query.order_by(desc(Customer.last_purchase_date))
    elif sort_by == 'loyalty_points':
        query = query.order_by(desc(Customer.loyalty_points))
    else:  # Default to name
        query = query.order_by(Customer.name)

    # Paginate results
    customers = query.paginate(page=page, per_page=per_page)

    result = {
        'customers': [],
        'total': customers.total,
        'pages': customers.pages,
        'current_page': customers.page
    }

    for customer in customers.items:
        customer_data = {
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address,
            'loyalty_points': customer.loyalty_points,
            'total_purchases': customer.total_purchases,
            'last_purchase_date': customer.last_purchase_date.strftime('%Y-%m-%d') if customer.last_purchase_date else None,
            'registration_date': customer.registration_date.strftime('%Y-%m-%d') if customer.registration_date else None,
            'notes': customer.notes,
            'preferred_payment_method': customer.preferred_payment_method,
            'credit_limit': customer.credit_limit,
            'current_balance': customer.current_balance
        }
        
        # Add is_active and archived_at only if they exist on the model
        if hasattr(customer, 'is_active'):
            customer_data['is_active'] = customer.is_active
        else:
            customer_data['is_active'] = True
            
        if hasattr(customer, 'archived_at'):
            customer_data['archived_at'] = customer.archived_at.strftime('%Y-%m-%d %H:%M:%S') if customer.archived_at else None
        else:
            customer_data['archived_at'] = None
            
        result['customers'].append(customer_data)

    return jsonify(result)

@customers_bp.route('/api/customers/<int:customer_id>', methods=['GET'])
@login_required
def get_customer(customer_id):
    """Get single customer details."""
    company_id = get_company_id()
    customer = Customer.query.filter(
        Customer.id == customer_id,
        Customer.company_id == company_id
    ).first()
    
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    return jsonify({
        'id': customer.id,
        'name': customer.name or '',
        'phone': customer.phone or '',
        'email': customer.email or '',
        'address': customer.address or '',
        'loyalty_points': int(customer.loyalty_points) if customer.loyalty_points else 0,
        'total_purchases': int(customer.total_purchases) if customer.total_purchases else 0,
        'last_purchase_date': customer.last_purchase_date.strftime('%Y-%m-%d') if customer.last_purchase_date else None,
        'registration_date': customer.registration_date.strftime('%Y-%m-%d') if customer.registration_date else None,
        'notes': customer.notes or '',
        'preferred_payment_method': customer.preferred_payment_method or '',
        'credit_limit': float(customer.credit_limit) if customer.credit_limit else 0.0,
        'current_balance': float(customer.current_balance) if customer.current_balance else 0.0
    })

@customers_bp.route('/api/customers', methods=['POST'])
@login_required
@require_permission('can_access_customers')
def create_customer():
    """Create a new customer."""
    data = request.get_json()

    if not data or 'name' not in data:
        return jsonify({'error': 'Customer name is required'}), 400

    # Validate name is not empty or whitespace
    name = data['name'].strip()
    if not name:
        return jsonify({'error': 'Customer name cannot be empty'}), 400

    # Check if customer with this name already exists
    company_id = get_company_id()
    existing = Customer.query.filter(
        Customer.name == name,
        Customer.company_id == company_id
    ).first()
    if existing:
        # Check if is_active attribute exists
        if hasattr(existing, 'is_active') and existing.is_active == False:
            # There's an archived customer with same name, offer to restore
            return jsonify({
                'error': 'A customer with this name already exists but is archived. Would you like to restore it?',
                'archived_customer_id': existing.id
            }), 400
        return jsonify({'error': 'Customer with this name already exists'}), 400

    try:
        # Handle credit_limit and current_balance with proper validation
        try:
            credit_limit = float(data.get('credit_limit', 0.0)) if data.get('credit_limit') else 0.0
        except (ValueError, TypeError):
            credit_limit = 0.0
        
        try:
            current_balance = float(data.get('current_balance', 0.0)) if data.get('current_balance') else 0.0
        except (ValueError, TypeError):
            current_balance = 0.0

        customer = Customer(
            name=name,
            phone=data.get('phone'),
            email=data.get('email'),
            address=data.get('address'),
            notes=data.get('notes'),
            preferred_payment_method=data.get('preferred_payment_method'),
            credit_limit=credit_limit,
            current_balance=current_balance
        )
        
        # Set company_id if the column exists
        company_id = get_company_id()
        if company_id and hasattr(Customer, 'company_id'):
            customer.company_id = company_id
        
        # Set is_active if the column exists
        if hasattr(Customer, 'is_active'):
            customer.is_active = True

        db.session.add(customer)
        db.session.commit()

        # Log audit
        log_create('Customer', customer.id, {
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address,
            'credit_limit': customer.credit_limit
        }, description=f"Customer '{customer.name}' created")

        return jsonify({
            'success': True,
            'customer_id': customer.id,
            'message': 'Customer created successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customers_bp.route('/api/customers/<int:customer_id>', methods=['PUT'])
@login_required
@require_permission('can_access_customers')
def update_customer(customer_id):
    """Update an existing customer."""
    company_id = get_company_id()
    customer = Customer.query.filter(
        Customer.id == customer_id,
        Customer.company_id == company_id
    ).first()
    
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
        
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        # Store old values for audit log
        old_values = {
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address,
            'notes': customer.notes,
            'credit_limit': customer.credit_limit,
            'current_balance': customer.current_balance
        }
        
        # Check name uniqueness if name is being changed
        if 'name' in data and data['name'] != customer.name:
            company_id = get_company_id()
            existing = Customer.query.filter(
                Customer.name == data['name'],
                Customer.id != customer_id,
                Customer.company_id == company_id
            ).first()
            if existing:
                return jsonify({'error': 'Customer with this name already exists'}), 400

        # Update customer fields
        for field in ['name', 'phone', 'email', 'address', 'notes',
                     'preferred_payment_method', 'credit_limit', 'current_balance']:
            if field in data:
                if field in ['credit_limit', 'current_balance']:
                    # Handle empty string values properly
                    try:
                        value = data[field]
                        if value == '' or value is None:
                            setattr(customer, field, 0.0)
                        else:
                            setattr(customer, field, float(value))
                    except (ValueError, TypeError):
                        setattr(customer, field, 0.0)
                else:
                    setattr(customer, field, data[field])

        db.session.commit()
        
        # Store new values for audit log
        new_values = {
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address,
            'notes': customer.notes,
            'credit_limit': customer.credit_limit,
            'current_balance': customer.current_balance
        }
        
        # Log audit
        log_update('Customer', customer.id, old_values, new_values, 
                   description=f"Customer '{customer.name}' updated")

        return jsonify({
            'success': True,
            'message': 'Customer updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customers_bp.route('/api/customers/<int:customer_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_customers')
def delete_customer(customer_id):
    """Archive (soft delete) a customer instead of permanent deletion."""
    company_id = get_company_id()
    customer = Customer.query.filter(
        Customer.id == customer_id,
        Customer.company_id == company_id
    ).first()
    
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    try:
        # Store old values for audit log
        old_values = {'name': customer.name, 'is_active': True if hasattr(customer, 'is_active') else None}
        
        # Check if is_active column exists
        if hasattr(customer, 'is_active'):
            # Soft delete - archive the customer
            customer.is_active = False
            customer.archived_at = datetime.utcnow()
        else:
            # Fallback: try to delete related feedback records first, then delete customer
            from app.models import CustomerFeedback
            CustomerFeedback.query.filter_by(customer_id=customer_id).delete()
            db.session.delete(customer)
        
        db.session.commit()
        
        # Log audit
        log_delete('Customer', customer_id, old_values, 
                   description=f"Customer '{customer.name}' archived")

        return jsonify({
            'success': True,
            'message': 'Customer archived successfully. You can restore them later if needed.'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customers_bp.route('/api/customers/<int:customer_id>/restore', methods=['POST'])
@login_required
@require_permission('can_access_customers')
def restore_customer(customer_id):
    """Restore an archived customer."""
    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    try:
        if hasattr(customer, 'is_active'):
            customer.is_active = True
            customer.archived_at = None
        
        db.session.commit()
        
        # Log audit
        log_audit('Customer', customer.id, 'restore', 
                  description=f"Customer '{customer.name}' restored")

        return jsonify({
            'success': True,
            'message': 'Customer restored successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customers_bp.route('/api/customers/<int:customer_id>/archive', methods=['POST'])
@login_required
@require_permission('can_access_customers')
def archive_customer(customer_id):
    """Archive a customer."""
    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    try:
        if hasattr(customer, 'is_active'):
            customer.is_active = False
            customer.archived_at = datetime.utcnow()
        
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Customer archived successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customers_bp.route('/api/customers/<int:customer_id>/purchase-history')
@login_required
def get_customer_purchase_history(customer_id):
    """Get purchase history for a specific customer."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    # Get sales for this customer
    company_id = get_company_id()
    sales = Sale.query.filter(Sale.customer == customer.name, Sale.company_id == company_id)\
                     .order_by(desc(Sale.date))\
                     .paginate(page=page, per_page=per_page)

    result = {
        'customer_name': customer.name,
        'sales': [],
        'total': sales.total,
        'pages': sales.pages,
        'current_page': sales.page
    }

    for sale in sales.items:
        sale_data = {
            'id': sale.id,
            'date': sale.date.strftime('%Y-%m-%d %H:%M:%S'),
            'total': sale.total,
            'payment': sale.payment,
            'items': []
        }

        # Get sale items with product names
        for item in sale.items:
            sale_data['items'].append({
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': item.price,
                'total': item.quantity * item.price
            })

        result['sales'].append(sale_data)

    return jsonify(result)

@customers_bp.route('/api/customers/<int:customer_id>/loyalty', methods=['POST'])
@login_required
@require_permission('can_access_customers')
def update_loyalty_points(customer_id):
    """Update customer loyalty points."""
    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    data = request.get_json()

    if not data or 'points' not in data:
        return jsonify({'error': 'Points value is required'}), 400

    try:
        points_change = int(data['points'])
        customer.loyalty_points += points_change

        # Ensure points don't go negative
        if customer.loyalty_points < 0:
            customer.loyalty_points = 0

        db.session.commit()

        return jsonify({
            'success': True,
            'new_points': customer.loyalty_points,
            'message': f'Loyalty points updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@customers_bp.route('/api/customers/analytics')
@login_required
def get_customer_analytics():
    """Get customer analytics data."""
    company_id = get_company_id()
    
    # Total customers (COMPANY FILTERED)
    total_customers = Customer.query.filter(
        Customer.company_id == company_id
    ).count()

    # Active customers (purchased in last 30 days) (COMPANY FILTERED)
    from datetime import timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    active_customers = Customer.query.filter(
        Customer.company_id == company_id,
        Customer.last_purchase_date >= thirty_days_ago
    ).count()

    # Top customers by total purchases (COMPANY FILTERED)
    top_customers = db.session.query(
        Customer.name,
        Customer.total_purchases,
        Customer.loyalty_points
    ).filter(
        Customer.company_id == company_id
    ).order_by(desc(Customer.total_purchases)).limit(10).all()

    # Average order value (COMPANY FILTERED)
    avg_order_value = db.session.query(func.avg(Sale.total)).filter(
        Sale.company_id == company_id
    ).scalar() or 0

    # Total revenue (COMPANY FILTERED)
    total_revenue = db.session.query(func.sum(Sale.total)).filter(
        Sale.company_id == company_id
    ).scalar() or 0

    return jsonify({
        'total_customers': total_customers,
        'active_customers': active_customers,
        'top_customers': [
            {
                'name': customer[0],
                'total_purchases': customer[1],
                'loyalty_points': customer[2]
            } for customer in top_customers
        ],
        'average_order_value': float(avg_order_value),
        'total_revenue': float(total_revenue)
    })


@customers_bp.route('/api/customers/outstanding-aging')
@login_required
def get_customer_outstanding_aging():
    """Get customer outstanding grouped by aging categories."""
    company_id = get_company_id()
    
    # Get all active customers with their current_balance (COMPANY FILTERED)
    customers = Customer.query.filter(
        Customer.company_id == company_id,
        Customer.is_active == True,
        Customer.current_balance > 0
    ).all()
    
    from datetime import timedelta
    
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    ninety_days_ago = now - timedelta(days=90)
    
    # Initialize totals
    totals = {
        '0_30_days': {'count': 0, 'total': 0.0},
        '30_60_days': {'count': 0, 'total': 0.0},
        '60_90_days': {'count': 0, 'total': 0.0},
        '90_plus_days': {'count': 0, 'total': 0.0}
    }
    
    customer_list = []
    
    company_id = get_company_id()
    for customer in customers:
        # Get credit sales for this customer (sales with balance remaining)
        credit_sales = Sale.query.filter(
            Sale.customer == customer.name,
            Sale.balance > 0,
            Sale.company_id == company_id
        ).all()
        
        outstanding_0_30 = 0.0
        outstanding_30_60 = 0.0
        outstanding_60_90 = 0.0
        outstanding_90_plus = 0.0
        
        for sale in credit_sales:
            days_old = (now - sale.date).days
            
            if days_old <= 30:
                outstanding_0_30 += sale.balance
            elif days_old <= 60:
                outstanding_30_60 += sale.balance
            elif days_old <= 90:
                outstanding_60_90 += sale.balance
            else:
                outstanding_90_plus += sale.balance
        
        # Calculate total outstanding for this customer
        total_outstanding = outstanding_0_30 + outstanding_30_60 + outstanding_60_90 + outstanding_90_plus
        
        if total_outstanding > 0:
            customer_data = {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'total_outstanding': total_outstanding,
                'outstanding_0_30': outstanding_0_30,
                'outstanding_30_60': outstanding_30_60,
                'outstanding_60_90': outstanding_60_90,
                'outstanding_90_plus': outstanding_90_plus,
                'supply_stopped': customer.supply_stopped,
                'credit_limit': customer.credit_limit
            }
            customer_list.append(customer_data)
            
            # Update totals
            if outstanding_0_30 > 0:
                totals['0_30_days']['count'] += 1
                totals['0_30_days']['total'] += outstanding_0_30
            if outstanding_30_60 > 0:
                totals['30_60_days']['count'] += 1
                totals['30_60_days']['total'] += outstanding_30_60
            if outstanding_60_90 > 0:
                totals['60_90_days']['count'] += 1
                totals['60_90_days']['total'] += outstanding_60_90
            if outstanding_90_plus > 0:
                totals['90_plus_days']['count'] += 1
                totals['90_plus_days']['total'] += outstanding_90_plus
    
    # Sort customers by 90+ days outstanding descending
    customer_list.sort(key=lambda x: x['outstanding_90_plus'], reverse=True)
    
    return jsonify({
        'customers': customer_list,
        'totals': totals
    })


@customers_bp.route('/api/customers/<int:customer_id>/stop-supply', methods=['POST'])
@login_required
@require_permission('can_access_customers')
def stop_customer_supply(customer_id):
    """Stop or resume supply for a customer."""
    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    data = request.get_json()
    
    try:
        stop = data.get('stop', True)
        customer.supply_stopped = stop
        db.session.commit()
        
        action = "stopped" if stop else "resumed"
        return jsonify({
            'success': True,
            'message': f'Supply {action} successfully for {customer.name}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@customers_bp.route('/api/customers/recalculate-balance', methods=['POST'])
@login_required
@require_permission('can_access_customers')
def recalculate_customer_balance():
    """Recalculate outstanding balances for all customers based on credit sales."""
    company_id = get_company_id()
    customers = Customer.query.filter(
        Customer.is_active == True,
        Customer.company_id == company_id
    ).all()
    
    from datetime import timedelta
    now = datetime.utcnow()
    
    updated_count = 0
    
    company_id = get_company_id()
    for customer in customers:
        # Get all credit sales for this customer
        credit_sales = Sale.query.filter(
            Sale.customer == customer.name,
            Sale.balance > 0,
            Sale.company_id == company_id
        ).all()
        
        # Calculate total outstanding by age
        outstanding_0_30 = 0.0
        outstanding_30_60 = 0.0
        outstanding_60_90 = 0.0
        outstanding_90_plus = 0.0
        total_balance = 0.0
        
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        ninety_days_ago = now - timedelta(days=90)
        
        for sale in credit_sales:
            days_old = (now - sale.date).days
            
            if sale.date >= thirty_days_ago:
                outstanding_0_30 += sale.balance
            elif sale.date >= sixty_days_ago:
                outstanding_30_60 += sale.balance
            elif sale.date >= ninety_days_ago:
                outstanding_60_90 += sale.balance
            else:
                outstanding_90_plus += sale.balance
            
            total_balance += sale.balance
        
        # Update customer balance
        customer.current_balance = total_balance
        customer.outstanding_0_30 = outstanding_0_30
        customer.outstanding_30_60 = outstanding_30_60
        customer.outstanding_60_90 = outstanding_60_90
        customer.outstanding_90_plus = outstanding_90_plus
        customer.last_balance_update = now
        
        # Auto-stop supply for 90+ days customers if not already stopped
        if outstanding_90_plus > 0 and not customer.supply_stopped:
            customer.supply_stopped = True
        
        updated_count += 1
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Balance recalculated for {updated_count} customers'
    })


@customers_bp.route('/api/customers/credit-settings', methods=['GET', 'POST'])
@login_required
@require_permission('can_access_customers')
def get_set_credit_settings():
    """Get or set global credit settings."""
    from app.models import Setting
    
    if request.method == 'POST':
        data = request.get_json()
        
        # Update or create default credit days
        default_credit_days = data.get('default_credit_days', 30)
        
        setting = Setting.query.filter_by(
            setting_category='credit',
            setting_key='default_credit_days'
        ).first()
        
        if setting:
            setting.setting_value = str(default_credit_days)
        else:
            setting = Setting(
                setting_category='credit',
                setting_key='default_credit_days',
                setting_value=str(default_credit_days)
            )
            db.session.add(setting)
        
        # Also update enable_credit_sales if provided
        if 'enable_credit_sales' in data:
            enable_setting = Setting.query.filter_by(
                setting_category='credit',
                setting_key='enable_credit_sales'
            ).first()
            
            if enable_setting:
                enable_setting.setting_value = str(data.get('enable_credit_sales', 'true')).lower()
            else:
                enable_setting = Setting(
                    setting_category='credit',
                    setting_key='enable_credit_sales',
                    setting_value=str(data.get('enable_credit_sales', 'true')).lower()
                )
                db.session.add(enable_setting)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Credit settings updated successfully'
        })
    
    # GET - return current settings
    default_days = Setting.query.filter_by(
        setting_category='credit',
        setting_key='default_credit_days'
    ).first()
    
    enable_credit = Setting.query.filter_by(
        setting_category='credit',
        setting_key='enable_credit_sales'
    ).first()
    
    return jsonify({
        'default_credit_days': int(default_days.setting_value) if default_days else 30,
        'enable_credit_sales': enable_credit.setting_value.lower() == 'true' if enable_credit else True
    })


@customers_bp.route('/api/customers/<int:customer_id>/ledger')
@login_required
def get_customer_ledger(customer_id):
    """Get customer ledger - all transactions (sales, payments, returns) for a customer."""
    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Default to last 12 months if no dates provided
    if not start_date or not end_date:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Get sales for this customer within date range
    company_id = get_company_id()
    sales = Sale.query.filter(
        Sale.customer == customer.name,
        Sale.date >= start_date,
        Sale.date <= end_date,
        Sale.company_id == company_id
    ).order_by(Sale.date.desc()).all()
    
    # Get returns for this customer
    returns = Return.query.filter(
        Return.customer == customer.name,
        Return.date >= start_date,
        Return.date <= end_date
    ).order_by(Return.date.desc()).all()
    
    # Build ledger entries
    ledger_entries = []
    running_balance = customer.current_balance  # Start with current balance and work backwards
    
    # First, get total historical balance before start date
    historical_sales = Sale.query.filter(
        Sale.customer == customer.name,
        Sale.date < start_date,
        Sale.company_id == company_id
    ).all()
    
    historical_returns = Return.query.filter(
        Return.customer == customer.name,
        Return.date < start_date
    ).all()
    
    opening_balance = sum(s.balance for s in historical_sales)
    opening_balance -= sum(r.refund_amount for r in historical_returns)
    
    # Get credit days for this customer
    default_credit_days = 30
    credit_days_setting = Setting.query.filter_by(
        setting_category='credit',
        setting_key='default_credit_days'
    ).first()
    if credit_days_setting:
        default_credit_days = int(credit_days_setting.setting_value)
    
    customer_credit_days = customer.credit_days if customer.credit_days and customer.credit_days > 0 else default_credit_days
    
    # Process sales
    for sale in sales:
        days_old = (datetime.utcnow() - sale.date).days
        is_overdue = days_old > customer_credit_days and sale.balance > 0
        
        entry = {
            'date': sale.date.strftime('%Y-%m-%d'),
            'time': sale.date.strftime('%H:%M:%S'),
            'type': 'Sale',
            'reference': f'INV-{sale.id:06d}',
            'debit': float(sale.total),
            'credit': 0,
            'balance': float(sale.balance),
            'payment_method': sale.payment,
            'days_old': days_old,
            'is_overdue': is_overdue
        }
        ledger_entries.append(entry)
    
    # Process returns
    for return_obj in returns:
        entry = {
            'date': return_obj.date.strftime('%Y-%m-%d'),
            'time': return_obj.date.strftime('%H:%M:%S'),
            'type': 'Return',
            'reference': f'RET-{return_obj.id:06d}',
            'debit': 0,
            'credit': float(return_obj.refund_amount),
            'balance': 0,  # Returns reduce balance
            'payment_method': return_obj.refund_method,
            'days_old': (datetime.utcnow() - return_obj.date).days,
            'is_overdue': False
        }
        ledger_entries.append(entry)

    # Process payments for this customer within date range
    payments = CustomerPayment.query.filter(
        CustomerPayment.customer_id == customer.id,
        CustomerPayment.date >= start_date,
        CustomerPayment.date <= end_date
    ).order_by(CustomerPayment.date.desc()).all()

    for payment in payments:
        # Try to find a matching Cheque record if payment method is Cheque
        cheque_info = None
        try:
            if payment.payment_method and payment.payment_method.lower() == 'cheque' and payment.reference_number:
                cheque = Cheque.query.filter(
                    Cheque.cheque_number == payment.reference_number,
                    Cheque.customer_id == customer.id,
                    Cheque.amount == payment.amount
                ).first()
                if cheque:
                    cheque_info = {
                        'cheque_bank': cheque.bank_name,
                        'cheque_date': cheque.cheque_date.strftime('%Y-%m-%d') if cheque.cheque_date else None
                    }
        except Exception:
            cheque_info = None

        entry = {
            'date': payment.date.strftime('%Y-%m-%d'),
            'time': payment.date.strftime('%H:%M:%S'),
            'type': 'Payment',
            'reference': payment.reference_number or f'PAY-{payment.id:06d}',
            'debit': 0,
            'credit': float(payment.amount),
            'balance': 0,
            'payment_method': payment.payment_method,
            'notes': payment.notes or '',
            'days_old': (datetime.utcnow() - payment.date).days,
            'is_overdue': False
        }

        if cheque_info:
            entry.update(cheque_info)

        ledger_entries.append(entry)
    
    # Sort by date descending
    ledger_entries.sort(key=lambda x: (x['date'], x['time']), reverse=True)
    
    # Calculate totals
    total_debit = sum(e['debit'] for e in ledger_entries)
    total_credit = sum(e['credit'] for e in ledger_entries)
    
    return jsonify({
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address,
            'credit_limit': customer.credit_limit,
            'credit_days': customer_credit_days,
            'current_balance': customer.current_balance
        },
        'period': {
            'start_date': start_date_str,
            'end_date': end_date_str
        },
        'opening_balance': opening_balance,
        'ledger': ledger_entries,
        'summary': {
            'total_sales': total_debit,
            'total_returns': total_credit,
            'closing_balance': customer.current_balance
        }
    })


@customers_bp.route('/api/customers/<int:customer_id>/record-payment', methods=['POST'])
@login_required
@require_permission('can_manage_customer_payments')
def record_customer_payment(customer_id):
    """Record a payment received from a customer."""
    customer = get_customer_secure(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid payment amount'}), 400

    if amount <= 0:
        return jsonify({'error': 'Invalid payment amount'}), 400

    payment_method = data.get('payment_method', 'Cash')
    notes = data.get('notes', '')
    reference_number = data.get('reference_number', '')
    sale_id = data.get('sale_id')  # Optional: link to specific sale

    # Company context
    company_id = customer.company_id if hasattr(customer, 'company_id') else None

    try:
        # Create payment record
        payment = CustomerPayment(
            customer_id=customer.id,
            sale_id=sale_id,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            user_id=current_user.id if hasattr(current_user, 'id') else None,
            company_id=company_id
        )
        db.session.add(payment)

        # If payment is by cheque, optionally create Cheque record
        if payment_method and payment_method.lower() == 'cheque':
            cheque_number = (data.get('cheque_number') or reference_number or '').strip()
            cheque_bank = (data.get('cheque_bank') or '').strip()
            cheque_date_str = data.get('cheque_date')

            if cheque_number:
                try:
                    cheque_date = datetime.strptime(cheque_date_str, '%Y-%m-%d').date() if cheque_date_str else datetime.utcnow().date()
                except Exception:
                    cheque_date = datetime.utcnow().date()

                # Avoid inserting duplicate cheques (unique constraint on cheque_number + bank_name)
                existing_cheque = Cheque.query.filter(
                    Cheque.cheque_number == cheque_number,
                    Cheque.bank_name == (cheque_bank if cheque_bank else 'Unknown')
                ).first()

                if existing_cheque:
                    try:
                        current_app.logger.info(f"Found existing Cheque (id={existing_cheque.id}) for number={cheque_number}, bank={cheque_bank}")
                    except Exception:
                        pass

                    # Ensure the existing cheque is linked to this customer/sale so it appears in received cheques
                    updated = False
                    if not existing_cheque.customer_id:
                        existing_cheque.customer_id = customer.id
                        updated = True
                    if sale_id and not existing_cheque.sale_id:
                        existing_cheque.sale_id = sale_id
                        updated = True
                    if not existing_cheque.payer_name:
                        existing_cheque.payer_name = customer.name
                        updated = True
                    if existing_cheque.notes != notes and notes:
                        existing_cheque.notes = (existing_cheque.notes or '') + '\n' + notes
                        updated = True
                    if existing_cheque.status != 'pending':
                        existing_cheque.status = 'pending'
                        updated = True

                    if updated:
                        try:
                            db.session.add(existing_cheque)
                        except Exception:
                            pass
                else:
                    cheque = Cheque(
                        cheque_number=cheque_number,
                        bank_name=cheque_bank if cheque_bank else 'Unknown',
                        branch=None,
                        cheque_date=cheque_date,
                        amount=amount,
                        payer_name=customer.name,
                        customer_id=customer.id,
                        notes=notes,
                        created_by=current_user.id if hasattr(current_user, 'id') else None,
                        company_id=company_id,
                        sale_id=sale_id
                    )
                    db.session.add(cheque)

        # Apply payment to unpaid sales (oldest first)
        unpaid_sales = Sale.query.filter(
            Sale.customer == customer.name,
            Sale.balance > 0,
            Sale.company_id == get_company_id()
        ).order_by(Sale.date.asc()).all()

        remaining_payment = amount
        for sale in unpaid_sales:
            if remaining_payment <= 0:
                break
            apply_amt = min(remaining_payment, sale.balance)
            sale.balance = max(0, sale.balance - apply_amt)
            remaining_payment -= apply_amt

        # Persist changes
        db.session.commit()

        # Recalculate customer's current balance and aging
        company_id = get_company_id()
        total_balance = sum(s.balance for s in Sale.query.filter(Sale.customer == customer.name, Sale.company_id == company_id).all())
        customer.current_balance = total_balance

        from datetime import timedelta
        now = datetime.utcnow()
        outstanding_0_30 = outstanding_30_60 = outstanding_60_90 = outstanding_90_plus = 0.0
        for s in Sale.query.filter(Sale.customer == customer.name, Sale.balance > 0, Sale.company_id == company_id).all():
            days_old = (now - s.date).days
            if days_old <= 30:
                outstanding_0_30 += s.balance
            elif days_old <= 60:
                outstanding_30_60 += s.balance
            elif days_old <= 90:
                outstanding_60_90 += s.balance
            else:
                outstanding_90_plus += s.balance

        customer.outstanding_0_30 = outstanding_0_30
        customer.outstanding_30_60 = outstanding_30_60
        customer.outstanding_60_90 = outstanding_60_90
        customer.outstanding_90_plus = outstanding_90_plus
        customer.last_balance_update = now

        # Resume supply if balance low
        if hasattr(customer, 'credit_limit') and customer.current_balance < (customer.credit_limit or 0) * 0.5:
            customer.supply_stopped = False

        db.session.commit()

        # Log audit
        try:
            log_audit('Payment', payment.id, 'create',
                      new_values={'amount': amount, 'payment_method': payment_method, 'customer_id': customer_id, 'reference': reference_number},
                      description=f"Payment of ₨{amount} recorded from customer '{customer.name}'")
        except Exception:
            pass

        return jsonify({
            'success': True,
            'message': f'Payment of {amount} recorded successfully',
            'new_balance': customer.current_balance,
            'payment_id': payment.id
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        tb = traceback.format_exc()
        try:
            current_app.logger.error('Error in record_customer_payment: %s', tb)
        except Exception:
            pass
        return jsonify({'error': 'Server error', 'exception': str(e), 'trace': tb}), 500
