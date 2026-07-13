from flask import Blueprint, render_template, request, jsonify, flash, send_file
from flask_login import login_required, current_user
from app.models import db, Sale, SaleItem, Product, Customer, InventoryTransaction, User, Return, ReturnItem, Expense, CustomerPayment
from app.utils.permissions import require_permission
from app.utils.security import get_company_id, require_company_context
from datetime import datetime, timedelta
from sqlalchemy import func, desc, and_, or_
import calendar
import io
import xlsxwriter
import pandas as pd
import pytz

reports_bp = Blueprint('reports', __name__, template_folder='../../templates')

# Timezone configuration (Pakistan Standard Time)
LOCAL_TIMEZONE = pytz.timezone('Asia/Karachi')

def get_company_filter(model):
    """Get company filter for a model - returns filter or None if no company_id column."""
    company_id = get_company_id()
    if company_id and hasattr(model, 'company_id'):
        return model.company_id == company_id
    return None

def to_local_datetime(dt):
    """Convert UTC datetime to local timezone."""
    if dt.tzinfo is None:
        # Assume UTC if naive
        dt = pytz.utc.localize(dt)
    return dt.astimezone(LOCAL_TIMEZONE)

@reports_bp.route('')
@login_required
@require_company_context
@require_permission('can_view_reports')
def reports():
    """Main reports dashboard page."""
    return render_template('reports/reports.html')

