from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.models import db, Sale, Product, Customer, SaleItem, Purchase, Return
from app.utils.security import get_company_id
from sqlalchemy import func, desc, or_
from datetime import datetime, timedelta
import calendar

main_bp = Blueprint('main', __name__, template_folder='../../templates')

@main_bp.route('/health')
def health_check():
    """Health check endpoint for Docker health checks."""
    return jsonify({'status': 'healthy'}), 200

@main_bp.route('/')
@main_bp.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard page."""
    company_id = get_company_id()
    
    # Get today's sales
    today = datetime.utcnow().date()
    today_sales = Sale.query.filter(
        func.date(Sale.date) == today,
        Sale.company_id == company_id
    ).all()
    today_total = sum(sale.total for sale in today_sales)

    # Get this week's sales
    week_start = today - timedelta(days=today.weekday())
    week_sales = Sale.query.filter(
        func.date(Sale.date) >= week_start,
        Sale.company_id == company_id
    ).all()
    week_total = sum(sale.total for sale in week_sales)

    # Get this month's sales
    month_start = today.replace(day=1)
    month_sales = Sale.query.filter(
        func.date(Sale.date) >= month_start,
        Sale.company_id == company_id
    ).all()
    month_total = sum(sale.total for sale in month_sales)

    # Get today's returns (completed)
    today_returns = Return.query.filter(
        func.date(Return.date) == today,
        Return.status == 'completed',
        Return.company_id == company_id
    ).all()
    today_returns_total = sum(r.refund_amount for r in today_returns)

    # Get this month's returns (completed)
    month_returns = Return.query.filter(
        func.date(Return.date) >= month_start,
        Return.status == 'completed',
        Return.company_id == company_id
    ).all()
    month_returns_total = sum(r.refund_amount for r in month_returns)

    # Calculate Net Sales (Gross Sales - Returns)
    today_net_sales = today_total - today_returns_total
    month_net_sales = month_total - month_returns_total

    # Get total orders this month
    month_orders_count = len(month_sales)

    # Calculate profit this month
    # Get sale items for this month's sales
    month_sale_ids = [sale.id for sale in month_sales]
    month_sale_items = SaleItem.query.filter(SaleItem.sale_id.in_(month_sale_ids)).all() if month_sale_ids else []
    # Profit = sum((selling_price - cost_price) * quantity)
    month_profit = sum((item.price - (item.product.cost_price if item.product else 0)) * item.quantity for item in month_sale_items)

    # Get low stock products
    low_stock_products = Product.query.filter(
        Product.stock <= Product.low_stock_threshold,
        Product.company_id == company_id
    ).all()

    # Get all products count
    products_count = Product.query.filter(
        Product.company_id == company_id
    ).count()

    # Get recent sales
    recent_sales = Sale.query.filter(
        Sale.company_id == company_id
    ).order_by(desc(Sale.date)).limit(10).all()

    # Get top customers
    top_customers = db.session.query(
        Sale.customer,
        func.sum(Sale.total).label('total_spent'),
        func.count(Sale.id).label('total_orders')
    ).filter(
        Sale.company_id == company_id
    ).group_by(Sale.customer).order_by(desc('total_spent')).limit(5).all()

    # Get sales data for chart (last 7 days)
    chart_labels = []
    chart_data = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_sales = Sale.query.filter(
            func.date(Sale.date) == day,
            Sale.company_id == company_id
        ).all()
        day_total = sum(sale.total for sale in day_sales)
        chart_labels.append(day.strftime('%d/%m'))
        chart_data.append(day_total)

    return render_template('main/dashboard.html',
                         today_total=today_total,
                         today_net_sales=today_net_sales,
                         today_returns_total=today_returns_total,
                         week_total=week_total,
                         month_total=month_total,
                         month_net_sales=month_net_sales,
                         month_returns_total=month_returns_total,
                         today_sales_count=len(today_sales),
                         week_sales_count=len(week_sales),
                         month_orders_count=month_orders_count,
                         month_profit=month_profit,
                         low_stock_count=len(low_stock_products),
                         products_count=products_count,
                         recent_sales=recent_sales,
                         top_customers=top_customers,
                         low_stock_products=low_stock_products,
                         chart_labels=chart_labels,
                         chart_data=chart_data)

@main_bp.route('/api/sales-chart-data')
@login_required
def get_sales_chart_data():
    """API endpoint to get sales data for different time periods and metrics."""
    try:
        company_id = get_company_id()
        period = request.args.get('period', 'week')  # day, week, month, year
        metric = request.args.get('metric', 'total')  # total, net, count, profit
        
        today = datetime.utcnow().date()
        labels = []
        data = []
        
        if period == 'day':
            # Hourly data for today
            today_start = datetime.combine(today, datetime.min.time())
            today_end = datetime.combine(today, datetime.max.time())
            
            sales = Sale.query.filter(
                Sale.date >= today_start,
                Sale.date <= today_end,
                Sale.company_id == company_id
            ).all()
            
            for hour in range(24):
                key = f"{hour:02d}:00"
                labels.append(key)
                hour_sales = [s for s in sales if s.date.hour == hour]
                
                if metric == 'total':
                    data.append(sum(s.total for s in hour_sales))
                elif metric == 'net':
                    sale_ids = [s.id for s in hour_sales]
                    returns = Return.query.filter(
                        Return.original_sale_id.in_(sale_ids),
                        Return.status == 'completed',
                        Return.company_id == company_id
                    ).all() if sale_ids else []
                    gross = sum(s.total for s in hour_sales)
                    refunds = sum(r.refund_amount for r in returns)
                    data.append(max(0, gross - refunds))
                elif metric == 'count':
                    data.append(len(hour_sales))
                elif metric == 'profit':
                    sale_ids = [s.id for s in hour_sales]
                    items = SaleItem.query.filter(SaleItem.sale_id.in_(sale_ids)).all() if sale_ids else []
                    profit = sum(((item.price - (item.product.cost_price or 0)) * item.quantity) 
                                 if item.product else 0 for item in items)
                    data.append(profit)
        
        elif period == 'week':
            # Daily data for last 7 days
            for i in range(6, -1, -1):
                day = today - timedelta(days=i)
                labels.append(day.strftime('%a'))
                
                day_sales = Sale.query.filter(
                    func.date(Sale.date) == day,
                    Sale.company_id == company_id
                ).all()
                
                if metric == 'total':
                    data.append(sum(s.total for s in day_sales))
                elif metric == 'net':
                    sale_ids = [s.id for s in day_sales]
                    returns = Return.query.filter(
                        Return.original_sale_id.in_(sale_ids),
                        Return.status == 'completed',
                        Return.company_id == company_id
                    ).all() if sale_ids else []
                    gross = sum(s.total for s in day_sales)
                    refunds = sum(r.refund_amount for r in returns)
                    data.append(max(0, gross - refunds))
                elif metric == 'count':
                    data.append(len(day_sales))
                elif metric == 'profit':
                    sale_ids = [s.id for s in day_sales]
                    items = SaleItem.query.filter(SaleItem.sale_id.in_(sale_ids)).all() if sale_ids else []
                    profit = sum(((item.price - (item.product.cost_price or 0)) * item.quantity)
                                 if item.product else 0 for item in items)
                    data.append(profit)
        
        elif period == 'month':
            # Weekly data for current month
            month_start = today.replace(day=1)
            current_date = month_start
            week_num = 0
            
            while current_date.month == today.month and current_date <= today:
                week_end = min(current_date + timedelta(days=6), today)
                labels.append(f"Week {week_num + 1}")
                
                week_sales = Sale.query.filter(
                    func.date(Sale.date) >= current_date,
                    func.date(Sale.date) <= week_end,
                    Sale.company_id == company_id
                ).all()
                
                if metric == 'total':
                    data.append(sum(s.total for s in week_sales))
                elif metric == 'net':
                    sale_ids = [s.id for s in week_sales]
                    returns = Return.query.filter(
                        Return.original_sale_id.in_(sale_ids),
                        Return.status == 'completed',
                        Return.company_id == company_id
                    ).all() if sale_ids else []
                    gross = sum(s.total for s in week_sales)
                    refunds = sum(r.refund_amount for r in returns)
                    data.append(max(0, gross - refunds))
                elif metric == 'count':
                    data.append(len(week_sales))
                elif metric == 'profit':
                    sale_ids = [s.id for s in week_sales]
                    items = SaleItem.query.filter(SaleItem.sale_id.in_(sale_ids)).all() if sale_ids else []
                    profit = sum(((item.price - (item.product.cost_price or 0)) * item.quantity)
                                 if item.product else 0 for item in items)
                    data.append(profit)
                
                current_date = week_end + timedelta(days=1)
                week_num += 1
        
        elif period == 'year':
            # Monthly data for last 12 months
            for i in range(11, -1, -1):
                month_date = today - timedelta(days=30*i)
                labels.append(month_date.strftime('%b'))
                
                month_start = month_date.replace(day=1)
                if month_date.month == 12:
                    month_end = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
                
                month_sales = Sale.query.filter(
                    func.date(Sale.date) >= month_start,
                    func.date(Sale.date) <= month_end,
                    Sale.company_id == company_id
                ).all()
                
                if metric == 'total':
                    data.append(sum(s.total for s in month_sales))
                elif metric == 'net':
                    sale_ids = [s.id for s in month_sales]
                    returns = Return.query.filter(
                        Return.original_sale_id.in_(sale_ids),
                        Return.status == 'completed',
                        Return.company_id == company_id
                    ).all() if sale_ids else []
                    gross = sum(s.total for s in month_sales)
                    refunds = sum(r.refund_amount for r in returns)
                    data.append(max(0, gross - refunds))
                elif metric == 'count':
                    data.append(len(month_sales))
                elif metric == 'profit':
                    sale_ids = [s.id for s in month_sales]
                    items = SaleItem.query.filter(SaleItem.sale_id.in_(sale_ids)).all() if sale_ids else []
                    profit = sum(((item.price - (item.product.cost_price or 0)) * item.quantity)
                                 if item.product else 0 for item in items)
                    data.append(profit)
        
        return jsonify({
            'labels': labels,
            'data': data,
            'period': period,
            'metric': metric
        })
    
    except Exception as e:
        print(f"Error fetching sales chart data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'labels': [], 'data': []}), 500

@main_bp.route('/api/notifications')
@login_required
def get_notifications():
    """API endpoint to get real notifications."""
    try:
        company_id = get_company_id()
        notifications = []
        
        # Get recent sales (last 5)
        try:
            recent_sales = Sale.query.filter(
                Sale.company_id == company_id
            ).order_by(desc(Sale.date)).limit(5).all()
            for sale in recent_sales:
                time_ago = get_time_ago(sale.date)
                notifications.append({
                    'type': 'success',
                    'icon': 'fa-check-circle',
                    'title': f'Sale #{sale.id}',
                    'message': 'completed successfully.',
                    'time': time_ago
                })
        except Exception as e:
            print(f"Error fetching sales: {e}")
        
        # Get low stock products
        try:
            low_stock_products = Product.query.filter(
                Product.stock <= Product.low_stock_threshold,
                Product.company_id == company_id
            ).limit(3).all()
            for product in low_stock_products:
                notifications.append({
                    'type': 'warning',
                    'icon': 'fa-exclamation-triangle',
                    'title': 'Low Stock Alert',
                    'message': f'Product "{product.name}" is running low (stock: {float(product.stock) if product.stock else 0}).',
                    'time': 'Just now'
                })
        except Exception as e:
            print(f"Error fetching low stock products: {e}")
        
        # Get recent purchases (last 3)
        try:
            recent_purchases = Purchase.query.filter(
                Purchase.company_id == company_id
            ).order_by(desc(Purchase.date)).limit(3).all()
            for purchase in recent_purchases:
                time_ago = get_time_ago(purchase.date)
                purchase_title = f'Purchase #{purchase.invoice_number}' if purchase.invoice_number else f'Purchase #{purchase.id}'
                notifications.append({
                    'type': 'info',
                    'icon': 'fa-box',
                    'title': purchase_title,
                    'message': 'has been received.',
                    'time': time_ago
                })
        except Exception as e:
            print(f"Error fetching purchases: {e}")
        
        # Limit to 10 notifications
        notifications = notifications[:10]
        
        return jsonify({
            'notifications': notifications,
            'count': len(notifications)
        })
    except Exception as e:
        print(f"Error in get_notifications: {e}")
        return jsonify({'error': 'Failed to load notifications', 'notifications': [], 'count': 0}), 200

def get_time_ago(dt):
    """Helper function to get time ago string."""
    if not dt:
        return 'Unknown'
    
    now = datetime.utcnow()
    if dt.tzinfo:
        now = datetime.utcnow().replace(tzinfo=dt.tzinfo)
    
    diff = now - dt
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f'{hours} hour{"s" if hours > 1 else ""} ago'
    else:
        days = int(seconds / 86400)
        if days == 1:
            return 'Yesterday'
        return f'{days} days ago'
