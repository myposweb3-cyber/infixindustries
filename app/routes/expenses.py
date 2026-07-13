from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from app.models import db, Expense, User
from app.utils.permissions import require_permission
from app.utils.security import get_company_id, require_company_context
from app.utils.audit import log_create, log_update, log_delete, log_audit
from datetime import datetime
from sqlalchemy import desc, or_

expenses_bp = Blueprint('expenses', __name__, template_folder='../../templates')

def get_expense_secure(expense_id):
    """Get an expense with company_id verification (security check)."""
    company_id = get_company_id()
    expense_query = Expense.query.filter_by(id=expense_id)
    if company_id and hasattr(Expense, 'company_id'):
        expense_query = expense_query.filter(Expense.company_id == company_id)
    return expense_query.first()

@expenses_bp.route('/expenses')
@login_required
@require_company_context
@require_permission('can_access_expenses')
def expenses():
    """Main expenses page."""
    # Get filter parameters
    category_filter = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Build query
    query = Expense.query
    
    # Apply company filter
    company_id = get_company_id()
    if company_id and hasattr(Expense, 'company_id'):
        query = query.filter(Expense.company_id == company_id)
    
    if category_filter:
        query = query.filter(Expense.category == category_filter)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Expense.date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            query = query.filter(Expense.date <= end)
        except ValueError:
            pass
    
    # Get all expenses ordered by date descending
    expenses_list = query.order_by(desc(Expense.date)).all()
    
    # Get expense categories
    categories_query = db.session.query(Expense.category)
    if company_id and hasattr(Expense, 'company_id'):
        categories_query = categories_query.filter(Expense.company_id == company_id)
    categories = categories_query.distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    # Calculate totals
    total_expenses = sum(e.amount for e in expenses_list)
    
    # Get category totals
    category_totals_query = db.session.query(
        Expense.category,
        db.func.sum(Expense.amount).label('total')
    )
    if company_id and hasattr(Expense, 'company_id'):
        category_totals_query = category_totals_query.filter(Expense.company_id == company_id)
    category_totals = category_totals_query.group_by(Expense.category).all()
    
    return render_template(
        'expenses/expenses.html',
        expenses=expenses_list,
        categories=categories,
        total_expenses=total_expenses,
        category_totals=category_totals,
        category_filter=category_filter,
        start_date=start_date,
        end_date=end_date
    )

@expenses_bp.route('/api/expenses', methods=['GET'])
@login_required
@require_permission('can_access_expenses')
def get_expenses():
    """Get expenses data as JSON."""
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    
    query = Expense.query
    
    # Apply company filter
    company_id = get_company_id()
    if company_id and hasattr(Expense, 'company_id'):
        query = query.filter(Expense.company_id == company_id)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Expense.date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            query = query.filter(Expense.date <= end)
        except ValueError:
            pass
    
    if category:
        query = query.filter(Expense.category == category)
    
    expenses_list = query.order_by(desc(Expense.date)).all()
    
    return jsonify({
        'expenses': [
            {
                'id': e.id,
                'date': e.date.strftime('%Y-%m-%d %H:%M'),
                'category': e.category,
                'description': e.description,
                'amount': float(e.amount)
            }
            for e in expenses_list
        ],
        'total': sum(e.amount for e in expenses_list)
    })