@reports_bp.route('/api/sales-summary')
@login_required
@require_company_context
def get_sales_summary():
    """Get sales summary data for dashboard."""
    company_id = get_company_id()
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        # Default to current month
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Total sales (gross)
    sales_query = db.session.query(func.sum(Sale.total)).filter(
        and_(Sale.date >= start, Sale.date <= end)
    )
    if company_id and hasattr(Sale, 'company_id'):
        sales_query = sales_query.filter(Sale.company_id == company_id)
    total_sales = sales_query.scalar() or 0

    # Total returns for the date range
    returns_query = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    )
    if company_id and hasattr(Return, 'company_id'):
        returns_query = returns_query.filter(Return.company_id == company_id)
    total_returns = returns_query.scalar() or 0

    # Net sales (sales - returns)
    net_sales = float(total_sales) - float(total_returns)

    # Total transactions
    trans_query = Sale.query.filter(
        and_(Sale.date >= start, Sale.date <= end)
    )
    if company_id and hasattr(Sale, 'company_id'):
        trans_query = trans_query.filter(Sale.company_id == company_id)
    total_transactions = trans_query.count()

    # Average transaction value (using net sales)
    avg_transaction = net_sales / total_transactions if total_transactions > 0 else 0

    # Total discounts given - use Sale.discount field for cart-level discount
    total_discounts_query = db.session.query(func.sum(Sale.discount)).filter(
        and_(Sale.date >= start, Sale.date <= end)
    )
    if company_id and hasattr(Sale, 'company_id'):
        total_discounts_query = total_discounts_query.filter(Sale.company_id == company_id)
    total_discounts = total_discounts_query.scalar() or 0

    # Calculate profit (revenue - cost)
    profit_query = db.session.query(
        func.sum(SaleItem.quantity * (SaleItem.price - Product.cost_price))
    ).join(Sale, Sale.id == SaleItem.sale_id)\
     .join(Product, Product.id == SaleItem.product_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        profit_query = profit_query.filter(Sale.company_id == company_id)
    total_profit = float(profit_query.scalar() or 0)

    # Top selling products
    top_products_query = db.session.query(
        Product.name,
        func.sum(SaleItem.quantity).label('total_quantity'),
        func.sum(SaleItem.quantity * SaleItem.price).label('total_revenue')
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        top_products_query = top_products_query.filter(Sale.company_id == company_id)
    top_products = top_products_query.group_by(Product.id, Product.name)\
     .order_by(desc('total_revenue'))\
     .limit(10).all()

    # Sales by payment method
    payment_methods_query = db.session.query(
        Sale.payment,
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        payment_methods_query = payment_methods_query.filter(Sale.company_id == company_id)
    payment_methods = payment_methods_query.group_by(Sale.payment).all()

    # Find top payment method
    top_payment_method = None
    top_payment_total = 0
    payment_methods_list = []
    for pm in payment_methods:
        payment_methods_list.append({
            'method': pm.payment, 
            'count': pm.count, 
            'total': float(pm.total)
        })
        if float(pm.total) > top_payment_total:
            top_payment_total = float(pm.total)
            top_payment_method = pm.payment

    # Daily sales data for chart
    daily_sales_query = db.session.query(
        func.date(Sale.date).label('date'),
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        daily_sales_query = daily_sales_query.filter(Sale.company_id == company_id)
    daily_sales = daily_sales_query.group_by(func.date(Sale.date))\
     .order_by('date').all()

    # Get all sold products details
    all_sold_products_query = db.session.query(
        Product.name,
        Product.category,
        Product.barcode,
        func.sum(SaleItem.quantity).label('total_quantity'),
        func.sum(SaleItem.quantity * SaleItem.price).label('total_revenue'),
        func.sum(SaleItem.quantity * (SaleItem.price - Product.cost_price)).label('total_profit')
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        all_sold_products_query = all_sold_products_query.filter(Sale.company_id == company_id)
    all_sold_products = all_sold_products_query.group_by(Product.id, Product.name, Product.category, Product.barcode)\
     .order_by(desc('total_quantity')).all()

    sold_products_list = []
    for p in all_sold_products:
        sold_products_list.append({
            'name': p.name,
            'category': p.category or 'Uncategorized',
            'sku': p.barcode or '-',
            'quantity': float(p.total_quantity),
            'revenue': float(p.total_revenue),
            'profit': float(p.total_profit or 0)
        })

    # Get customer purchase details
    customer_purchases_query = db.session.query(
        Sale.customer,
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total).label('total_purchases')
    ).filter(and_(Sale.date >= start, Sale.date <= end, Sale.customer != None))
    if company_id and hasattr(Sale, 'company_id'):
        customer_purchases_query = customer_purchases_query.filter(Sale.company_id == company_id)
    customer_purchases = customer_purchases_query.group_by(Sale.customer)\
     .order_by(desc('total_purchases')).limit(20).all()

    customer_list = []
    for c in customer_purchases:
        if c.customer and c.customer != 'Walk-in Customer':
            customer_list.append({
                'name': c.customer,
                'transactions': c.transactions,
                'total_purchases': float(c.total_purchases)
            })

    # Get operating expenses for the period
    operating_expenses_query = db.session.query(func.sum(Expense.amount)).filter(
        and_(Expense.date >= start, Expense.date <= end)
    )
    if company_id and hasattr(Expense, 'company_id'):
        operating_expenses_query = operating_expenses_query.filter(Expense.company_id == company_id)
    operating_expenses = operating_expenses_query.scalar() or 0

    # Net Profit = Gross Profit - Expenses
    # total_profit here is the gross profit (revenue - cost)
    net_profit = float(total_profit) - float(operating_expenses)

    return jsonify({
        'total_sales': float(total_sales),
        'net_sales': float(net_sales),
        'total_returns': float(total_returns),
        'total_transactions': total_transactions,
        'avg_transaction': float(avg_transaction),
        'total_discounts': float(total_discounts),
        'total_profit': float(total_profit),
        'operating_expenses': float(operating_expenses),
        'net_profit': net_profit,
        'top_payment_method': top_payment_method or 'N/A',
        'top_products': [
            {
                'name': product[0],
                'quantity': int(product[1]),
                'revenue': float(product[2])
            } for product in top_products
        ],
        'payment_methods': payment_methods_list,
        'daily_sales': [
            {
                'date': str(day[0]),
                'total': float(day[1])
            } for day in daily_sales
        ],
        'all_sold_products': sold_products_list,
        'customers': customer_list
    })

@reports_bp.route('/api/inventory-summary')
@login_required
def get_inventory_summary():
    """Get inventory summary data."""
    company_id = get_company_id()
    
    # Base query for products
    product_query = Product.query
    if company_id and hasattr(Product, 'company_id'):
        product_query = product_query.filter(Product.company_id == company_id)
    
    # Total products
    total_products = product_query.count()

    # Total inventory value
    total_value = db.session.query(func.sum(Product.stock * Product.cost_price))
    if company_id and hasattr(Product, 'company_id'):
        total_value = total_value.filter(Product.company_id == company_id)
    total_value = total_value.scalar() or 0

    # Low stock products
    low_stock_count = product_query.filter(Product.stock <= Product.low_stock_threshold).count()

    # Out of stock products
    out_of_stock_count = product_query.filter(Product.stock == 0).count()

    # Recent inventory transactions
    transaction_query = InventoryTransaction.query.order_by(desc(InventoryTransaction.date))
    if company_id and hasattr(InventoryTransaction, 'company_id'):
        transaction_query = transaction_query.filter(InventoryTransaction.company_id == company_id)
    recent_transactions = transaction_query.limit(10).all()

    # Inventory value by category
    category_values = db.session.query(
        Product.category,
        func.sum(Product.stock * Product.cost_price).label('value')
    ).filter(Product.category.isnot(None))
    if company_id and hasattr(Product, 'company_id'):
        category_values = category_values.filter(Product.company_id == company_id)
    category_values = category_values.group_by(Product.category).order_by(desc('value')).all()

    return jsonify({
        'total_products': total_products,
        'total_value': float(total_value),
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'recent_transactions': [
            {
                'date': to_local_datetime(transaction.date).strftime('%Y-%m-%d %H:%M'),
                'product_name': transaction.product.name,
                'type': transaction.transaction_type,
                'quantity': transaction.quantity,
                'notes': transaction.notes
            } for transaction in recent_transactions
        ],
        'category_values': [
            {
                'category': cat[0],
                'value': float(cat[1])
            } for cat in category_values
        ]
    })

@reports_bp.route('/api/customer-summary')
@login_required
def get_customer_summary():
    """Get customer summary data."""
    company_id = get_company_id()
    # Total customers
    customer_query = Customer.query
    if company_id and hasattr(Customer, 'company_id'):
        customer_query = customer_query.filter(Customer.company_id == company_id)
    total_customers = customer_query.count()

    # Active customers (purchased in last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    active_query = Customer.query.filter(
        Customer.last_purchase_date >= thirty_days_ago
    )
    if company_id and hasattr(Customer, 'company_id'):
        active_query = active_query.filter(Customer.company_id == company_id)
    active_customers = active_query.count()

    # New customers this month
    this_month = datetime.utcnow().replace(day=1)
    new_query = Customer.query.filter(
        Customer.registration_date >= this_month
    )
    if company_id and hasattr(Customer, 'company_id'):
        new_query = new_query.filter(Customer.company_id == company_id)
    new_customers = new_query.count()

    # Top customers by purchase value
    top_query = db.session.query(
        Customer.name,
        Customer.total_purchases,
        Customer.loyalty_points
    )
    if company_id and hasattr(Customer, 'company_id'):
        top_query = top_query.filter(Customer.company_id == company_id)
    top_customers = top_query.order_by(desc(Customer.total_purchases)).limit(10).all()

    # Customer acquisition over time
    monthly_query = db.session.query(
        func.date_trunc('month', Customer.registration_date).label('month'),
        func.count(Customer.id).label('count')
    )
    if company_id and hasattr(Customer, 'company_id'):
        monthly_query = monthly_query.filter(Customer.company_id == company_id)
    monthly_customers = monthly_query.group_by(func.date_trunc('month', Customer.registration_date))\
     .order_by('month').all()

    return jsonify({
        'total_customers': total_customers,
        'active_customers': active_customers,
        'new_customers': new_customers,
        'top_customers': [
            {
                'name': customer[0],
                'total_purchases': float(customer[1]),
                'loyalty_points': customer[2]
            } for customer in top_customers
        ],
        'monthly_customers': [
            {
                'month': str(customer[0].strftime('%Y-%m')),
                'count': customer[1]
            } for customer in monthly_customers
        ]
    })

@reports_bp.route('/api/profit-loss')
@login_required
@require_permission('can_view_profit')
def get_profit_loss_report():
    """Get profit and loss report."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        # Default to current month
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Step 1: Gross Sales (total sales)
    gross_sales_query = db.session.query(func.sum(Sale.total)).filter(
        and_(Sale.date >= start, Sale.date <= end)
    )
    if company_id and hasattr(Sale, 'company_id'):
        gross_sales_query = gross_sales_query.filter(Sale.company_id == company_id)
    gross_sales = gross_sales_query.scalar() or 0

    # Step 2: Total Returns (completed returns)
    returns_query = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    )
    if company_id and hasattr(Return, 'company_id'):
        returns_query = returns_query.filter(Return.company_id == company_id)
    total_returns = returns_query.scalar() or 0

    # Step 3: Net Sales = Gross Sales - Returns
    net_sales = float(gross_sales) - float(total_returns)

    # Step 4: Cost of goods sold (COGS) - based on net sales items
    cogs_query = db.session.query(func.sum(SaleItem.quantity * Product.cost_price))\
        .select_from(SaleItem)\
        .join(Product, Product.id == SaleItem.product_id)\
        .join(Sale, Sale.id == SaleItem.sale_id)\
        .filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        cogs_query = cogs_query.filter(Sale.company_id == company_id)
    cogs = cogs_query.scalar() or 0

    # Step 5: Gross Profit = Net Sales - COGS
    gross_profit = float(net_sales) - float(cogs)

    # Step 6: Get actual operating expenses from Expense table
    expense_query = db.session.query(func.sum(Expense.amount)).filter(
        and_(Expense.date >= start, Expense.date <= end)
    )
    if company_id and hasattr(Expense, 'company_id'):
        expense_query = expense_query.filter(Expense.company_id == company_id)
    operating_expenses = expense_query.scalar() or 0

    # Step 7: Net Profit = Gross Profit - Expenses
    net_profit = gross_profit - float(operating_expenses)

    # Monthly breakdown with proper formulas
    monthly_query = db.session.query(
        func.date_trunc('month', Sale.date).label('month'),
        func.sum(Sale.total).label('revenue'),
        func.sum(SaleItem.quantity * Product.cost_price).label('cogs')
    ).select_from(Sale)\
     .join(SaleItem, Sale.id == SaleItem.sale_id)\
     .join(Product, Product.id == SaleItem.product_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        monthly_query = monthly_query.filter(Sale.company_id == company_id)
    monthly_data = monthly_query.group_by(func.date_trunc('month', Sale.date))\
     .order_by('month').all()

    # Get returns by month for accurate monthly calculations
    returns_month_query = db.session.query(
        func.date_trunc('month', Return.date).label('month'),
        func.sum(Return.refund_amount).label('returns')
    ).filter(and_(Return.date >= start, Return.date <= end, Return.status == 'completed'))
    if company_id and hasattr(Return, 'company_id'):
        returns_month_query = returns_month_query.filter(Return.company_id == company_id)
    monthly_returns = returns_month_query.group_by(func.date_trunc('month', Return.date)).all()
    
    returns_by_month = {str(month.strftime('%Y-%m')): float(ret or 0) for month, ret in monthly_returns}

    # Get expenses by month
    expense_month_query = db.session.query(
        func.date_trunc('month', Expense.date).label('month'),
        func.sum(Expense.amount).label('expenses')
    ).filter(and_(Expense.date >= start, Expense.date <= end))
    if company_id and hasattr(Expense, 'company_id'):
        expense_month_query = expense_month_query.filter(Expense.company_id == company_id)
    monthly_expenses = expense_month_query.group_by(func.date_trunc('month', Expense.date)).all()
    
    expenses_by_month = {str(month.strftime('%Y-%m')): float(exp or 0) for month, exp in monthly_expenses}

    monthly_breakdown = []
    for month_data in monthly_data:
        month_key = str(month_data[0].strftime('%Y-%m'))
        month_gross_sales = float(month_data[1] or 0)
        month_returns = returns_by_month.get(month_key, 0)
        month_net_sales = month_gross_sales - month_returns
        month_cogs = float(month_data[2] or 0)
        month_gross_profit = month_net_sales - month_cogs
        month_expenses = expenses_by_month.get(month_key, 0)
        month_net_profit = month_gross_profit - month_expenses
        
        monthly_breakdown.append({
            'month': month_key,
            'gross_sales': month_gross_sales,
            'returns': month_returns,
            'net_sales': month_net_sales,
            'cogs': month_cogs,
            'gross_profit': month_gross_profit,
            'expenses': month_expenses,
            'net_profit': month_net_profit
        })

    return jsonify({
        'period': {
            'start_date': start_date,
            'end_date': end_date
        },
        'summary': {
            'gross_sales': float(gross_sales),
            'returns': float(total_returns),
            'net_sales': float(net_sales),
            'cogs': float(cogs),
            'gross_profit': gross_profit,
            'operating_expenses': float(operating_expenses),
            'net_profit': net_profit
        },
        'monthly_breakdown': monthly_breakdown
    })

@reports_bp.route('/api/export/<report_type>')
@login_required
def export_report(report_type):
    """Export report data as CSV."""
    # This would generate CSV data for download
    # For now, return JSON that can be converted to CSV on frontend
    if report_type == 'sales':
        return get_sales_summary()
    elif report_type == 'inventory':
        return get_inventory_summary()
    elif report_type == 'customers':
        return get_customer_summary()
    else:
        return jsonify({'error': 'Invalid report type'}), 400


@reports_bp.route('/api/refunds')
@login_required
@require_permission('can_view_reports')
def get_refund_report():
    """Refund report summarizing returns/refunds."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    total_refunds_query = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    )
    if company_id and hasattr(Return, 'company_id'):
        total_refunds_query = total_refunds_query.filter(Return.company_id == company_id)
    total_refunds = total_refunds_query.scalar() or 0

    refunds_query = db.session.query(Return.return_reason, func.count(Return.id), func.sum(Return.refund_amount))
    refunds_query = refunds_query.filter(and_(Return.date >= start, Return.date <= end))
    if company_id and hasattr(Return, 'company_id'):
        refunds_query = refunds_query.filter(Return.company_id == company_id)
    refunds_by_reason = refunds_query.group_by(Return.return_reason).all()

    # Top refunded products
    top_products_query = db.session.query(
        Product.name,
        func.sum(ReturnItem.quantity).label('qty'),
        func.sum(ReturnItem.quantity * ReturnItem.price).label('amount')
    ).join(ReturnItem, Product.id == ReturnItem.product_id)
    top_products_query = top_products_query.join(Return, Return.id == ReturnItem.return_id)
    top_products_query = top_products_query.filter(and_(Return.date >= start, Return.date <= end))
    if company_id and hasattr(Return, 'company_id'):
        top_products_query = top_products_query.filter(Return.company_id == company_id)
    top_refunded_products = top_products_query.group_by(Product.id, Product.name).order_by(desc('amount')).limit(10).all()

    return jsonify({
        'period': {'start_date': start_date, 'end_date': end_date},
        'total_refunds': float(total_refunds),
        'by_reason': [
            {'reason': r[0], 'count': int(r[1]), 'amount': float(r[2] or 0)} for r in refunds_by_reason
        ],
        'top_products': [
            {'product': p[0], 'quantity': float(p[1] or 0), 'amount': float(p[2] or 0)} for p in top_refunded_products
        ]
    })


@reports_bp.route('/api/export/excel/<report_type>')
def export_report_excel(report_type):
    """Export report data as Excel file."""
    # Check authentication manually
    if not current_user.is_authenticated:
        return jsonify({'error': 'Please log in to export reports'}), 401
    
    # Handle routes that should have permissions checked
    detailed_types = ['sales-detail', 'payment-detail', 'cashier-detail', 'category-detail', 'return-detail']
    if report_type in detailed_types:
        if not (current_user.role and current_user.role.lower() in ['admin', 'super admin']) and not getattr(current_user, 'can_view_reports', False):
            return jsonify({'error': 'Permission denied'}), 403
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # Create Excel file in memory
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # Define formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    if report_type == 'sales':
        # Sales Summary Sheet
        ws = workbook.add_worksheet('Sales Summary')
        
        # Get sales data
        total_sales = db.session.query(func.sum(Sale.total)).filter(
            and_(Sale.date >= start, Sale.date <= end)
        ).scalar() or 0
        
        # Get total returns
        total_returns = db.session.query(func.sum(Return.refund_amount)).filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        ).scalar() or 0
        
        # Calculate Net Sales
        net_sales = float(total_sales) - float(total_returns)
        
        company_id = get_company_id()
        total_transactions = Sale.query.filter(
            and_(Sale.date >= start, Sale.date <= end, Sale.company_id == company_id)
        ).count()
        
        # Write header
        ws.write('A1', 'Sales Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        ws.write('A4', 'Metric', bold_format)
        ws.write('B4', 'Value', bold_format)
        
        ws.write('A5', 'Gross Sales')
        ws.write('B5', float(total_sales), money_format)
        ws.write('A6', 'Total Returns')
        ws.write('B6', float(total_returns), money_format)
        ws.write('A7', 'Net Sales')
        ws.write('B7', float(net_sales), money_format)
        ws.write('A8', 'Total Transactions')
        ws.write('B8', total_transactions)
        ws.write('A9', 'Average Transaction')
        ws.write('B9', float(net_sales) / total_transactions if total_transactions > 0 else 0, money_format)
        
        # Top Products Sheet
        ws2 = workbook.add_worksheet('Top Products')
        
        top_products = db.session.query(
            Product.name,
            func.sum(SaleItem.quantity).label('total_quantity'),
            func.sum(SaleItem.quantity * SaleItem.price).label('total_revenue')
        ).join(SaleItem, Product.id == SaleItem.product_id)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(and_(Sale.date >= start, Sale.date <= end))\
         .group_by(Product.id, Product.name)\
         .order_by(desc('total_revenue')).all()
        
        ws2.write('A1', 'Top Selling Products', bold_format)
        ws2.write('A2', f'Period: {start_date} to {end_date}')
        
        ws2.write('A4', 'Product Name', header_format)
        ws2.write('B4', 'Quantity Sold', header_format)
        ws2.write('C4', 'Revenue', header_format)
        
        row = 4
        for product in top_products:
            ws2.write(row, 0, product[0])
            ws2.write(row, 1, int(product[1]))
            ws2.write(row, 2, float(product[2]), money_format)
            row += 1
        
        # Payment Methods Sheet
        ws3 = workbook.add_worksheet('Payment Methods')
        
        payment_methods = db.session.query(
            Sale.payment,
            func.count(Sale.id).label('count'),
            func.sum(Sale.total).label('total')
        ).filter(and_(Sale.date >= start, Sale.date <= end))\
         .group_by(Sale.payment).all()
        
        ws3.write('A1', 'Sales by Payment Method', bold_format)
        
        ws3.write('A3', 'Payment Method', header_format)
        ws3.write('B3', 'Transactions', header_format)
        ws3.write('C3', 'Total Amount', header_format)
        
        row = 3
        for method in payment_methods:
            ws3.write(row, 0, method[0])
            ws3.write(row, 1, method[1])
            ws3.write(row, 2, float(method[2]), money_format)
            row += 1
        
        # Daily Sales Sheet
        ws4 = workbook.add_worksheet('Daily Sales')
        
        daily_sales = db.session.query(
            func.date(Sale.date).label('date'),
            func.sum(Sale.total).label('total')
        ).filter(and_(Sale.date >= start, Sale.date <= end))\
         .group_by(func.date(Sale.date))\
         .order_by('date').all()
        
        ws4.write('A1', 'Daily Sales', bold_format)
        
        ws4.write('A3', 'Date', header_format)
        ws4.write('B3', 'Total Sales', header_format)
        
        row = 3
        for day in daily_sales:
            ws4.write(row, 0, str(day[0]))
            ws4.write(row, 1, float(day[1]), money_format)
            row += 1
        
    elif report_type == 'inventory':
        # Inventory Summary Sheet
        ws = workbook.add_worksheet('Inventory Summary')
        
        total_products = Product.query.count()
        total_value = db.session.query(func.sum(Product.stock * Product.cost_price)).scalar() or 0
        low_stock_count = Product.query.filter(Product.stock <= Product.low_stock_threshold).count()
        out_of_stock_count = Product.query.filter(Product.stock == 0).count()
        
        ws.write('A1', 'Inventory Report', bold_format)
        
        ws.write('A3', 'Metric', bold_format)
        ws.write('B3', 'Value', bold_format)
        
        ws.write('A4', 'Total Products')
        ws.write('B4', total_products)
        ws.write('A5', 'Total Inventory Value')
        ws.write('B5', float(total_value), money_format)
        ws.write('A6', 'Low Stock Items')
        ws.write('B6', low_stock_count)
        ws.write('A7', 'Out of Stock')
        ws.write('B7', out_of_stock_count)
        
        # Products Sheet
        ws2 = workbook.add_worksheet('All Products')
        
        products_query = Product.query
        company_filter = get_company_filter(Product)
        if company_filter is not None:
            products_query = products_query.filter(company_filter)
        products = products_query.all()
        
        ws2.write('A1', 'Product Name', header_format)
        ws2.write('B1', 'Category', header_format)
        ws2.write('C1', 'Stock', header_format)
        ws2.write('D1', 'Cost Price', header_format)
        ws2.write('E1', 'Selling Price', header_format)
        ws2.write('F1', 'Stock Value', header_format)
        
        row = 1
        for product in products:
            ws2.write(row, 0, product.name)
            ws2.write(row, 1, product.category or 'N/A')
            ws2.write(row, 2, product.stock)
            ws2.write(row, 3, float(product.cost_price or 0), money_format)
            ws2.write(row, 4, float(product.price), money_format)
            ws2.write(row, 5, float(product.stock * (product.cost_price or 0)), money_format)
            row += 1
        
        # Category Values Sheet
        ws3 = workbook.add_worksheet('Category Values')
        
        category_values = db.session.query(
            Product.category,
            func.sum(Product.stock * Product.cost_price).label('value')
        ).filter(Product.category.isnot(None))\
         .group_by(Product.category)\
         .order_by(desc('value')).all()
        
        ws3.write('A1', 'Inventory Value by Category', bold_format)
        
        ws3.write('A3', 'Category', header_format)
        ws3.write('B3', 'Value', header_format)
        
        row = 3
        for cat in category_values:
            ws3.write(row, 0, cat[0] or 'Uncategorized')
            ws3.write(row, 1, float(cat[1]), money_format)
            row += 1
        
    elif report_type == 'customers':
        # Customer Summary Sheet
        ws = workbook.add_worksheet('Customer Summary')
        
        total_customers = Customer.query.count()
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        active_customers = Customer.query.filter(
            Customer.last_purchase_date >= thirty_days_ago
        ).count()
        this_month = datetime.utcnow().replace(day=1)
        new_customers = Customer.query.filter(
            Customer.registration_date >= this_month
        ).count()
        
        ws.write('A1', 'Customer Report', bold_format)
        
        ws.write('A3', 'Metric', bold_format)
        ws.write('B3', 'Value', bold_format)
        
        ws.write('A4', 'Total Customers')
        ws.write('B4', total_customers)
        ws.write('A5', 'Active Customers (30 days)')
        ws.write('B5', active_customers)
        ws.write('A6', 'New This Month')
        ws.write('B6', new_customers)
        
        # Top Customers Sheet
        ws2 = workbook.add_worksheet('Top Customers')
        
        top_customers = db.session.query(
            Customer.name,
            Customer.total_purchases,
            Customer.loyalty_points
        ).order_by(desc(Customer.total_purchases)).limit(50).all()
        
        ws2.write('A1', 'Top Customers by Purchase Value', bold_format)
        
        ws2.write('A3', 'Customer Name', header_format)
        ws2.write('B3', 'Total Purchases', header_format)
        ws2.write('C3', 'Loyalty Points', header_format)
        
        row = 3
        for customer in top_customers:
            ws2.write(row, 0, customer[0])
            ws2.write(row, 1, float(customer[1]), money_format)
            ws2.write(row, 2, customer[2] or 0)
            row += 1
        
    elif report_type == 'returns':
        # Returns/Refunds Sheet
        ws = workbook.add_worksheet('Returns & Refunds')
        
        total_refunds = db.session.query(func.sum(Return.refund_amount)).filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        ).scalar() or 0
        
        returns_count = Return.query.filter(
            and_(Return.date >= start, Return.date <= end)
        ).count()
        
        completed_count = Return.query.filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        ).count()
        
        pending_count = Return.query.filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'pending')
        ).count()
        
        ws.write('A1', 'Returns & Refunds Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        ws.write('A4', 'Metric', bold_format)
        ws.write('B4', 'Value', bold_format)
        
        ws.write('A5', 'Total Returns')
        ws.write('B5', returns_count)
        ws.write('A6', 'Total Refund Amount')
        ws.write('B6', float(total_refunds), money_format)
        ws.write('A7', 'Completed')
        ws.write('B7', completed_count)
        ws.write('A8', 'Pending')
        ws.write('B8', pending_count)
        
        # Returns Details Sheet
        ws2 = workbook.add_worksheet('Returns Details')
        
        returns = Return.query.filter(
            and_(Return.date >= start, Return.date <= end)
        ).order_by(desc(Return.date)).all()
        
        ws2.write('A1', 'Returns Details', bold_format)
        
        ws2.write('A3', 'Return ID', header_format)
        ws2.write('B3', 'Date', header_format)
        ws2.write('C3', 'Customer', header_format)
        ws2.write('D3', 'Original Sale', header_format)
        ws2.write('E3', 'Reason', header_format)
        ws2.write('F3', 'Refund Method', header_format)
        ws2.write('G3', 'Amount', header_format)
        ws2.write('H3', 'Status', header_format)
        
        row = 3
        for ret in returns:
            ws2.write(row, 0, ret.id)
            ws2.write(row, 1, to_local_datetime(ret.date).strftime('%Y-%m-%d %H:%M'))
            ws2.write(row, 2, ret.customer)
            ws2.write(row, 3, ret.original_sale_id)
            ws2.write(row, 4, ret.return_reason)
            ws2.write(row, 5, ret.refund_method)
            ws2.write(row, 6, float(ret.refund_amount), money_format)
            ws2.write(row, 7, ret.status)
            row += 1
        
    elif report_type == 'profit':
        # Profit & Loss Sheet with proper formulas
        ws = workbook.add_worksheet('Profit & Loss')
        
        # Step 1: Gross Sales
        gross_sales = db.session.query(func.sum(Sale.total)).filter(
            and_(Sale.date >= start, Sale.date <= end)
        ).scalar() or 0
        
        # Step 2: Total Returns
        total_returns = db.session.query(func.sum(Return.refund_amount)).filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        ).scalar() or 0
        
        # Step 3: Net Sales = Gross Sales - Returns
        net_sales = float(gross_sales) - float(total_returns)
        
        # Step 4: COGS
        cogs = db.session.query(func.sum(SaleItem.quantity * Product.cost_price))\
            .select_from(SaleItem)\
            .join(Product, Product.id == SaleItem.product_id)\
            .join(Sale, Sale.id == SaleItem.sale_id)\
            .filter(and_(Sale.date >= start, Sale.date <= end)).scalar() or 0
        
        # Step 5: Gross Profit = Net Sales - COGS
        gross_profit = float(net_sales) - float(cogs)
        
        # Step 6: Get actual expenses
        operating_expenses = db.session.query(func.sum(Expense.amount)).filter(
            and_(Expense.date >= start, Expense.date <= end)
        ).scalar() or 0
        
        # Step 7: Net Profit = Gross Profit - Expenses
        net_profit = gross_profit - float(operating_expenses)
        
        ws.write('A1', 'Profit & Loss Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        ws.write('A4', 'Metric', bold_format)
        ws.write('B4', 'Value', bold_format)
        
        ws.write('A5', 'Gross Sales')
        ws.write('B5', float(gross_sales), money_format)
        ws.write('A6', 'Returns')
        ws.write('B6', float(total_returns), money_format)
        ws.write('A7', 'Net Sales')
        ws.write('B7', float(net_sales), money_format)
        ws.write('A8', 'Cost of Goods Sold')
        ws.write('B8', float(cogs), money_format)
        ws.write('A9', 'Gross Profit')
        ws.write('B9', gross_profit, money_format)
        ws.write('A10', 'Operating Expenses')
        ws.write('B10', float(operating_expenses), money_format)
        ws.write('A11', 'Net Profit')
        ws.write('B11', net_profit, money_format)
        
        # Monthly Breakdown Sheet - Using proper formulas: Net Sales = Gross Sales - Returns
        ws2 = workbook.add_worksheet('Monthly Profit & Loss')
        
        # Get monthly sales data
        monthly_sales = db.session.query(
            func.date_trunc('month', Sale.date).label('month'),
            func.sum(Sale.total).label('revenue'),
            func.sum(SaleItem.quantity * Product.cost_price).label('cogs')
        ).join(SaleItem, Sale.id == SaleItem.sale_id)\
         .join(Product, Product.id == SaleItem.product_id)\
         .filter(and_(Sale.date >= start, Sale.date <= end))\
         .group_by(func.date_trunc('month', Sale.date))\
         .order_by('month').all()
        
        # Get monthly returns
        monthly_returns = db.session.query(
            func.date_trunc('month', Return.date).label('month'),
            func.sum(Return.refund_amount).label('returns')
        ).filter(and_(Return.date >= start, Return.date <= end, Return.status == 'completed'))\
         .group_by(func.date_trunc('month', Return.date)).all()
        
        returns_by_month = {str(month.strftime('%Y-%m')): float(ret or 0) for month, ret in monthly_returns}
        
        # Get monthly expenses
        monthly_expenses = db.session.query(
            func.date_trunc('month', Expense.date).label('month'),
            func.sum(Expense.amount).label('expenses')
        ).filter(and_(Expense.date >= start, Expense.date <= end))\
         .group_by(func.date_trunc('month', Expense.date)).all()
        
        expenses_by_month = {str(month.strftime('%Y-%m')): float(exp or 0) for month, exp in monthly_expenses}
        
        ws2.write('A1', 'Monthly Profit & Loss', bold_format)
        
        ws2.write('A3', 'Month', header_format)
        ws2.write('B3', 'Gross Sales', header_format)
        ws2.write('C3', 'Returns', header_format)
        ws2.write('D3', 'Net Sales', header_format)
        ws2.write('E3', 'COGS', header_format)
        ws2.write('F3', 'Gross Profit', header_format)
        ws2.write('G3', 'Expenses', header_format)
        ws2.write('H3', 'Net Profit', header_format)
        
        row = 3
        for month_data in monthly_sales:
            month_key = str(month_data[0].strftime('%Y-%m'))
            month_gross_sales = float(month_data[1] or 0)
            month_returns = returns_by_month.get(month_key, 0)
            month_net_sales = month_gross_sales - month_returns
            month_cogs = float(month_data[2] or 0)
            month_gross_profit = month_net_sales - month_cogs
            month_expenses = expenses_by_month.get(month_key, 0)
            month_net_profit = month_gross_profit - month_expenses
            
            ws2.write(row, 0, month_key)
            ws2.write(row, 1, month_gross_sales, money_format)
            ws2.write(row, 2, month_returns, money_format)
            ws2.write(row, 3, month_net_sales, money_format)
            ws2.write(row, 4, month_cogs, money_format)
            ws2.write(row, 5, month_gross_profit, money_format)
            ws2.write(row, 6, month_expenses, money_format)
            ws2.write(row, 7, month_net_profit, money_format)
            row += 1
    
    elif report_type == 'sales-detail':
        # Detailed Sales Report
        ws = workbook.add_worksheet('Sales Details')
        
        ws.write('A1', 'Detailed Sales Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        sale_filter = get_company_filter(Sale)
        total_sales_query = db.session.query(func.sum(Sale.total)).filter(
            and_(Sale.date >= start, Sale.date <= end)
        )
        if sale_filter is not None:
            total_sales_query = total_sales_query.filter(sale_filter)
        total_sales = total_sales_query.scalar() or 0
        
        return_filter = get_company_filter(Return)
        total_returns_query = db.session.query(func.sum(Return.refund_amount)).filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        )
        if return_filter is not None:
            total_returns_query = total_returns_query.filter(return_filter)
        total_returns = total_returns_query.scalar() or 0
        
        net_sales = float(total_sales) - float(total_returns)
        
        ws.write('A3', 'Summary', bold_format)
        ws.write('A4', 'Gross Sales:')
        ws.write('B4', float(total_sales), money_format)
        ws.write('A5', 'Total Returns:')
        ws.write('B5', float(total_returns), money_format)
        ws.write('A6', 'Net Sales:')
        ws.write('B6', float(net_sales), money_format)
        
        headers = ['Date', 'Time', 'Invoice No', 'Customer', 'Total Items', 'Sub Total', 'Discount', 'Tax', 'Grand Total', 'Payment Method', 'Cashier']
        for col, header in enumerate(headers):
            ws.write(9, col, header, header_format)
        
        sales_query = db.session.query(Sale, User.username).join(User, Sale.user_id == User.id)\
            .filter(and_(Sale.date >= start, Sale.date <= end))
        sale_filter = get_company_filter(Sale)
        if sale_filter is not None:
            sales_query = sales_query.filter(sale_filter)
        sales_data = sales_query.order_by(desc(Sale.date)).all()
        
        row = 10
        for sale, username in sales_data:
            sale_items = SaleItem.query.filter_by(sale_id=sale.id).all()
            total_items = sum(item.quantity for item in sale_items)
            item_discount = sum(item.discount or 0 for item in sale_items)
            cart_discount = float(sale.discount or 0)
            total_discount = item_discount + cart_discount
            total_tax = sum(item.tax or 0 for item in sale_items)
            subtotal = float(sale.total) - float(total_tax) + float(total_discount)
            
            local_dt = to_local_datetime(sale.date)
            ws.write(row, 0, local_dt.strftime('%Y-%m-%d'))
            ws.write(row, 1, local_dt.strftime('%H:%M:%S'))
            ws.write(row, 2, f'INV-{sale.id:06d}')
            ws.write(row, 3, sale.customer)
            ws.write(row, 4, int(total_items))
            ws.write(row, 5, round(subtotal, 2), money_format)
            ws.write(row, 6, round(float(total_discount), 2), money_format)
            ws.write(row, 7, round(float(total_tax), 2), money_format)
            ws.write(row, 8, round(float(sale.total), 2), money_format)
            ws.write(row, 9, sale.payment)
            ws.write(row, 10, username)
            row += 1
        
        ws.set_column('A:A', 12)
        ws.set_column('B:B', 10)
        ws.set_column('C:C', 14)
        ws.set_column('D:D', 20)
        ws.set_column('E:K', 14)
    
    elif report_type == 'payment-detail':
        # Payment Details Report
        ws = workbook.add_worksheet('Payment Summary')
        
        ws.write('A1', 'Payment Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        payment_totals = db.session.query(
            Sale.payment,
            func.count(Sale.id).label('count'),
            func.sum(Sale.total).label('total')
        ).filter(and_(Sale.date >= start, Sale.date <= end)).group_by(Sale.payment).all()
        
        cash_total = card_total = qr_total = credit_total = 0
        for payment, count, total in payment_totals:
            payment_lower = payment.lower() if payment else ''
            amount = float(total or 0)
            if 'cash' in payment_lower:
                cash_total += amount
            elif 'card' in payment_lower:
                card_total += amount
            elif 'qr' in payment_lower:
                qr_total += amount
            else:
                credit_total += amount
        
        total_sales = cash_total + card_total + qr_total + credit_total
        
        ws.write('A4', 'Payment Method', header_format)
        ws.write('B4', 'Total Amount', header_format)
        
        ws.write('A5', 'Cash')
        ws.write('B5', cash_total, money_format)
        
        ws.write('A6', 'Card')
        ws.write('B6', card_total, money_format)
        
        ws.write('A7', 'QR')
        ws.write('B7', qr_total, money_format)
        
        ws.write('A8', 'Credit')
        ws.write('B8', credit_total, money_format)
        
        ws.write('A10', 'TOTAL')
        ws.write('B10', total_sales, money_format)
    
    elif report_type == 'cashier-detail':
        # Cashier Details Report
        ws = workbook.add_worksheet('Cashier Performance')
        
        ws.write('A1', 'Cashier Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        ws.write('A4', 'Cashier Name', header_format)
        ws.write('B4', 'Total Sales', header_format)
        ws.write('C4', 'Transactions', header_format)
        
        cashier_sales = db.session.query(
            User.username,
            func.count(Sale.id).label('transactions'),
            func.sum(Sale.total).label('total_sales')
        ).join(Sale, User.id == Sale.user_id)\
         .filter(and_(Sale.date >= start, Sale.date <= end))\
         .group_by(User.id, User.username).all()
        
        row = 4
        for username, transactions, sales in cashier_sales:
            total_sales = float(sales or 0)
            transaction_count = int(transactions or 0)
            
            ws.write(row, 0, username)
            ws.write(row, 1, total_sales, money_format)
            ws.write(row, 2, transaction_count)
            row += 1
        
        ws.set_column('A:C', 20)
    
    elif report_type == 'category-detail':
        # Category Performance Report
        ws = workbook.add_worksheet('Category Performance')
        
        ws.write('A1', 'Category Performance Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        ws.write('A4', 'Category', header_format)
        ws.write('B4', 'Quantity Sold', header_format)
        ws.write('C4', 'Revenue', header_format)
        ws.write('D4', 'Cost', header_format)
        ws.write('E4', 'Profit', header_format)
        
        category_data = db.session.query(
            Product.category,
            func.sum(SaleItem.quantity).label('quantity_sold'),
            func.sum(SaleItem.quantity * SaleItem.price).label('revenue'),
            func.sum(SaleItem.quantity * Product.cost_price).label('cost')
        ).join(SaleItem, Product.id == SaleItem.product_id)\
         .join(Sale, Sale.id == SaleItem.sale_id)\
         .filter(and_(Sale.date >= start, Sale.date <= end))\
         .group_by(Product.category)\
         .order_by(desc('revenue')).all()
        
        row = 4
        for category, quantity, revenue, cost in category_data:
            qty = float(quantity or 0)
            rev = float(revenue or 0)
            cst = float(cost or 0)
            profit = rev - cst
            
            ws.write(row, 0, category or 'Uncategorized')
            ws.write(row, 1, round(qty, 2))
            ws.write(row, 2, rev, money_format)
            ws.write(row, 3, cst, money_format)
            ws.write(row, 4, profit, money_format)
            row += 1
        
        ws.set_column('A:E', 20)
    
    elif report_type == 'return-detail':
        # Returns/Refunds Report
        ws = workbook.add_worksheet('Returns & Refunds')
        
        total_refunds = db.session.query(func.sum(Return.refund_amount)).filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        ).scalar() or 0
        
        returns_count = Return.query.filter(and_(Return.date >= start, Return.date <= end)).count()
        completed_count = Return.query.filter(
            and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
        ).count()
        
        ws.write('A1', 'Returns & Refunds Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        
        ws.write('A4', 'Metric', bold_format)
        ws.write('B4', 'Value', bold_format)
        
        ws.write('A5', 'Total Returns')
        ws.write('B5', returns_count)
        ws.write('A6', 'Total Refund Amount')
        ws.write('B6', float(total_refunds), money_format)
        ws.write('A7', 'Completed')
        ws.write('B7', completed_count)
        
        # Returns Details Sheet
        ws2 = workbook.add_worksheet('Returns Details')
        
        returns = Return.query.filter(
            and_(Return.date >= start, Return.date <= end)
        ).order_by(desc(Return.date)).all()
        
        ws2.write('A1', 'Returns Details', bold_format)
        
        ws2.write('A3', 'Return ID', header_format)
        ws2.write('B3', 'Date', header_format)
        ws2.write('C3', 'Customer', header_format)
        ws2.write('D3', 'Amount', header_format)
        ws2.write('E3', 'Status', header_format)
        
        row = 3
        for ret in returns:
            ws2.write(row, 0, ret.id)
            ws2.write(row, 1, to_local_datetime(ret.date).strftime('%Y-%m-%d %H:%M'))
            ws2.write(row, 2, ret.customer)
            ws2.write(row, 3, float(ret.refund_amount), money_format)
            ws2.write(row, 4, ret.status)
            row += 1
    
    elif report_type in ['customer-outstanding', 'customer-purchase-summary', 'customer-ledger']:
        # These customer reports require additional parameters and are handled by their specific routes
        # For now, just return a simple summary
        ws = workbook.add_worksheet('Summary')
        ws.write('A1', f'{report_type.replace("-", " ").title()} Report', bold_format)
        ws.write('A2', f'Period: {start_date} to {end_date}')
        ws.write('A4', 'Note: Please use the specific export button in the report tab for complete details.')
        
    else:
        workbook.close()
        return jsonify({'error': 'Invalid report type'}), 400
    
    # Close workbook and send file
    workbook.close()
    output.seek(0)
    
    filename = f'{report_type}_report_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@reports_bp.route('/api/export/all')
@login_required
def export_all_reports():
    """Export all reports as a single Excel file with multiple sheets."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # Create Excel file in memory
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # Define formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    # ===== Sales Summary Sheet =====
    ws = workbook.add_worksheet('Sales Summary')
    
    total_sales = db.session.query(func.sum(Sale.total)).filter(
        and_(Sale.date >= start, Sale.date <= end)
    ).scalar() or 0
    
    # Get total returns
    total_returns = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    ).scalar() or 0
    
    # Calculate Net Sales
    net_sales = float(total_sales) - float(total_returns)
    
    trans_query = Sale.query.filter(
        and_(Sale.date >= start, Sale.date <= end, Sale.company_id == company_id)
    )
    total_transactions = trans_query.count()
    
    ws.write('A1', 'Sales Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    ws.write('A4', 'Metric', bold_format)
    ws.write('B4', 'Value', bold_format)
    
    ws.write('A5', 'Gross Sales')
    ws.write('B5', float(total_sales), money_format)
    ws.write('A6', 'Total Returns')
    ws.write('B6', float(total_returns), money_format)
    ws.write('A7', 'Net Sales')
    ws.write('B7', float(net_sales), money_format)
    ws.write('A8', 'Total Transactions')
    ws.write('B8', total_transactions)
    ws.write('A9', 'Average Transaction')
    ws.write('B9', float(net_sales) / total_transactions if total_transactions > 0 else 0, money_format)
    
    # ===== Top Products Sheet =====
    ws2 = workbook.add_worksheet('Top Products')
    
    top_products = db.session.query(
        Product.name,
        func.sum(SaleItem.quantity).label('total_quantity'),
        func.sum(SaleItem.quantity * SaleItem.price).label('total_revenue')
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))\
     .group_by(Product.id, Product.name)\
     .order_by(desc('total_revenue')).limit(50).all()
    
    ws2.write('A1', 'Top Selling Products', bold_format)
    
    ws2.write('A3', 'Product Name', header_format)
    ws2.write('B3', 'Quantity Sold', header_format)
    ws2.write('C3', 'Revenue', header_format)
    
    row = 3
    for product in top_products:
        ws2.write(row, 0, product[0])
        ws2.write(row, 1, int(product[1]))
        ws2.write(row, 2, float(product[2]), money_format)
        row += 1
    
    # ===== Payment Methods Sheet =====
    ws3 = workbook.add_worksheet('Payment Methods')
    
    payment_methods = db.session.query(
        Sale.payment,
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))\
     .group_by(Sale.payment).all()
    
    ws3.write('A1', 'Sales by Payment Method', bold_format)
    
    ws3.write('A3', 'Payment Method', header_format)
    ws3.write('B3', 'Transactions', header_format)
    ws3.write('C3', 'Total Amount', header_format)
    
    row = 3
    for method in payment_methods:
        ws3.write(row, 0, method[0])
        ws3.write(row, 1, method[1])
        ws3.write(row, 2, float(method[2]), money_format)
        row += 1
    
    # ===== Inventory Summary Sheet =====
    ws4 = workbook.add_worksheet('Inventory Summary')
    
    products_query = Product.query
    product_filter = get_company_filter(Product)
    if product_filter is not None:
        products_query = products_query.filter(product_filter)
    
    total_products = products_query.count()
    total_value = db.session.query(func.sum(Product.stock * Product.cost_price)).filter(product_filter if product_filter is not None else True).scalar() or 0
    low_stock_count = products_query.filter(Product.stock <= Product.low_stock_threshold).count()
    out_of_stock_count = products_query.filter(Product.stock == 0).count()
    
    ws4.write('A1', 'Inventory Report', bold_format)
    
    ws4.write('A3', 'Metric', bold_format)
    ws4.write('B3', 'Value', bold_format)
    
    ws4.write('A4', 'Total Products')
    ws4.write('B4', total_products)
    ws4.write('A5', 'Total Inventory Value')
    ws4.write('B5', float(total_value), money_format)
    ws4.write('A6', 'Low Stock Items')
    ws4.write('B6', low_stock_count)
    ws4.write('A7', 'Out of Stock')
    ws4.write('B7', out_of_stock_count)
    
    # ===== All Products Sheet =====
    ws5 = workbook.add_worksheet('All Products')
    
    products = Product.query.all()
    
    ws5.write('A1', 'Product Name', header_format)
    ws5.write('B1', 'Category', header_format)
    ws5.write('C1', 'Stock', header_format)
    ws5.write('D1', 'Cost Price', header_format)
    ws5.write('E1', 'Selling Price', header_format)
    ws5.write('F1', 'Stock Value', header_format)
    
    row = 1
    for product in products:
        ws5.write(row, 0, product.name)
        ws5.write(row, 1, product.category or 'N/A')
        ws5.write(row, 2, product.stock)
        ws5.write(row, 3, float(product.cost_price or 0), money_format)
        ws5.write(row, 4, float(product.price), money_format)
        ws5.write(row, 5, float(product.stock * (product.cost_price or 0)), money_format)
        row += 1
    
    # ===== Customer Summary Sheet =====
    ws6 = workbook.add_worksheet('Customer Summary')
    
    total_customers = Customer.query.count()
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    active_customers = Customer.query.filter(
        Customer.last_purchase_date >= thirty_days_ago
    ).count()
    this_month = datetime.utcnow().replace(day=1)
    new_customers = Customer.query.filter(
        Customer.registration_date >= this_month
    ).count()
    
    ws6.write('A1', 'Customer Report', bold_format)
    
    ws6.write('A3', 'Metric', bold_format)
    ws6.write('B3', 'Value', bold_format)
    
    ws6.write('A4', 'Total Customers')
    ws6.write('B4', total_customers)
    ws6.write('A5', 'Active Customers (30 days)')
    ws6.write('B5', active_customers)
    ws6.write('A6', 'New This Month')
    ws6.write('B6', new_customers)
    
    # ===== Top Customers Sheet =====
    ws7 = workbook.add_worksheet('Top Customers')
    
    top_customers = db.session.query(
        Customer.name,
        Customer.total_purchases,
        Customer.loyalty_points
    ).order_by(desc(Customer.total_purchases)).limit(50).all()
    
    ws7.write('A1', 'Top Customers by Purchase Value', bold_format)
    
    ws7.write('A3', 'Customer Name', header_format)
    ws7.write('B3', 'Total Purchases', header_format)
    ws7.write('C3', 'Loyalty Points', header_format)
    
    row = 3
    for customer in top_customers:
        ws7.write(row, 0, customer[0])
        ws7.write(row, 1, float(customer[1]), money_format)
        ws7.write(row, 2, customer[2] or 0)
        row += 1
    
    # ===== Returns Summary Sheet =====
    ws8 = workbook.add_worksheet('Returns Summary')
    
    total_refunds = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    ).scalar() or 0
    
    returns_count = Return.query.filter(
        and_(Return.date >= start, Return.date <= end)
    ).count()
    
    ws8.write('A1', 'Returns & Refunds Report', bold_format)
    ws8.write('A2', f'Period: {start_date} to {end_date}')
    
    ws8.write('A4', 'Metric', bold_format)
    ws8.write('B4', 'Value', bold_format)
    
    ws8.write('A5', 'Total Returns')
    ws8.write('B5', returns_count)
    ws8.write('A6', 'Total Refund Amount')
    ws8.write('B6', float(total_refunds), money_format)
    
    # ===== Returns Details Sheet =====
    ws9 = workbook.add_worksheet('Returns Details')
    
    returns = Return.query.filter(
        and_(Return.date >= start, Return.date <= end)
    ).order_by(desc(Return.date)).limit(100).all()
    
    ws9.write('A1', 'Returns Details', bold_format)
    
    ws9.write('A3', 'Return ID', header_format)
    ws9.write('B3', 'Date', header_format)
    ws9.write('C3', 'Customer', header_format)
    ws9.write('D3', 'Original Sale', header_format)
    ws9.write('E3', 'Reason', header_format)
    ws9.write('F3', 'Amount', header_format)
    ws9.write('G3', 'Status', header_format)
    
    row = 3
    for ret in returns:
        ws9.write(row, 0, ret.id)
        ws9.write(row, 1, ret.date.strftime('%Y-%m-%d %H:%M'))
        ws9.write(row, 2, ret.customer)
        ws9.write(row, 3, ret.original_sale_id)
        ws9.write(row, 4, ret.return_reason)
        ws9.write(row, 5, float(ret.refund_amount), money_format)
        ws9.write(row, 6, ret.status)
        row += 1
    
    # ===== Profit & Loss Sheet =====
    ws10 = workbook.add_worksheet('Profit & Loss')
    
    # Step 1: Gross Sales
    gross_sales = db.session.query(func.sum(Sale.total)).filter(
        and_(Sale.date >= start, Sale.date <= end)
    ).scalar() or 0
    
    # Step 2: Total Returns
    total_returns = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    ).scalar() or 0
    
    # Step 3: Net Sales = Gross Sales - Returns
    net_sales = float(gross_sales) - float(total_returns)
    
    # Step 4: COGS
    cogs = db.session.query(func.sum(SaleItem.quantity * Product.cost_price))\
        .join(SaleItem, Product.id == SaleItem.product_id)\
        .join(Sale, Sale.id == SaleItem.sale_id)\
        .filter(and_(Sale.date >= start, Sale.date <= end)).scalar() or 0
    
    # Step 5: Gross Profit = Net Sales - COGS
    gross_profit = float(net_sales) - float(cogs)
    
    # Step 6: Get actual expenses
    operating_expenses = db.session.query(func.sum(Expense.amount)).filter(
        and_(Expense.date >= start, Expense.date <= end)
    ).scalar() or 0
    
    # Step 7: Net Profit = Gross Profit - Expenses
    net_profit = gross_profit - float(operating_expenses)
    
    ws10.write('A1', 'Profit & Loss Report', bold_format)
    ws10.write('A2', f'Period: {start_date} to {end_date}')
    
    ws10.write('A4', 'Metric', bold_format)
    ws10.write('B4', 'Value', bold_format)
    
    ws10.write('A5', 'Gross Sales')
    ws10.write('B5', float(gross_sales), money_format)
    ws10.write('A6', 'Returns')
    ws10.write('B6', float(total_returns), money_format)
    ws10.write('A7', 'Net Sales')
    ws10.write('B7', float(net_sales), money_format)
    ws10.write('A8', 'Cost of Goods Sold')
    ws10.write('B8', float(cogs), money_format)
    ws10.write('A9', 'Gross Profit')
    ws10.write('B9', gross_profit, money_format)
    ws10.write('A10', 'Operating Expenses')
    ws10.write('B10', float(operating_expenses), money_format)
    ws10.write('A11', 'Net Profit')
    ws10.write('B11', net_profit, money_format)
    
    # Close workbook and send file
    workbook.close()
    output.seek(0)
    
    filename = f'complete_report_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@reports_bp.route('/api/sales-report')
@login_required
@require_permission('can_view_reports')
def get_sales_report():
    """Get detailed sales report with all sale transactions."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    customer_filter = request.args.get('customer', '')

    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Build query
    query = db.session.query(
        Sale,
        User.username,
        func.sum(SaleItem.quantity).label('total_items'),
        func.sum(SaleItem.discount).label('total_discount'),
        func.sum(SaleItem.tax).label('total_tax')
    ).join(User, Sale.user_id == User.id)\
     .outerjoin(SaleItem, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))

    # Apply company filter
    if company_id and hasattr(Sale, 'company_id'):
        query = query.filter(Sale.company_id == company_id)

    # Apply customer filter if provided
    if customer_filter:
        query = query.filter(Sale.customer.ilike(f'%{customer_filter}%'))

    # Group by sale
    query = query.group_by(Sale.id, User.username)

    # Order by date descending
    sales = query.order_by(desc(Sale.date)).all()

    # Calculate totals
    total_sales = sum(float(sale[0].total) for sale in sales)
    total_items = sum(int(sale[2] or 0) for sale in sales)
    total_discount = sum(float(sale[3] or 0) for sale in sales)
    total_tax = sum(float(sale[4] or 0) for sale in sales)

    sales_data = []
    for sale, username, items, discount, tax in sales:
        # Calculate subtotal (total - tax + discount)
        subtotal = float(sale.total) - float(tax or 0) + float(discount or 0)
        
        sales_data.append({
            'id': sale.id,
            'date': sale.date.strftime('%Y-%m-%d'),
            'time': sale.date.strftime('%H:%M:%S'),
            'invoice_no': f'INV-{sale.id:06d}',
            'customer': sale.customer,
            'total_items': int(items or 0),
            'sub_total': round(subtotal, 2),
            'discount': round(float(discount or 0), 2),
            'tax': round(float(tax or 0), 2),
            'grand_total': round(float(sale.total), 2),
            'payment_method': sale.payment,
            'cashier': username,
            'payment': sale.payment
        })

    return jsonify({
        'period': {'start_date': start_date, 'end_date': end_date},
        'sales': sales_data,
        'summary': {
            'total_sales': round(total_sales, 2),
            'total_items': total_items,
            'total_discount': round(total_discount, 2),
            'total_tax': round(total_tax, 2),
            'transaction_count': len(sales_data)
        }
    })


@reports_bp.route('/api/payment-report')
@login_required
@require_permission('can_view_reports')
def get_payment_report():
    """Get payment method breakdown report."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Get totals by payment method
    payment_query = db.session.query(
        Sale.payment,
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))
    
    # Apply company filter
    if company_id and hasattr(Sale, 'company_id'):
        payment_query = payment_query.filter(Sale.company_id == company_id)
    
    payment_totals = payment_query.group_by(Sale.payment).all()

    # Initialize totals
    cash_total = 0
    card_total = 0
    qr_total = 0
    credit_total = 0

    payment_breakdown = {}
    for payment, count, total in payment_totals:
        payment_lower = payment.lower() if payment else ''
        amount = float(total or 0)
        count = int(count or 0)
        
        payment_breakdown[payment] = {
            'count': count,
            'total': amount
        }
        
        # Categorize payments
        if 'cash' in payment_lower:
            cash_total += amount
        elif 'card' in payment_lower:
            card_total += amount
        elif 'qr' in payment_lower or 'payment' in payment_lower:
            qr_total += amount
        elif 'credit' in payment_lower or 'due' in payment_lower:
            credit_total += amount

    # Get daily breakdown
    daily_query = db.session.query(
        func.date(Sale.date).label('date'),
        Sale.payment,
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))
    if company_id and hasattr(Sale, 'company_id'):
        daily_query = daily_query.filter(Sale.company_id == company_id)
    daily_payments = daily_query.group_by(func.date(Sale.date), Sale.payment)\
     .order_by('date').all()

    daily_data = {}
    for date, payment, total in daily_payments:
        date_str = str(date)
        if date_str not in daily_data:
            daily_data[date_str] = {}
        daily_data[date_str][payment] = float(total)

    return jsonify({
        'period': {'start_date': start_date, 'end_date': end_date},
        'totals': {
            'cash_total': round(cash_total, 2),
            'card_total': round(card_total, 2),
            'qr_total': round(qr_total, 2),
            'credit_total': round(credit_total, 2),
            'total_sales': round(cash_total + card_total + qr_total + credit_total, 2)
        },
        'breakdown': payment_breakdown,
        'daily': daily_data
    })


@reports_bp.route('/api/cashier-report')
@login_required
@require_permission('can_view_reports')
def get_cashier_report():
    """Get cashier performance report."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Get sales by cashier - include both cart-level (Sale.discount) and item-level (SaleItem.discount) discounts
    cashier_query = db.session.query(
        User.id,
        User.username,
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total).label('total_sales'),
        func.coalesce(func.sum(SaleItem.discount), 0) + func.coalesce(func.sum(Sale.discount), 0).label('total_discount')
    ).join(Sale, User.id == Sale.user_id)\
     .outerjoin(SaleItem, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))
    
    # Apply company filter
    if company_id and hasattr(Sale, 'company_id'):
        cashier_query = cashier_query.filter(Sale.company_id == company_id)
    
    cashier_sales = cashier_query.group_by(User.id, User.username).all()

    # Get returns processed by cashier
    returns_query = db.session.query(
        User.id,
        func.count(Return.id).label('returns_count'),
        func.sum(Return.refund_amount).label('returns_amount')
    ).join(Return, User.id == Return.user_id)\
     .filter(and_(Return.date >= start, Return.date <= end))
    
    # Apply company filter
    if company_id and hasattr(Return, 'company_id'):
        returns_query = returns_query.filter(Return.company_id == company_id)
    
    cashier_returns = returns_query.group_by(User.id).all()

    returns_dict = {}
    for user_id, count, amount in cashier_returns:
        returns_dict[user_id] = {
            'count': int(count or 0),
            'amount': float(amount or 0)
        }

    cashier_data = []
    for user_id, username, transactions, sales, discount in cashier_sales:
        total_sales = float(sales or 0)
        transaction_count = int(transactions or 0)
        avg_bill = total_sales / transaction_count if transaction_count > 0 else 0
        total_discount = float(discount or 0)
        
        returns_info = returns_dict.get(user_id, {'count': 0, 'amount': 0})

        cashier_data.append({
            'cashier_name': username,
            'total_sales': round(total_sales, 2),
            'transactions': transaction_count,
            'average_bill': round(avg_bill, 2),
            'discount_given': round(total_discount, 2),
            'returns_processed': returns_info['count']
        })

    # Sort by total sales descending
    cashier_data.sort(key=lambda x: x['total_sales'], reverse=True)

    # Calculate totals
    total_sales = sum(c['total_sales'] for c in cashier_data)
    total_transactions = sum(c['transactions'] for c in cashier_data)
    total_discount = sum(c['discount_given'] for c in cashier_data)
    total_returns = sum(c['returns_processed'] for c in cashier_data)

    return jsonify({
        'period': {'start_date': start_date, 'end_date': end_date},
        'cashiers': cashier_data,
        'summary': {
            'total_sales': round(total_sales, 2),
            'total_transactions': total_transactions,
            'average_bill': round(total_sales / total_transactions, 2) if total_transactions > 0 else 0,
            'total_discount_given': round(total_discount, 2),
            'total_returns_processed': total_returns,
            'cashier_count': len(cashier_data)
        }
    })


