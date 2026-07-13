from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from app.models import db, Cheque, ChequeDeposit, Customer, Supplier, Sale, Purchase
from app.utils.permissions import require_permission
from app.utils.security import get_company_id, require_company_context
from datetime import datetime, timedelta
from sqlalchemy import desc, func, and_, or_
import os
from werkzeug.utils import secure_filename

cheques_bp = Blueprint('cheques', __name__, template_folder='../../templates')

# Upload configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'gif', 'bmp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

def apply_company_filter(query, model_class=Cheque):
    """Apply company filter to a query if company is set in session."""
    company_id = get_company_id()
    if company_id and hasattr(model_class, 'company_id'):
        query = query.filter(
            model_class.company_id == company_id
        )
    return query

def get_cheque_secure(cheque_id):
    """Get a cheque with company_id verification (security check)."""
    cheque_query = Cheque.query.filter_by(id=cheque_id)
    cheque_query = apply_company_filter(cheque_query, Cheque)
    return cheque_query.first()

def get_deposit_secure(deposit_id):
    """Get a cheque deposit with company_id verification (security check)."""
    deposit_query = ChequeDeposit.query.filter_by(id=deposit_id)
    deposit_query = apply_company_filter(deposit_query, ChequeDeposit)
    return deposit_query.first()

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_upload_folder():
    """Get upload folder for cheque images."""
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads', 'cheques')
    os.makedirs(folder, exist_ok=True)
    return folder

# ============================================================================
# IMAGE SERVING ROUTE
# ============================================================================

@cheques_bp.route('/image/<filename>')
@login_required
@require_permission('can_access_cheques')
def serve_cheque_image(filename):
    """Serve uploaded cheque images."""
    try:
        upload_folder = get_upload_folder()
        # Validate filename to prevent directory traversal
        filename = secure_filename(filename)
        if not filename or '..' in filename:
            return jsonify({'error': 'Invalid filename'}), 400
        
        file_path = os.path.join(upload_folder, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'Image not found'}), 404
        
        return send_file(file_path, mimetype='image/jpeg')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# MAIN CHEQUE MANAGEMENT PAGE
# ============================================================================