@expenses_bp.route('/api/expenses', methods=['POST'])
@login_required
@require_permission('can_access_expenses')
def add_expense():
    """Add a new expense."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    category = data.get('category')
    description = data.get('description', '')
    amount = data.get('amount')
    
    if not category:
        return jsonify({'error': 'Category is required'}), 400
    
    if not amount or float(amount) <= 0:
        return jsonify({'error': 'Valid amount is required'}), 400
    
    try:
        expense = Expense(
            category=category,
            description=description,
            amount=float(amount),
            date=datetime.utcnow(),
            company_id=get_company_id()  # Set company_id
        )
        db.session.add(expense)
        db.session.commit()
        
        # Log audit
        log_create('Expense', expense.id, {
            'category': expense.category,
            'description': expense.description,
            'amount': expense.amount
        }, description=f"Expense '{category}' of ₨{amount} recorded")
        
        return jsonify({
            'message': 'Expense added successfully',
            'expense': {
                'id': expense.id,
                'date': expense.date.strftime('%Y-%m-%d %H:%M'),
                'category': expense.category,
                'description': expense.description,
                'amount': float(expense.amount)
            }
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@expenses_bp.route('/api/expenses/<int:expense_id>', methods=['PUT'])
@login_required
@require_permission('can_access_expenses')
def update_expense(expense_id):
    """Update an existing expense."""
    expense = get_expense_secure(expense_id)
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Store old values for audit
    old_values = {
        'category': expense.category,
        'description': expense.description,
        'amount': expense.amount
    }
    
    category = data.get('category')
    description = data.get('description', '')
    amount = data.get('amount')
    
    if category:
        expense.category = category
    if description is not None:
        expense.description = description
    if amount and float(amount) > 0:
        expense.amount = float(amount)
    
    try:
        db.session.commit()
        
        # Store new values for audit
        new_values = {
            'category': expense.category,
            'description': expense.description,
            'amount': expense.amount
        }
        
        # Log audit
        log_update('Expense', expense_id, old_values, new_values,
                   description=f"Expense '{expense.category}' updated")
        
        return jsonify({
            'message': 'Expense updated successfully',
            'expense': {
                'id': expense.id,
                'date': expense.date.strftime('%Y-%m-%d %H:%M'),
                'category': expense.category,
                'description': expense.description,
                'amount': float(expense.amount)
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@expenses_bp.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_expenses')
def delete_expense(expense_id):
    """Delete an expense."""
    expense = get_expense_secure(expense_id)
    if not expense:
        return jsonify({'error': 'Expense not found'}), 404
    
    try:
        expense_category = expense.category
        expense_amount = expense.amount
        db.session.delete(expense)
        db.session.commit()
        
        # Log audit
        log_delete('Expense', expense_id, {'category': expense_category, 'amount': expense_amount},
                   description=f"Expense '{expense_category}' of ₨{expense_amount} deleted")
        
        return jsonify({'message': 'Expense deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@expenses_bp.route('/api/expenses/categories', methods=['GET'])
@login_required
@require_permission('can_access_expenses')
def get_expense_categories():
    """Get all expense categories."""
    company_id = get_company_id()
    categories_query = db.session.query(Expense.category)
    if company_id and hasattr(Expense, 'company_id'):
        categories_query = categories_query.filter(Expense.company_id == company_id)
    categories = categories_query.distinct().all()
    categories = [c[0] for c in categories if c[0]]
    
    # Default categories if none exist
    if not categories:
        categories = [
            'Rent',
            'Utilities',
            'Salaries',
            'Supplies',
            'Maintenance',
            'Marketing',
            'Transportation',
            'Insurance',
            'Taxes',
            'Miscellaneous'
        ]
    
    return jsonify({'categories': categories})

@expenses_bp.route('/api/expenses/summary', methods=['GET'])
@login_required
@require_permission('can_access_expenses')
def get_expense_summary():
    """Get expense summary statistics."""
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    company_id = get_company_id()
    
    query = Expense.query
    if company_id and hasattr(Expense, 'company_id'):
        query = query.filter(Expense.company_id == company_id)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Expense.date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            query = query.filter(Expense.date <= end)
        except ValueError:
            pass
    
    # Total expenses
    total = db.session.query(db.func.sum(Expense.amount)).filter(
        Expense.id.in_([e.id for e in query.all()])
    ).scalar() or 0
    
    # By category
    by_category_query = db.session.query(
        Expense.category,
        db.func.sum(Expense.amount).label('total'),
        db.func.count(Expense.id).label('count')
    )
    if company_id and hasattr(Expense, 'company_id'):
        by_category_query = by_category_query.filter(Expense.company_id == company_id)
    
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            by_category_query = by_category_query.filter(Expense.date >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            by_category_query = by_category_query.filter(Expense.date <= end)
        except ValueError:
            pass
    
    by_category = by_category_query.group_by(Expense.category).all()
    
    # Monthly breakdown
    monthly = db.session.query(
        db.func.strftime('%Y-%m', Expense.date).label('month'),
        db.func.sum(Expense.amount).label('total')
    )
    if company_id and hasattr(Expense, 'company_id'):
        monthly = monthly.filter(Expense.company_id == company_id)
    
    return jsonify({
        'total': float(total),
        'by_category': [
            {
                'category': c[0],
                'total': float(c[1] or 0),
                'count': c[2]
            }
            for c in by_category
        ],
        'monthly': [
            {
                'month': m[0],
                'total': float(m[1] or 0)
            }
            for m in monthly
        ]
    })