@reports_bp.route('/api/category-performance')
@login_required
@require_permission('can_view_reports')
def get_category_performance():
    """Get category performance report with quantity sold, revenue, and profit."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Get category performance
    category_query = db.session.query(
        Product.category,
        func.sum(SaleItem.quantity).label('quantity_sold'),
        func.sum(SaleItem.quantity * SaleItem.price).label('revenue'),
        func.sum(SaleItem.quantity * (SaleItem.price - Product.cost_price)).label('profit')
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))
    
    # Apply company filter
    if company_id and hasattr(Sale, 'company_id'):
        category_query = category_query.filter(Sale.company_id == company_id)
    
    category_data = category_query.group_by(Product.category)\
     .order_by(desc('revenue')).all()

    categories = []
    total_quantity = 0
    total_revenue = 0
    total_profit = 0

    for category, quantity, revenue, profit in category_data:
        cat_quantity = float(quantity or 0)
        cat_revenue = float(revenue or 0)
        cat_profit = float(profit or 0)
        
        categories.append({
            'category': category or 'Uncategorized',
            'quantity_sold': round(cat_quantity, 2),
            'revenue': round(cat_revenue, 2),
            'profit': round(cat_profit, 2)
        })
        
        total_quantity += cat_quantity
        total_revenue += cat_revenue
        total_profit += cat_profit

    return jsonify({
        'period': {'start_date': start_date, 'end_date': end_date},
        'categories': categories,
        'summary': {
            'total_quantity_sold': round(total_quantity, 2),
            'total_revenue': round(total_revenue, 2),
            'total_profit': round(total_profit, 2),
            'category_count': len(categories)
        }
    })


@reports_bp.route('/api/return-refund-report')
@login_required
@require_permission('can_view_reports')
def get_return_refund_report():
    """Get detailed return and refund report."""
    company_id = get_company_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)

    # Get returns with items
    returns_query = db.session.query(
        Return,
        User.username
    ).join(User, Return.user_id == User.id)\
     .filter(and_(Return.date >= start, Return.date <= end))
    
    # Apply company filter
    if company_id and hasattr(Return, 'company_id'):
        returns_query = returns_query.filter(Return.company_id == company_id)
    
    returns = returns_query.order_by(desc(Return.date)).all()

    return_data = []
    total_refund = 0

    for return_obj, username in returns:
        # Get return items
        return_items = ReturnItem.query.filter_by(return_id=return_obj.id).all()
        
        items_list = []
        for item in return_items:
            items_list.append({
                'product': item.product.name if item.product else 'Unknown',
                'quantity': float(item.quantity or 0),
                'refund_amount': round(float(item.quantity * item.price), 2)
            })
        
        return_data.append({
            'id': return_obj.id,
            'date': return_obj.date.strftime('%Y-%m-%d'),
            'invoice_no': f'INV-{return_obj.original_sale_id:06d}',
            'customer': return_obj.customer,
            'items': items_list,
            'total_refund': round(float(return_obj.refund_amount), 2),
            'reason': return_obj.return_reason,
            'processed_by': username,
            'status': return_obj.status,
            'refund_method': return_obj.refund_method
        })
        
        total_refund += float(return_obj.refund_amount)

    # Get returns by reason
    returns_by_reason = db.session.query(
        Return.return_reason,
        func.count(Return.id).label('count'),
        func.sum(Return.refund_amount).label('total')
    ).filter(and_(Return.date >= start, Return.date <= end))\
     .group_by(Return.return_reason).all()

    reason_breakdown = []
    for reason, count, total in returns_by_reason:
        reason_breakdown.append({
            'reason': reason or 'Unknown',
            'count': int(count or 0),
            'total': round(float(total or 0), 2)
        })

    return jsonify({
        'period': {'start_date': start_date, 'end_date': end_date},
        'returns': return_data,
        'by_reason': reason_breakdown,
        'summary': {
            'total_returns': len(return_data),
            'total_refund_amount': round(total_refund, 2),
            'completed_count': sum(1 for r in return_data if r['status'] == 'completed'),
            'pending_count': sum(1 for r in return_data if r['status'] == 'pending')
        }
    })


# NOTE: This route is now handled by the generic /api/export/excel/<report_type> route above
# @reports_bp.route('/api/export/excel/sales-detail')
# @login_required
# @require_permission('can_view_reports')
# def export_sales_detail_excel():
    """Export detailed sales report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    # Sales Details Sheet
    ws = workbook.add_worksheet('Sales Details')
    
    ws.write('A1', 'Detailed Sales Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    # Get sales, returns, and calculate net sales
    total_sales = db.session.query(func.sum(Sale.total)).filter(
        and_(Sale.date >= start, Sale.date <= end)
    ).scalar() or 0
    
    total_returns = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    ).scalar() or 0
    
    net_sales = float(total_sales) - float(total_returns)
    
    # Write summary section
    ws.write('A3', 'Summary', bold_format)
    ws.write('A4', 'Gross Sales:')
    ws.write('B4', float(total_sales), money_format)
    ws.write('A5', 'Total Returns:')
    ws.write('B5', float(total_returns), money_format)
    ws.write('A6', 'Net Sales:')
    ws.write('B6', float(net_sales), money_format)
    
    # Headers
    headers = ['Date', 'Time', 'Invoice No', 'Customer', 'Total Items', 'Sub Total', 'Discount', 'Tax', 'Grand Total', 'Payment Method', 'Cashier']
    for col, header in enumerate(headers):
        ws.write(9, col, header, header_format)
    
    # Get all sales with details
    sales_data = db.session.query(
        Sale,
        User.username
    ).join(User, Sale.user_id == User.id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))\
     .order_by(desc(Sale.date)).all()
    
    row = 10
    grand_total_items = 0
    grand_total_subtotal = 0
    grand_total_discount = 0
    grand_total_tax = 0
    grand_total = 0
    
    for sale, username in sales_data:
        # Get sale items for this sale
        sale_items = SaleItem.query.filter_by(sale_id=sale.id).all()
        total_items = sum(item.quantity for item in sale_items)
        # Include both cart-level (Sale.discount) and item-level (SaleItem.discount) discounts
        item_discount = sum(item.discount or 0 for item in sale_items)
        cart_discount = float(sale.discount or 0)
        total_discount = item_discount + cart_discount
        total_tax = sum(item.tax or 0 for item in sale_items)
        subtotal = float(sale.total) - float(total_tax) + float(total_discount)
        
        ws.write(row, 0, sale.date.strftime('%Y-%m-%d'))
        ws.write(row, 1, sale.date.strftime('%H:%M:%S'))
        ws.write(row, 2, f'INV-{sale.id:06d}')
        ws.write(row, 3, sale.customer)
        ws.write(row, 4, int(total_items))
        ws.write(row, 5, round(subtotal, 2), money_format)
        ws.write(row, 6, round(float(total_discount), 2), money_format)
        ws.write(row, 7, round(float(total_tax), 2), money_format)
        ws.write(row, 8, round(float(sale.total), 2), money_format)
        ws.write(row, 9, sale.payment)
        ws.write(row, 10, username)
        
        grand_total_items += total_items
        grand_total_subtotal += subtotal
        grand_total_discount += total_discount
        grand_total_tax += total_tax
        grand_total += float(sale.total)
        row += 1
    
    # Add totals row
    row += 1
    ws.write(row, 0, 'TOTAL', bold_format)
    ws.write(row, 4, grand_total_items)
    ws.write(row, 5, round(grand_total_subtotal, 2), money_format)
    ws.write(row, 6, round(grand_total_discount, 2), money_format)
    ws.write(row, 7, round(grand_total_tax, 2), money_format)
    ws.write(row, 8, round(grand_total, 2), money_format)
    
    # Set column widths
    ws.set_column('A:A', 12)
    ws.set_column('B:B', 10)
    ws.set_column('C:C', 14)
    ws.set_column('D:D', 20)
    ws.set_column('E:E', 12)
    ws.set_column('F:K', 14)
    
    workbook.close()
    output.seek(0)
    
    filename = f'sales_detail_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# NOTE: This route is now handled by the generic /api/export/excel/<report_type> route