@cheques_bp.route('')
@login_required
@require_company_context
@require_permission('can_access_cheques')
def cheques():
    """Main cheques page with filters and tabs."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    cheque_type_filter = request.args.get('cheque_type')  # 'payment' or 'received'
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    bank_filter = request.args.get('bank')
    customer_filter = request.args.get('customer')
    
    # Build query
    query = Cheque.query
    
    # Apply company filter
    query = apply_company_filter(query)
    
    # Filter by cheque type (payment made or payment received)
    if cheque_type_filter == 'payment':
        # Payments to suppliers (has supplier_id) or payments (via purchase)
        query = query.filter(
            or_(
                Cheque.supplier_id.isnot(None),
                Cheque.purchase_id.isnot(None)
            )
        )
    elif cheque_type_filter == 'received':
        # Payments from customers (has customer_id) or from sales
        query = query.filter(
            or_(
                Cheque.customer_id.isnot(None),
                Cheque.sale_id.isnot(None)
            )
        )
    
    if status_filter:
        query = query.filter(Cheque.status == status_filter)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Cheque.cheque_date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Cheque.cheque_date <= end)
        except ValueError:
            pass
    
    if bank_filter:
        query = query.filter(Cheque.bank_name.ilike(f'%{bank_filter}%'))
    
    if customer_filter:
        query = query.filter(Cheque.customer_id == int(customer_filter) if customer_filter.isdigit() else True)
    
    # Get all cheques ordered by date descending
    cheques_list = query.order_by(desc(Cheque.cheque_date)).all()
    
    # Get unique banks for filter
    banks = db.session.query(Cheque.bank_name).distinct().all()
    banks = [b[0] for b in banks if b[0]]
    
    # Get customers for dropdown
    customers = Customer.query.all()
    
    # Calculate totals
    total_amount = sum(c.amount for c in cheques_list)
    pending_amount = sum(c.amount for c in cheques_list if c.status == 'pending')
    deposited_amount = sum(c.amount for c in cheques_list if c.status == 'deposited')
    cleared_amount = sum(c.amount for c in cheques_list if c.status == 'cleared')
    bounced_amount = sum(c.amount for c in cheques_list if c.status == 'bounced')
    
    # Status counts with company filter
    def get_status_count(status):
        q = apply_company_filter(Cheque.query)
        return q.filter(Cheque.status == status).count()
    
    status_counts = {
        'pending': get_status_count('pending'),
        'deposited': get_status_count('deposited'),
        'cleared': get_status_count('cleared'),
        'bounced': get_status_count('bounced'),
        'cancelled': get_status_count('cancelled'),
    }
    
    # Upcoming/Overdue cheques with company filter
    today = datetime.today().date()
    upcoming_cheques = apply_company_filter(Cheque.query).filter(
        and_(
            Cheque.cheque_date > today,
            Cheque.status == 'pending'
        )
    ).count()
    
    overdue_cheques = apply_company_filter(Cheque.query).filter(
        and_(
            Cheque.cheque_date < today,
            Cheque.status == 'pending'
        )
    ).count()
    
    return render_template(
        'cheques/cheques.html',
        cheques=cheques_list,
        banks=banks,
        customers=customers,
        total_amount=total_amount,
        pending_amount=pending_amount,
        deposited_amount=deposited_amount,
        cleared_amount=cleared_amount,
        bounced_amount=bounced_amount,
        status_counts=status_counts,
        upcoming_cheques=upcoming_cheques,
        overdue_cheques=overdue_cheques,
        status_filter=status_filter,
        cheque_type=cheque_type_filter,
        start_date=start_date,
        end_date=end_date,
        bank_filter=bank_filter,
        customer_filter=customer_filter
    )


# ============================================================================
# CHEQUE CRUD OPERATIONS
# ============================================================================

@cheques_bp.route('/api/cheques', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_cheques():
    """Get cheques data as JSON with filtering."""
    status = request.args.get('status')
    cheque_type = request.args.get('cheque_type')  # 'payment' or 'received'
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = apply_company_filter(Cheque.query)
    
    if cheque_type == 'payment':
        query = query.filter(Cheque.supplier_id.isnot(None))
    elif cheque_type == 'received':
        query = query.filter(Cheque.customer_id.isnot(None))
    
    if status:
        query = query.filter(Cheque.status == status)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Cheque.cheque_date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Cheque.cheque_date <= end)
        except ValueError:
            pass
    
    cheques_list = query.order_by(desc(Cheque.cheque_date)).all()
    
    return jsonify({
        'cheques': [_cheque_to_dict(c) for c in cheques_list],
        'total': sum(c.amount for c in cheques_list),
        'count': len(cheques_list)
    })


@cheques_bp.route('/api/cheques', methods=['POST'])
@login_required
@require_permission('can_access_cheques')
def add_cheque():
    """Add a new cheque with optional image uploads."""
    try:
        # Handle form data + file uploads
        cheque_number = request.form.get('cheque_number')
        bank_name = request.form.get('bank_name')
        branch = request.form.get('branch', '')
        cheque_date = request.form.get('cheque_date')
        amount = request.form.get('amount')
        payer_name = request.form.get('payer_name') or request.form.get('customer_name', '')  # Backward compat
        customer_id = request.form.get('customer_id')
        supplier_id = request.form.get('supplier_id')
        notes = request.form.get('notes', '')
        is_partial = request.form.get('is_partial', 'false').lower() == 'true'
        
        # Validation
        if not cheque_number:
            return jsonify({'error': 'Cheque number is required'}), 400
        if not bank_name:
            return jsonify({'error': 'Bank name is required'}), 400
        if not cheque_date:
            return jsonify({'error': 'Cheque date is required'}), 400
        if not amount or float(amount) <= 0:
            return jsonify({'error': 'Valid amount is required'}), 400
        if not payer_name:
            return jsonify({'error': 'Payer name is required'}), 400
        
        # Note: customer_id and supplier_id are optional for backward compatibility
        # Old system used customer_name text field instead of customer_id
        
        # Check for duplicate cheque
        existing = Cheque.query.filter(
            and_(
                Cheque.cheque_number == cheque_number,
                Cheque.bank_name == bank_name
            )
        ).first()
        
        if existing:
            return jsonify({'error': 'Cheque number already exists for this bank'}), 400
        
        # Parse date
        cheque_date_obj = datetime.strptime(cheque_date, '%Y-%m-%d').date()
        
        # Create cheque
        cheque = Cheque(
            cheque_number=cheque_number,
            bank_name=bank_name,
            branch=branch,
            cheque_date=cheque_date_obj,
            amount=float(amount),
            payer_name=payer_name,
            customer_id=int(customer_id) if customer_id else None,
            supplier_id=int(supplier_id) if supplier_id else None,
            notes=notes,
            is_partial=is_partial,
            status='pending',
            created_by=current_user.id,
            company_id=get_company_id()
        )
        
        # Handle file uploads
        upload_folder = get_upload_folder()
        
        if 'image_front' in request.files:
            file = request.files['image_front']
            if file and file.filename and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    return jsonify({'error': 'Front image is too large (max 5MB)'}), 400
                filename = secure_filename(f"{cheque_number}_front_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                file.save(os.path.join(upload_folder, filename))
                cheque.image_front = filename
        
        if 'image_back' in request.files:
            file = request.files['image_back']
            if file and file.filename and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    return jsonify({'error': 'Back image is too large (max 5MB)'}), 400
                filename = secure_filename(f"{cheque_number}_back_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                file.save(os.path.join(upload_folder, filename))
                cheque.image_back = filename
        
        db.session.add(cheque)
        db.session.commit()
        
        return jsonify({
            'message': 'Cheque added successfully',
            'cheque': _cheque_to_dict(cheque)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cheques_bp.route('/api/cheques/<int:cheque_id>', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_cheque(cheque_id):
    """Get a single cheque by ID."""
    cheque = get_cheque_secure(cheque_id)
    if not cheque:
        return jsonify({'error': 'Cheque not found'}), 404
    return jsonify({'cheque': _cheque_to_dict(cheque)})


@cheques_bp.route('/api/cheques/<int:cheque_id>', methods=['PUT'])
@login_required
@require_permission('can_access_cheques')
def update_cheque(cheque_id):
    """Update an existing cheque."""
    cheque = get_cheque_secure(cheque_id)
    if not cheque:
        return jsonify({'error': 'Cheque not found'}), 404
    
    try:
        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        if 'cheque_number' in data and data['cheque_number']:
            cheque.cheque_number = data['cheque_number']
        if 'bank_name' in data and data['bank_name']:
            cheque.bank_name = data['bank_name']
        if 'branch' in data:
            cheque.branch = data['branch']
        if 'cheque_date' in data and data['cheque_date']:
            cheque.cheque_date = datetime.strptime(data['cheque_date'], '%Y-%m-%d').date()
        if 'amount' in data and data['amount']:
            cheque.amount = float(data['amount'])
        if 'payer_name' in data and data['payer_name']:
            cheque.payer_name = data['payer_name']
        if 'customer_name' in data and data['customer_name']:
            cheque.payer_name = data['customer_name']
        if 'notes' in data:
            cheque.notes = data['notes']
        if 'is_partial' in data:
            cheque.is_partial = str(data['is_partial']).lower() == 'true'
        
        # Handle file uploads
        upload_folder = get_upload_folder()
        
        if 'image_front' in request.files:
            file = request.files['image_front']
            if file and file.filename and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    return jsonify({'error': 'Front image is too large (max 5MB)'}), 400
                # Delete old image if exists
                if cheque.image_front:
                    try:
                        os.remove(os.path.join(upload_folder, cheque.image_front))
                    except:
                        pass
                filename = secure_filename(f"{cheque.cheque_number}_front_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                file.save(os.path.join(upload_folder, filename))
                cheque.image_front = filename
        
        if 'image_back' in request.files:
            file = request.files['image_back']
            if file and file.filename and allowed_file(file.filename):
                if file.content_length and file.content_length > MAX_FILE_SIZE:
                    return jsonify({'error': 'Back image is too large (max 5MB)'}), 400
                # Delete old image if exists
                if cheque.image_back:
                    try:
                        os.remove(os.path.join(upload_folder, cheque.image_back))
                    except:
                        pass
                filename = secure_filename(f"{cheque.cheque_number}_back_{datetime.now().timestamp()}.{file.filename.rsplit('.', 1)[1].lower()}")
                file.save(os.path.join(upload_folder, filename))
                cheque.image_back = filename
        
        cheque.updated_by = current_user.id
        cheque.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': 'Cheque updated successfully',
            'cheque': _cheque_to_dict(cheque)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cheques_bp.route('/api/cheques/<int:cheque_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_cheques')
def delete_cheque(cheque_id):
    """Delete a cheque."""
    cheque = get_cheque_secure(cheque_id)
    if not cheque:
        return jsonify({'error': 'Cheque not found'}), 404
    
    try:
        # Delete attached images
        upload_folder = get_upload_folder()
        if cheque.image_front:
            try:
                os.remove(os.path.join(upload_folder, cheque.image_front))
            except:
                pass
        if cheque.image_back:
            try:
                os.remove(os.path.join(upload_folder, cheque.image_back))
            except:
                pass
        
        db.session.delete(cheque)
        db.session.commit()
        return jsonify({'message': 'Cheque deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# CHEQUE STATUS TRACKING
# ============================================================================

@cheques_bp.route('/api/cheques/<int:cheque_id>/status', methods=['PUT'])
@login_required
@require_permission('can_access_cheques')
def update_cheque_status(cheque_id):
    """Update cheque status with audit trail."""
    cheque = get_cheque_secure(cheque_id)
    if not cheque:
        return jsonify({'error': 'Cheque not found'}), 404
    data = request.get_json()
    
    if not data or 'status' not in data:
        return jsonify({'error': 'Status is required'}), 400
    
    new_status = data['status']
    valid_statuses = ['pending', 'deposited', 'cleared', 'bounced', 'cancelled']
    
    if new_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    try:
        cheque.status = new_status
        cheque.status_updated_at = datetime.utcnow()
        cheque.updated_by = current_user.id
        cheque.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'message': f'Cheque status updated to {new_status}',
            'cheque': _cheque_to_dict(cheque)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cheques_bp.route('/api/cheques/alerts/upcoming', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_upcoming_cheques():
    """Get upcoming cheques for alerts."""
    days_ahead = request.args.get('days', 7, type=int)
    
    today = datetime.today().date()
    future_date = today + timedelta(days=days_ahead)
    
    cheques = Cheque.query.filter(
        and_(
            Cheque.cheque_date >= today,
            Cheque.cheque_date <= future_date,
            Cheque.status == 'pending'
        )
    ).order_by(Cheque.cheque_date).all()
    
    return jsonify({
        'upcoming': [_cheque_to_dict(c) for c in cheques],
        'count': len(cheques)
    })


@cheques_bp.route('/api/cheques/alerts/overdue', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_overdue_cheques():
    """Get overdue cheques for alerts."""
    today = datetime.today().date()
    
    cheques = Cheque.query.filter(
        and_(
            Cheque.cheque_date < today,
            Cheque.status == 'pending'
        )
    ).order_by(Cheque.cheque_date).all()
    
    return jsonify({
        'overdue': [_cheque_to_dict(c) for c in cheques],
        'count': len(cheques)
    })


@cheques_bp.route('/api/cheques/alerts/bounced', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_bounced_cheques():
    """Get bounced cheques for alerts."""
    cheques = Cheque.query.filter(
        Cheque.status == 'bounced'
    ).order_by(desc(Cheque.updated_at)).all()
    
    return jsonify({
        'bounced': [_cheque_to_dict(c) for c in cheques],
        'count': len(cheques)
    })


# ============================================================================
# CHEQUE DEPOSIT MANAGEMENT
# ============================================================================

@cheques_bp.route('/deposits')
@login_required
@require_permission('can_access_cheques')
def deposits():
    """Cheque deposits management page."""
    deposits_list = apply_company_filter(
        ChequeDeposit.query.order_by(desc(ChequeDeposit.created_at)), 
        ChequeDeposit
    ).all()
    
    # Calculate totals
    total_deposits = len(deposits_list)
    total_amount = sum(
        sum(c.amount for c in d.cheques) for d in deposits_list
    )
    
    return render_template(
        'cheques/deposits.html',
        deposits=deposits_list,
        total_deposits=total_deposits,
        total_amount=total_amount
    )


@cheques_bp.route('/api/deposits', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_deposits():
    """Get all deposits."""
    deposits_list = apply_company_filter(
        ChequeDeposit.query.order_by(desc(ChequeDeposit.created_at)), 
        ChequeDeposit
    ).all()
    
    return jsonify({
        'deposits': [_deposit_to_dict(d) for d in deposits_list]
    })


@cheques_bp.route('/api/deposits', methods=['POST'])
@login_required
@require_permission('can_access_cheques')
def create_deposit():
    """Create a new cheque deposit."""
    try:
        data = request.get_json()
        
        if not data or 'deposit_date' not in data or 'bank_account' not in data:
            return jsonify({'error': 'deposit_date and bank_account are required'}), 400
        
        if 'cheque_ids' not in data or not data['cheque_ids']:
            return jsonify({'error': 'At least one cheque must be included'}), 400
        
        deposit_date = datetime.strptime(data['deposit_date'], '%Y-%m-%d').date()
        bank_account = data['bank_account']
        reference_number = data.get('reference_number', '')
        notes = data.get('notes', '')
        cheque_ids = data['cheque_ids']
        
        # Create deposit
        deposit = ChequeDeposit(
            deposit_date=deposit_date,
            bank_account=bank_account,
            reference_number=reference_number,
            notes=notes,
            created_by=current_user.id,
            company_id=get_company_id()
        )
        
        db.session.add(deposit)
        db.session.flush()  # Get the deposit ID
        
        # Link cheques to deposit and update status
        for cheque_id in cheque_ids:
            cheque = Cheque.query.get(cheque_id)
            if cheque:
                cheque.deposit_id = deposit.id
                cheque.status = 'deposited'
                cheque.status_updated_at = datetime.utcnow()
                cheque.updated_by = current_user.id
        
        db.session.commit()
        
        return jsonify({
            'message': 'Deposit created successfully',
            'deposit': _deposit_to_dict(deposit)
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cheques_bp.route('/api/deposits/<int:deposit_id>', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_deposit(deposit_id):
    """Get a single deposit."""
    deposit = get_deposit_secure(deposit_id)
    if not deposit:
        return jsonify({'error': 'Deposit not found'}), 404
    return jsonify({'deposit': _deposit_to_dict(deposit)})


@cheques_bp.route('/api/deposits/<int:deposit_id>', methods=['PUT'])
@login_required
@require_permission('can_access_cheques')
def update_deposit(deposit_id):
    """Update a deposit."""
    deposit = get_deposit_secure(deposit_id)
    if not deposit:
        return jsonify({'error': 'Deposit not found'}), 404
    
    try:
        data = request.get_json()
        
        if 'deposit_date' in data:
            deposit.deposit_date = datetime.strptime(data['deposit_date'], '%Y-%m-%d').date()
        if 'bank_account' in data:
            deposit.bank_account = data['bank_account']
        if 'reference_number' in data:
            deposit.reference_number = data['reference_number']
        if 'notes' in data:
            deposit.notes = data['notes']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Deposit updated successfully',
            'deposit': _deposit_to_dict(deposit)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@cheques_bp.route('/api/deposits/<int:deposit_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_cheques')
def delete_deposit(deposit_id):
    """Delete a deposit and remove cheques from it."""
    deposit = get_deposit_secure(deposit_id)
    if not deposit:
        return jsonify({'error': 'Deposit not found'}), 404
    
    try:
        # Unlink cheques from deposit
        for cheque in deposit.cheques:
            cheque.deposit_id = None
            cheque.status = 'pending'
        
        db.session.delete(deposit)
        db.session.commit()
        
        return jsonify({'message': 'Deposit deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# REPORTS & SUMMARIES
# ============================================================================

@cheques_bp.route('/api/cheques/summary', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_cheque_summary():
    """Get cheque summary statistics."""
    # Get counts by status
    status_counts = {}
    status_totals = {}
    
    for status in ['pending', 'deposited', 'cleared', 'bounced', 'cancelled']:
        count = apply_company_filter(
            Cheque.query.filter(Cheque.status == status)
        ).count()
        status_counts[status] = count
        
        total = apply_company_filter(
            db.session.query(func.sum(Cheque.amount)).filter(
                Cheque.status == status
            )
        ).scalar() or 0
        status_totals[status] = float(total)
    
    # Get total count and amount
    total_count = apply_company_filter(Cheque.query).count()
    total_amount = apply_company_filter(
        db.session.query(func.sum(Cheque.amount))
    ).scalar() or 0
    
    # Alerts
    today = datetime.today().date()
    upcoming_count = apply_company_filter(
        Cheque.query.filter(
            and_(
                Cheque.cheque_date > today,
                Cheque.status == 'pending'
            )
        )
    ).count()
    
    overdue_count = apply_company_filter(
        Cheque.query.filter(
            and_(
                Cheque.cheque_date < today,
                Cheque.status == 'pending'
            )
        )
    ).count()
    
    bounced_count = apply_company_filter(
        Cheque.query.filter(Cheque.status == 'bounced')
    ).count()
    
    return jsonify({
        'total_count': total_count,
        'total_amount': float(total_amount),
        'status_counts': status_counts,
        'status_totals': status_totals,
        'alerts': {
            'upcoming': upcoming_count,
            'overdue': overdue_count,
            'bounced': bounced_count
        }
    })


@cheques_bp.route('/api/cheques/report', methods=['GET'])
@login_required
@require_permission('can_access_cheques')
def get_cheque_report():
    """Generate cheque report with filters."""
    report_type = request.args.get('type', 'all')  # all, pending, cleared, bounced
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    bank_filter = request.args.get('bank')
    customer_filter = request.args.get('customer')
    
    query = Cheque.query
    
    if report_type == 'pending':
        query = query.filter(Cheque.status == 'pending')
    elif report_type == 'cleared':
        query = query.filter(Cheque.status == 'cleared')
    elif report_type == 'bounced':
        query = query.filter(Cheque.status == 'bounced')
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Cheque.cheque_date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Cheque.cheque_date <= end)
        except ValueError:
            pass
    
    if bank_filter:
        query = query.filter(Cheque.bank_name.ilike(f'%{bank_filter}%'))
    
    if customer_filter:
        query = query.filter(Cheque.customer_id == int(customer_filter) if customer_filter.isdigit() else True)
    
    cheques_list = query.order_by(Cheque.cheque_date).all()
    
    return jsonify({
        'report': [_cheque_to_dict(c) for c in cheques_list],
        'total_amount': sum(c.amount for c in cheques_list),
        'count': len(cheques_list)
    })


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _cheque_to_dict(cheque):
    """Convert Cheque model to dictionary."""
    # Handle backward compatibility: use payer_name if available, otherwise use customer_name
    payer_name = cheque.payer_name
    if not payer_name and hasattr(cheque, 'customer_name'):
        payer_name = cheque.customer_name
    
    return {
        'id': cheque.id,
        'cheque_number': cheque.cheque_number,
        'bank_name': cheque.bank_name,
        'branch': cheque.branch or '',
        'cheque_date': cheque.cheque_date.strftime('%Y-%m-%d') if cheque.cheque_date else None,
        'amount': float(cheque.amount),
        'payer_name': payer_name,
        'customer': {
            'id': cheque.customer.id,
            'name': cheque.customer.name
        } if cheque.customer else None,
        'supplier': {
            'id': cheque.supplier.id,
            'name': cheque.supplier.name
        } if cheque.supplier else None,
        'notes': cheque.notes,
        'status': cheque.status,
        'status_updated_at': cheque.status_updated_at.strftime('%Y-%m-%d %H:%M:%S') if cheque.status_updated_at else None,
        'image_front': cheque.image_front,
        'image_back': cheque.image_back,
        'is_partial': cheque.is_partial,
        'deposit_id': cheque.deposit_id,
        'created_at': cheque.created_at.strftime('%Y-%m-%d %H:%M:%S') if cheque.created_at else None,
        'updated_at': cheque.updated_at.strftime('%Y-%m-%d %H:%M:%S') if cheque.updated_at else None,
        'created_by': cheque.creator.username if cheque.creator else None,
        'updated_by': cheque.updater.username if cheque.updater else None,
    }


def _deposit_to_dict(deposit):
    """Convert ChequeDeposit model to dictionary."""
    return {
        'id': deposit.id,
        'deposit_date': deposit.deposit_date.strftime('%Y-%m-%d'),
        'bank_account': deposit.bank_account,
        'reference_number': deposit.reference_number,
        'notes': deposit.notes,
        'cheques': [_cheque_to_dict(c) for c in deposit.cheques],
        'total_amount': sum(c.amount for c in deposit.cheques),
        'cheque_count': len(deposit.cheques),
        'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'created_by': deposit.creator.username if deposit.creator else None,
    }

