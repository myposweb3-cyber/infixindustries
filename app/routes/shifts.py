from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from app.models import CashierShift, CustomerPayment, Return, Sale, db
from app.utils.permissions import require_permission
from app.utils.security import get_company_id

shifts_bp = Blueprint('shifts', __name__, template_folder='../../templates')


def _company_filter(query, model):
    company_id = get_company_id()
    if company_id and hasattr(model, 'company_id'):
        return query.filter(model.company_id == company_id)
    return query


def _cash_summary(shift):
    sales_query = Sale.query.filter(
        Sale.date >= shift.opened_at,
        Sale.payment == 'Cash'
    )
    returns_query = Return.query.filter(
        Return.date >= shift.opened_at,
        Return.refund_method == 'Cash',
        Return.status == 'completed'
    )
    payments_query = CustomerPayment.query.filter(
        CustomerPayment.date >= shift.opened_at,
        CustomerPayment.payment_method == 'Cash'
    )
    sales_query = _company_filter(sales_query, Sale)
    returns_query = _company_filter(returns_query, Return)
    payments_query = _company_filter(payments_query, CustomerPayment)
    cash_sales = sum(float(s.total or 0) for s in sales_query.all())
    cash_returns = sum(float(r.refund_amount or 0) for r in returns_query.all())
    customer_payments = sum(float(p.amount or 0) for p in payments_query.all())
    expected = float(shift.opening_cash or 0) + cash_sales + customer_payments - cash_returns
    return {
        'cash_sales': round(cash_sales, 2),
        'cash_returns': round(cash_returns, 2),
        'customer_payments': round(customer_payments, 2),
        'expected_cash': round(expected, 2),
    }


def _serialize_shift(shift):
    summary = _cash_summary(shift)
    return {
        'id': shift.id,
        'status': shift.status,
        'opened_at': shift.opened_at.isoformat() if shift.opened_at else None,
        'closed_at': shift.closed_at.isoformat() if shift.closed_at else None,
        'opening_cash': round(float(shift.opening_cash or 0), 2),
        'expected_cash': round(float(shift.expected_cash if shift.expected_cash is not None else summary['expected_cash']), 2),
        'actual_cash': round(float(shift.actual_cash), 2) if shift.actual_cash is not None else None,
        'variance': round(float(shift.variance), 2) if shift.variance is not None else None,
        'notes': shift.notes or '',
        **summary,
    }


@shifts_bp.route('/shifts')
@login_required
@require_permission('can_access_sales')
def shifts_page():
    return render_template('sales/shifts.html')


@shifts_bp.route('/api/shifts/current')
@login_required
@require_permission('can_access_sales')
def current_shift():
    query = CashierShift.query.filter_by(user_id=current_user.id, status='open')
    query = _company_filter(query, CashierShift)
    shift = query.order_by(CashierShift.opened_at.desc()).first()
    return jsonify({'shift': _serialize_shift(shift) if shift else None})


@shifts_bp.route('/api/shifts/history')
@login_required
@require_permission('can_access_sales')
def shift_history():
    query = _company_filter(CashierShift.query, CashierShift)
    shifts = query.order_by(CashierShift.opened_at.desc()).limit(50).all()
    return jsonify({'shifts': [_serialize_shift(shift) for shift in shifts]})


@shifts_bp.route('/api/shifts/open', methods=['POST'])
@login_required
@require_permission('can_access_sales')
def open_shift():
    data = request.get_json(silent=True) or {}
    company_id = get_company_id()
    existing_query = CashierShift.query.filter_by(user_id=current_user.id, status='open')
    existing_query = _company_filter(existing_query, CashierShift)
    if existing_query.first():
        return jsonify({'error': 'You already have an open cashier shift'}), 409
    try:
        opening_cash = float(data.get('opening_cash', 0))
        if opening_cash < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Opening cash must be a non-negative number'}), 400
    shift = CashierShift(
        user_id=current_user.id,
        company_id=company_id,
        opening_cash=opening_cash,
        notes=(data.get('notes') or '').strip(),
    )
    db.session.add(shift)
    db.session.commit()
    return jsonify({'success': True, 'shift': _serialize_shift(shift)}), 201


@shifts_bp.route('/api/shifts/close', methods=['POST'])
@login_required
@require_permission('can_access_sales')
def close_shift():
    data = request.get_json(silent=True) or {}
    query = CashierShift.query.filter_by(user_id=current_user.id, status='open')
    query = _company_filter(query, CashierShift)
    shift = query.order_by(CashierShift.opened_at.desc()).first()
    if not shift:
        return jsonify({'error': 'No open cashier shift found'}), 404
    try:
        actual_cash = float(data.get('actual_cash'))
        if actual_cash < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Actual cash must be a non-negative number'}), 400
    summary = _cash_summary(shift)
    shift.expected_cash = summary['expected_cash']
    shift.actual_cash = actual_cash
    shift.variance = round(actual_cash - summary['expected_cash'], 2)
    shift.closed_at = datetime.utcnow()
    shift.closed_by_id = current_user.id
    shift.status = 'closed'
    shift.notes = (data.get('notes') or '').strip()
    db.session.commit()
    return jsonify({'success': True, 'shift': _serialize_shift(shift)})