# @reports_bp.route('/api/export/excel/payment-detail')
# @login_required
# @require_permission('can_view_reports')
# def export_payment_detail_excel():
    """Export detailed payment report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    # Summary Sheet
    ws = workbook.add_worksheet('Payment Summary')
    
    ws.write('A1', 'Payment Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    # Get totals by payment method
    payment_totals = db.session.query(
        Sale.payment,
        func.count(Sale.id).label('count'),
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))\
     .group_by(Sale.payment).all()
    
    # Calculate totals
    cash_total = 0
    card_total = 0
    qr_total = 0
    credit_total = 0
    
    for payment, count, total in payment_totals:
        payment_lower = payment.lower() if payment else ''
        amount = float(total or 0)
        if 'cash' in payment_lower:
            cash_total += amount
        elif 'card' in payment_lower:
            card_total += amount
        elif 'qr' in payment_lower:
            qr_total += amount
        else:
            credit_total += amount
    
    total_sales = cash_total + card_total + qr_total + credit_total
    
    ws.write('A4', 'Payment Method', header_format)
    ws.write('B4', 'Total Amount', header_format)
    ws.write('C4', 'Percentage', header_format)
    
    ws.write('A5', 'Cash')
    ws.write('B5', cash_total, money_format)
    ws.write('C5', round(cash_total/total_sales*100, 1) if total_sales > 0 else 0)
    
    ws.write('A6', 'Card')
    ws.write('B6', card_total, money_format)
    ws.write('C6', round(card_total/total_sales*100, 1) if total_sales > 0 else 0)
    
    ws.write('A7', 'QR')
    ws.write('B7', qr_total, money_format)
    ws.write('C7', round(qr_total/total_sales*100, 1) if total_sales > 0 else 0)
    
    ws.write('A8', 'Credit')
    ws.write('B8', credit_total, money_format)
    ws.write('C8', round(credit_total/total_sales*100, 1) if total_sales > 0 else 0)
    
    ws.write('A10', 'TOTAL')
    ws.write('B10', total_sales, money_format)
    ws.write('C10', '100%')
    
    # Daily Breakdown Sheet
    ws2 = workbook.add_worksheet('Daily Payment Breakdown')
    
    ws2.write('A1', 'Daily Payment Breakdown', bold_format)
    
    ws2.write('A3', 'Date', header_format)
    ws2.write('B3', 'Payment Method', header_format)
    ws2.write('C3', 'Amount', header_format)
    
    daily_payments = db.session.query(
        func.date(Sale.date).label('date'),
        Sale.payment,
        func.sum(Sale.total).label('total')
    ).filter(and_(Sale.date >= start, Sale.date <= end))\
     .group_by(func.date(Sale.date), Sale.payment)\
     .order_by('date').all()
    
    row = 3
    payment_grand_total = 0
    for date, payment, total in daily_payments:
        ws2.write(row, 0, str(date))
        ws2.write(row, 1, payment)
        ws2.write(row, 2, float(total), money_format)
        payment_grand_total += float(total)
        row += 1
    
    # Add totals row
    row += 1
    ws2.write(row, 0, 'TOTAL', bold_format)
    ws2.write(row, 2, payment_grand_total, money_format)
    
    workbook.close()
    output.seek(0)
    
    filename = f'payment_report_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# NOTE: This route is now handled by the generic /api/export/excel/<report_type> route
# @reports_bp.route('/api/export/excel/cashier-detail')
# @login_required
# @require_permission('can_view_reports')
# def export_cashier_detail_excel():
    """Export detailed cashier report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    # Cashier Performance Sheet
    ws = workbook.add_worksheet('Cashier Performance')
    
    ws.write('A1', 'Cashier Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    ws.write('A4', 'Cashier Name', header_format)
    ws.write('B4', 'Total Sales', header_format)
    ws.write('C4', 'Transactions', header_format)
    ws.write('D4', 'Average Bill', header_format)
    ws.write('E4', 'Discount Given', header_format)
    ws.write('F4', 'Returns Processed', header_format)
    
    # Get sales by cashier
    cashier_sales = db.session.query(
        User.username,
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total).label('total_sales'),
        func.sum(SaleItem.discount).label('total_discount')
    ).join(Sale, User.id == Sale.user_id)\
     .outerjoin(SaleItem, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))\
     .group_by(User.id, User.username).all()
    
    # Get returns by cashier
    cashier_returns = db.session.query(
        User.username,
        func.count(Return.id).label('returns_count')
    ).join(Return, User.id == Return.user_id)\
     .filter(and_(Return.date >= start, Return.date <= end))\
     .group_by(User.id, User.username).all()
    
    returns_dict = {r[0]: r[1] for r in cashier_returns}
    
    row = 4
    total_all_sales = 0
    total_all_transactions = 0
    total_all_discount = 0
    total_all_returns = 0
    
    for username, transactions, sales, discount in cashier_sales:
        total_sales = float(sales or 0)
        transaction_count = int(transactions or 0)
        avg_bill = total_sales / transaction_count if transaction_count > 0 else 0
        total_discount = float(discount or 0)
        returns_count = returns_dict.get(username, 0)
        
        ws.write(row, 0, username)
        ws.write(row, 1, total_sales, money_format)
        ws.write(row, 2, transaction_count)
        ws.write(row, 3, avg_bill, money_format)
        ws.write(row, 4, total_discount, money_format)
        ws.write(row, 5, returns_count)
        
        total_all_sales += total_sales
        total_all_transactions += transaction_count
        total_all_discount += total_discount
        total_all_returns += returns_count
        row += 1
    
    # Totals row
    row += 1
    ws.write(row, 0, 'TOTAL', bold_format)
    ws.write(row, 1, total_all_sales, money_format)
    ws.write(row, 2, total_all_transactions)
    ws.write(row, 3, total_all_sales/total_all_transactions if total_all_transactions > 0 else 0, money_format)
    ws.write(row, 4, total_all_discount, money_format)
    ws.write(row, 5, total_all_returns)
    
    ws.set_column('A:A', 20)
    ws.set_column('B:F', 16)
    
    workbook.close()
    output.seek(0)
    
    filename = f'cashier_report_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# NOTE: This route is now handled by the generic /api/export/excel/<report_type> route
# @reports_bp.route('/api/export/excel/category-detail')
# @login_required
# @require_permission('can_view_reports')
# def export_category_detail_excel():
    """Export detailed category performance report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    # Category Performance Sheet
    ws = workbook.add_worksheet('Category Performance')
    
    ws.write('A1', 'Category Performance Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    ws.write('A4', 'Category', header_format)
    ws.write('B4', 'Quantity Sold', header_format)
    ws.write('C4', 'Revenue', header_format)
    ws.write('D4', 'Cost', header_format)
    ws.write('E4', 'Profit', header_format)
    ws.write('F4', 'Margin %', header_format)
    
    # Get category performance
    category_data = db.session.query(
        Product.category,
        func.sum(SaleItem.quantity).label('quantity_sold'),
        func.sum(SaleItem.quantity * SaleItem.price).label('revenue'),
        func.sum(SaleItem.quantity * Product.cost_price).label('cost')
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(and_(Sale.date >= start, Sale.date <= end))\
     .group_by(Product.category)\
     .order_by(desc('revenue')).all()
    
    row = 4
    total_quantity = 0
    total_revenue = 0
    total_cost = 0
    
    for category, quantity, revenue, cost in category_data:
        qty = float(quantity or 0)
        rev = float(revenue or 0)
        cst = float(cost or 0)
        profit = rev - cst
        margin = (profit / rev * 100) if rev > 0 else 0
        
        ws.write(row, 0, category or 'Uncategorized')
        ws.write(row, 1, round(qty, 2))
        ws.write(row, 2, rev, money_format)
        ws.write(row, 3, cst, money_format)
        ws.write(row, 4, profit, money_format)
        ws.write(row, 5, round(margin, 1))
        
        total_quantity += qty
        total_revenue += rev
        total_cost += cst
        row += 1
    
    # Totals
    total_profit = total_revenue - total_cost
    total_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    row += 1
    ws.write(row, 0, 'TOTAL', bold_format)
    ws.write(row, 1, round(total_quantity, 2))
    ws.write(row, 2, total_revenue, money_format)
    ws.write(row, 3, total_cost, money_format)
    ws.write(row, 4, total_profit, money_format)
    ws.write(row, 5, round(total_margin, 1))
    
    ws.set_column('A:A', 20)
    ws.set_column('B:F', 16)
    
    workbook.close()
    output.seek(0)
    
    filename = f'category_performance_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# NOTE: This route is now handled by the generic /api/export/excel/<report_type> route
# @reports_bp.route('/api/export/excel/return-detail')
# @login_required
# @require_permission('can_view_reports')
# def export_return_detail_excel():
    """Export detailed return & refund report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    # Returns Summary Sheet
    ws = workbook.add_worksheet('Returns Summary')
    
    ws.write('A1', 'Return & Refund Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    # Get return stats
    total_returns = Return.query.filter(
        and_(Return.date >= start, Return.date <= end)
    ).count()
    
    total_refund = db.session.query(func.sum(Return.refund_amount)).filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    ).scalar() or 0
    
    completed_count = Return.query.filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'completed')
    ).count()
    
    pending_count = Return.query.filter(
        and_(Return.date >= start, Return.date <= end, Return.status == 'pending')
    ).count()
    
    ws.write('A4', 'Metric', header_format)
    ws.write('B4', 'Value', header_format)
    
    ws.write('A5', 'Total Returns')
    ws.write('B5', total_returns)
    ws.write('A6', 'Total Refund Amount')
    ws.write('B6', float(total_refund), money_format)
    ws.write('A7', 'Completed')
    ws.write('B7', completed_count)
    ws.write('A8', 'Pending')
    ws.write('B8', pending_count)
    
    # Returns Details Sheet
    ws2 = workbook.add_worksheet('Returns Details')
    
    ws2.write('A1', 'Returns Details', bold_format)
    
    ws2.write('A3', 'Date', header_format)
    ws2.write('B3', 'Invoice No', header_format)
    ws2.write('C3', 'Customer', header_format)
    ws2.write('D3', 'Product', header_format)
    ws2.write('E3', 'Qty Returned', header_format)
    ws2.write('F3', 'Refund Amount', header_format)
    ws2.write('G3', 'Reason', header_format)
    ws2.write('H3', 'Processed By', header_format)
    ws2.write('I3', 'Status', header_format)
    
    # Get returns with items
    returns = db.session.query(
        Return,
        User.username
    ).join(User, Return.user_id == User.id)\
     .filter(and_(Return.date >= start, Return.date <= end))\
     .order_by(desc(Return.date)).all()
    
    row = 3
    for return_obj, username in returns:
        return_items = ReturnItem.query.filter_by(return_id=return_obj.id).all()
        
        for idx, item in enumerate(return_items):
            ws2.write(row, 0, return_obj.date.strftime('%Y-%m-%d'))
            ws2.write(row, 1, f'INV-{return_obj.original_sale_id:06d}')
            ws2.write(row, 2, return_obj.customer)
            ws2.write(row, 3, item.product.name if item.product else 'Unknown')
            ws2.write(row, 4, float(item.quantity or 0))
            ws2.write(row, 5, float(item.quantity * item.price), money_format)
            ws2.write(row, 6, item.reason or return_obj.return_reason)
            ws2.write(row, 7, username)
            ws2.write(row, 8, return_obj.status)
            row += 1
        
        # If no items, show at least the return
        if not return_items:
            ws2.write(row, 0, return_obj.date.strftime('%Y-%m-%d'))
            ws2.write(row, 1, f'INV-{return_obj.original_sale_id:06d}')
            ws2.write(row, 2, return_obj.customer)
            ws2.write(row, 3, '')
            ws2.write(row, 4, 0)
            ws2.write(row, 5, float(return_obj.refund_amount), money_format)
            ws2.write(row, 6, return_obj.return_reason)
            ws2.write(row, 7, username)
            ws2.write(row, 8, return_obj.status)
            row += 1
    
    ws2.set_column('A:A', 12)
    ws2.set_column('B:B', 14)
    ws2.set_column('C:C', 18)
    ws2.set_column('D:D', 20)
    ws2.set_column('E:I', 14)
    
    # By Reason Sheet
    ws3 = workbook.add_worksheet('By Reason')
    
    ws3.write('A1', 'Returns by Reason', bold_format)
    
    ws3.write('A3', 'Reason', header_format)
    ws3.write('B3', 'Count', header_format)
    ws3.write('C3', 'Total Amount', header_format)
    
    returns_by_reason = db.session.query(
        Return.return_reason,
        func.count(Return.id).label('count'),
        func.sum(Return.refund_amount).label('total')
    ).filter(and_(Return.date >= start, Return.date <= end))\
     .group_by(Return.return_reason).all()
    
    row = 3
    returns_total_count = 0
    returns_total_amount = 0
    for reason, count, total in returns_by_reason:
        ws3.write(row, 0, reason or 'Unknown')
        ws3.write(row, 1, int(count or 0))
        ws3.write(row, 2, float(total or 0), money_format)
        returns_total_count += int(count or 0)
        returns_total_amount += float(total or 0)
        row += 1
    
    # Add totals row
    row += 1
    ws3.write(row, 0, 'TOTAL', bold_format)
    ws3.write(row, 1, returns_total_count)
    ws3.write(row, 2, returns_total_amount, money_format)
    
    workbook.close()
    output.seek(0)
    
    filename = f'return_refund_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ============= Customer Credit Reports =============

@reports_bp.route('/api/customer-outstanding-report')
@login_required
@require_permission('can_view_reports')
def get_customer_outstanding_report():
    """Get customer outstanding report - all customers with their outstanding balances."""
    company_id = get_company_id()
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Default to all time if no dates provided
    if not start_date or not end_date:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Get all active customers
    customer_query = Customer.query.filter(Customer.is_active == True)
    if company_id and hasattr(Customer, 'company_id'):
        customer_query = customer_query.filter(Customer.company_id == company_id)
    customers = customer_query.all()
    
    # Get credit days setting
    from app.models import Setting
    default_credit_days = 30
    credit_days_setting = Setting.query.filter_by(
        setting_category='credit',
        setting_key='default_credit_days'
    ).first()
    if credit_days_setting:
        default_credit_days = int(credit_days_setting.setting_value)
    
    now = datetime.utcnow()
    
    customer_list = []
    total_outstanding = 0
    total_0_30 = 0
    total_30_60 = 0
    total_60_90 = 0
    total_90_plus = 0
    customer_count_with_outstanding = 0
    
    for customer in customers:
        # Get credit sales for this customer - include all sales with balance > 0 (no date restriction for outstanding)
        credit_query = Sale.query.filter(
            Sale.customer == customer.name,
            Sale.balance > 0
        )
        if company_id and hasattr(Sale, 'company_id'):
            credit_query = credit_query.filter(Sale.company_id == company_id)
        credit_sales = credit_query.all()
        
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
        
        total_for_customer = outstanding_0_30 + outstanding_30_60 + outstanding_60_90 + outstanding_90_plus
        
        if total_for_customer > 0:
            customer_credit_days = customer.credit_days if customer.credit_days and customer.credit_days > 0 else default_credit_days
            
            # Calculate if overdue
            has_overdue = outstanding_90_plus > 0
            
            customer_list.append({
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'email': customer.email,
                'credit_limit': customer.credit_limit,
                'credit_days': customer_credit_days,
                'outstanding_0_30': outstanding_0_30,
                'outstanding_30_60': outstanding_30_60,
                'outstanding_60_90': outstanding_60_90,
                'outstanding_90_plus': outstanding_90_plus,
                'total_outstanding': total_for_customer,
                'has_overdue': has_overdue,
                'supply_stopped': customer.supply_stopped
            })
            
            # Only count customers with outstanding
            customer_count_with_outstanding += 1
        
        total_outstanding += total_for_customer
        total_0_30 += outstanding_0_30
        total_30_60 += outstanding_30_60
        total_60_90 += outstanding_60_90
        total_90_plus += outstanding_90_plus
    
    # Sort by total outstanding descending
    customer_list.sort(key=lambda x: x['total_outstanding'], reverse=True)
    
    return jsonify({
        'period': {'start_date': start_date_str, 'end_date': end_date_str},
        'customers': customer_list,
        'summary': {
            'total_customers': customer_count_with_outstanding,
            'total_outstanding': total_outstanding,
            'total_0_30': total_0_30,
            'total_30_60': total_30_60,
            'total_60_90': total_60_90,
            'total_90_plus': total_90_plus
        }
    })


@reports_bp.route('/api/customer-purchase-summary')
@login_required
@require_permission('can_view_reports')
def get_customer_purchase_summary_report():
    """Get customer purchase summary report - total purchases per customer."""
    company_id = get_company_id()
    # Get date range from request
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
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
    
    # Get purchase summary by customer
    purchase_query = db.session.query(
        Sale.customer,
        func.count(Sale.id).label('transaction_count'),
        func.sum(Sale.total).label('total_purchases'),
        func.sum(Sale.balance).label('total_balance')
    ).filter(
        and_(
            Sale.date >= start_date,
            Sale.date <= end_date,
            Sale.customer != 'Walk-in Customer'
        )
    )
    if company_id and hasattr(Sale, 'company_id'):
        purchase_query = purchase_query.filter(Sale.company_id == company_id)
    customer_purchases = purchase_query.group_by(Sale.customer).order_by(desc('total_purchases')).all()
    
    customer_list = []
    total_purchases = 0
    total_transactions = 0
    
    for customer_name, transactions, purchases, balance in customer_purchases:
        if customer_name and customer_name != 'Walk-in Customer':
            purchases_value = float(purchases or 0)
            customer_list.append({
                'name': customer_name,
                'transaction_count': transactions,
                'total_purchases': purchases_value,
                'outstanding_balance': float(balance or 0)
            })
            total_purchases += purchases_value
            total_transactions += transactions
    
    # Sort by total purchases descending
    customer_list.sort(key=lambda x: x['total_purchases'], reverse=True)
    
    return jsonify({
        'period': {'start_date': start_date_str, 'end_date': end_date_str},
        'customers': customer_list,
        'summary': {
            'total_customers': len(customer_list),
            'total_transactions': total_transactions,
            'total_purchases': total_purchases
        }
    })


@reports_bp.route('/api/customer-ledger-report')
@login_required
@require_permission('can_view_reports')
def get_customer_ledger_report():
    """Get customer ledger statement - detailed transactions for a specific customer."""
    company_id = get_company_id()
    customer_id = request.args.get('customer_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not customer_id:
        return jsonify({'error': 'Customer ID is required'}), 400
    
    # Get customer with company verification
    company_id = get_company_id()
    customer_query = Customer.query.filter_by(id=customer_id)
    if company_id and hasattr(Customer, 'company_id'):
        customer_query = customer_query.filter(Customer.company_id == company_id)
    customer = customer_query.first()
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
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
    
    # Get sales for this customer
    sales_query = Sale.query.filter(
        Sale.customer == customer.name,
        Sale.date >= start_date,
        Sale.date <= end_date
    )
    if company_id and hasattr(Sale, 'company_id'):
        sales_query = sales_query.filter(Sale.company_id == company_id)
    sales = sales_query.order_by(Sale.date.desc()).all()
    
    # Get returns for this customer
    returns_query = Return.query.filter(
        Return.customer == customer.name,
        Return.date >= start_date,
        Return.date <= end_date
    )
    if company_id and hasattr(Return, 'company_id'):
        returns_query = returns_query.filter(Return.company_id == company_id)
    returns = returns_query.order_by(Return.date.desc()).all()
    
    # Build ledger entries
    ledger_entries = []
    
    for sale in sales:
        local_dt = to_local_datetime(sale.date)
        entry = {
            'date': local_dt.strftime('%Y-%m-%d'),
            'time': local_dt.strftime('%H:%M:%S'),
            'type': 'Sale',
            'reference': f'INV-{sale.id:06d}',
            'debit': float(sale.total),
            'credit': 0,
            'balance': float(getattr(sale, 'balance', 0)),
            'payment_method': sale.payment
        }
        ledger_entries.append(entry)
    
    for return_obj in returns:
        local_dt = to_local_datetime(return_obj.date)
        entry = {
            'date': local_dt.strftime('%Y-%m-%d'),
            'time': local_dt.strftime('%H:%M:%S'),
            'type': 'Return',
            'reference': f'RET-{return_obj.id:06d}',
            'debit': 0,
            'credit': float(return_obj.refund_amount),
            'balance': 0,
            'payment_method': return_obj.refund_method
        }
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
            'current_balance': customer.current_balance
        },
        'period': {'start_date': start_date_str, 'end_date': end_date_str},
        'ledger': ledger_entries,
        'summary': {
            'total_sales': total_debit,
            'total_returns': total_credit,
            'closing_balance': customer.current_balance
        }
    })


@reports_bp.route('/api/export/excel/customer-purchase-summary')
@login_required
@require_permission('can_view_reports')
def export_customer_purchase_summary_excel():
    """Export customer purchase summary report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    ws = workbook.add_worksheet('Customer Purchase Summary')
    
    ws.write('A1', 'Customer Purchase Summary Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    ws.write('A4', 'Customer Name', header_format)
    ws.write('B4', 'Transaction Count', header_format)
    ws.write('C4', 'Total Purchases', header_format)
    ws.write('D4', 'Outstanding Balance', header_format)
    
    # Get purchase summary by customer
    customer_purchases = db.session.query(
        Sale.customer,
        func.count(Sale.id).label('transaction_count'),
        func.sum(Sale.total).label('total_purchases'),
        func.sum(Sale.balance).label('total_balance')
    ).filter(
        and_(
            Sale.date >= start,
            Sale.date <= end,
            Sale.customer != 'Walk-in Customer'
        )
    ).group_by(Sale.customer).order_by(desc('total_purchases')).all()
    
    row = 4
    total_purchases = 0
    total_transactions = 0
    total_balance = 0
    
    for customer_name, transactions, purchases, balance in customer_purchases:
        if customer_name and customer_name != 'Walk-in Customer':
            purchases_value = float(purchases or 0)
            balance_value = float(balance or 0)
            
            ws.write(row, 0, customer_name)
            ws.write(row, 1, int(transactions or 0))
            ws.write(row, 2, purchases_value, money_format)
            ws.write(row, 3, balance_value, money_format)
            
            total_purchases += purchases_value
            total_transactions += int(transactions or 0)
            total_balance += balance_value
            row += 1
    
    # Add totals row
    row += 1
    ws.write(row, 0, 'TOTAL', bold_format)
    ws.write(row, 1, total_transactions)
    ws.write(row, 2, total_purchases, money_format)
    ws.write(row, 3, total_balance, money_format)
    
    ws.set_column('A:A', 25)
    ws.set_column('B:D', 18)
    
    workbook.close()
    output.seek(0)
    
    filename = f'customer_purchase_summary_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@reports_bp.route('/api/export/excel/customer-outstanding')
@login_required
@require_permission('can_view_reports')
def export_customer_outstanding_excel():
    """Export customer outstanding report as Excel file."""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    ws = workbook.add_worksheet('Customer Outstanding')
    
    ws.write('A1', 'Customer Outstanding Report', bold_format)
    ws.write('A2', f'Period: {start_date} to {end_date}')
    
    ws.write('A4', 'Customer Name', header_format)
    ws.write('B4', 'Phone', header_format)
    ws.write('C4', 'Credit Limit', header_format)
    ws.write('D4', '0-30 Days', header_format)
    ws.write('E4', '30-60 Days', header_format)
    ws.write('F4', '60-90 Days', header_format)
    ws.write('G4', '90+ Days', header_format)
    ws.write('H4', 'Total Outstanding', header_format)
    ws.write('I4', 'Status', header_format)
    
    # Get all active customers
    customers = Customer.query.filter(Customer.is_active == True).all()
    now = datetime.utcnow()
    
    row = 4
    total_0_30 = 0
    total_30_60 = 0
    total_60_90 = 0
    total_90_plus = 0
    total_outstanding = 0
    customer_count = 0
    
    for customer in customers:
        # Get credit sales for this customer - no date restriction (show all outstanding)
        credit_sales = Sale.query.filter(
            Sale.customer == customer.name,
            Sale.balance > 0
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
        
        total_for_customer = outstanding_0_30 + outstanding_30_60 + outstanding_60_90 + outstanding_90_plus
        
        if total_for_customer > 0:
            status = 'Overdue' if outstanding_90_plus > 0 else 'Active'
            if customer.supply_stopped:
                status = 'Supply Stopped'
            
            ws.write(row, 0, customer.name)
            ws.write(row, 1, customer.phone or '')
            ws.write(row, 2, float(customer.credit_limit or 0), money_format)
            ws.write(row, 3, outstanding_0_30, money_format)
            ws.write(row, 4, outstanding_30_60, money_format)
            ws.write(row, 5, outstanding_60_90, money_format)
            ws.write(row, 6, outstanding_90_plus, money_format)
            ws.write(row, 7, total_for_customer, money_format)
            ws.write(row, 8, status)
            
            total_0_30 += outstanding_0_30
            total_30_60 += outstanding_30_60
            total_60_90 += outstanding_60_90
            total_90_plus += outstanding_90_plus
            total_outstanding += total_for_customer
            customer_count += 1
            row += 1
    
    # Add totals row
    row += 1
    ws.write(row, 0, 'TOTAL', bold_format)
    ws.write(row, 2, '')
    ws.write(row, 3, total_0_30, money_format)
    ws.write(row, 4, total_30_60, money_format)
    ws.write(row, 5, total_60_90, money_format)
    ws.write(row, 6, total_90_plus, money_format)
    ws.write(row, 7, total_outstanding, money_format)
    
    ws.set_column('A:A', 25)
    ws.set_column('B:B', 15)
    ws.set_column('C:I', 14)
    
    workbook.close()
    output.seek(0)
    
    filename = f'customer_outstanding_{start_date}_to_{end_date}.xlsx'
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@reports_bp.route('/api/export/excel/customer-ledger')
@login_required
@require_permission('can_view_reports')
def export_customer_ledger_excel():
    """Export customer ledger statement as Excel file."""
    customer_id = request.args.get('customer_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not customer_id:
        return jsonify({'error': 'Customer ID is required'}), 400
    
    # Get customer with company verification
    company_id = get_company_id()
    customer_query = Customer.query.filter_by(id=int(customer_id))
    if company_id and hasattr(Customer, 'company_id'):
        customer_query = customer_query.filter(Customer.company_id == company_id)
    customer = customer_query.first()
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    if not start_date or not end_date:
        today = datetime.utcnow()
        start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4472C4',
        'font_color': 'white',
        'border': 1
    })
    money_format = workbook.add_format({'num_format': 'Rs#,##0.00'})
    bold_format = workbook.add_format({'bold': True})
    
    ws = workbook.add_worksheet('Customer Ledger')
    
    # Customer Info
    ws.write('A1', 'Customer Ledger Statement', bold_format)
    ws.write('A2', f'Customer: {customer.name}')
    ws.write('A3', f'Period: {start_date} to {end_date}')
    ws.write('A4', f'Credit Limit: Rs {float(customer.credit_limit or 0):.2f}')
    ws.write('A5', f'Current Balance: Rs {float(customer.current_balance or 0):.2f}')
    
    # Headers
    ws.write('A7', 'Date', header_format)
    ws.write('B7', 'Time', header_format)
    ws.write('C7', 'Type', header_format)
    ws.write('D7', 'Reference', header_format)
    ws.write('E7', 'Debit', header_format)
    ws.write('F7', 'Credit', header_format)
    ws.write('G7', 'Balance', header_format)
    ws.write('H7', 'Payment Method', header_format)
    
    # Get sales
    sales = Sale.query.filter(
        Sale.customer == customer.name,
        Sale.date >= start,
        Sale.date <= end
    ).order_by(Sale.date.desc()).all()
    
    # Get returns
    returns = Return.query.filter(
        Return.customer == customer.name,
        Return.date >= start,
        Return.date <= end
    ).order_by(Return.date.desc()).all()
    
    # Build entries
    entries = []
    for sale in sales:
        entries.append({
            'date': sale.date,
            'type': 'Sale',
            'reference': f'INV-{sale.id:06d}',
            'debit': float(sale.total),
            'credit': 0,
            'balance': float(sale.balance),
            'payment': sale.payment
        })
    
    for return_obj in returns:
        entries.append({
            'date': return_obj.date,
            'type': 'Return',
            'reference': f'RET-{return_obj.id:06d}',
            'debit': 0,
            'credit': float(return_obj.refund_amount),
            'balance': 0,
            'payment': return_obj.refund_method
        })
    
    # Sort by date
    entries.sort(key=lambda x: x['date'], reverse=True)
    
    row = 7
    total_debit = 0
    total_credit = 0
    
    for entry in entries:
        local_dt = to_local_datetime(entry['date'])
        ws.write(row, 0, local_dt.strftime('%Y-%m-%d'))
        ws.write(row, 1, local_dt.strftime('%H:%M:%S'))
        ws.write(row, 2, entry['type'])
        ws.write(row, 3, entry['reference'])
        ws.write(row, 4, entry['debit'], money_format)
        ws.write(row, 5, entry['credit'], money_format)
        ws.write(row, 6, entry['balance'], money_format)
        ws.write(row, 7, entry['payment'])
        
        total_debit += entry['debit']
        total_credit += entry['credit']
        row += 1
    
    # Totals
    row += 1
    ws.write(row, 0, 'TOTAL', bold_format)
    ws.write(row, 4, total_debit, money_format)
    ws.write(row, 5, total_credit, money_format)
    
    ws.set_column('A:A', 12)
    ws.set_column('B:B', 10)
    ws.set_column('C:C', 10)
    ws.set_column('D:D', 14)
    ws.set_column('E:H', 14)
    
    workbook.close()
    output.seek(0)
    
    filename = f'customer_ledger_{customer.name}_{start_date}_to_{end_date}.xlsx'
    
    # Clean filename
    filename = filename.replace(' ', '_')
    
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
