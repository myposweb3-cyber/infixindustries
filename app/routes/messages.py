"""
Messages Routes - Fixed version with proper permissions
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, Customer, Sale, Setting
from app.utils.permissions import require_permission
from app.utils.security import get_company_id
from app.utils.message_scheduler import MessageScheduler, send_sale_receipt, send_order_notification, send_delivery_update, send_payment_due_reminder, send_bulk_to_customers, send_reminder_to_self
from app import csrf
from sqlalchemy import or_
import logging

logger = logging.getLogger(__name__)

messages_bp = Blueprint('messages', __name__, template_folder='../../templates')


@messages_bp.route('/messages')
@login_required
@require_permission('can_access_messages')
def messages():
    return render_template('messages/messages.html')


# GET customers for messaging
@messages_bp.route('/api/messages/customers', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_get_customers_for_messaging():
    company_id = get_company_id()
    search = request.args.get('search', '').strip()
    with_balance = request.args.get('with_balance', 'false').lower() == 'true'
    
    # Skip is_active filter - query all customers
    query = Customer.query.filter(
        Customer.company_id == company_id
    )
    
    if search:
        query = query.filter(
            db.or_(
                Customer.name.ilike(f'%{search}%'),
                Customer.phone.ilike(f'%{search}%')
            )
        )
    
    if with_balance:
        query = query.filter(Customer.current_balance > 0)
    
    customers = query.order_by(Customer.name).limit(50).all()
    
    result = []
    for customer in customers:
        result.append({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'current_balance': customer.current_balance,
            'total_purchases': customer.total_purchases
        })
    
    return jsonify(result)


# Send custom reminder to customer
@messages_bp.route('/api/messages/customer/<int:customer_id>/custom-reminder', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_send_custom_reminder(customer_id):
    data = request.get_json() or {}
    message = data.get('message')
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    try:
        scheduler = MessageScheduler()
        ok, result = scheduler.send_custom_reminder(customer_id, message)
        
        if ok:
            return jsonify({'success': True, 'message': 'Reminder sent successfully'})
        else:
            return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        logger.error(f"Error sending custom reminder: {e}")
        return jsonify({'error': str(e)}), 500


# Send payment reminder
@messages_bp.route('/api/messages/customer/<int:customer_id>/payment-reminder', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_send_payment_reminder(customer_id):
    try:
        scheduler = MessageScheduler()
        ok, result = scheduler.send_payment_reminder(customer_id)
        
        if ok:
            return jsonify({'success': True, 'message': 'Payment reminder sent'})
        else:
            return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        logger.error(f"Error sending payment reminder: {e}")
        return jsonify({'error': str(e)}), 500


# Send payment reminders to all
@messages_bp.route('/api/messages/payment-reminders/send-all', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_send_all_payment_reminders():
    try:
        scheduler = MessageScheduler()
        results = scheduler.send_bulk_payment_reminders()
        
        success_count = sum(1 for _, ok, _ in results if ok)
        return jsonify({
            'success': True, 
            'message': f'Sent {success_count} payment reminders',
            'results': results
        })
    except Exception as e:
        logger.error(f"Error sending bulk payment reminders: {e}")
        return jsonify({'error': str(e)}), 500


# Self message
@messages_bp.route('/api/messages/self', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_send_self_message():
    data = request.get_json() or {}
    message = data.get('message')
    channel = data.get('channel', 'whatsapp')
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    try:
        ok, result = send_reminder_to_self(message, channel)
        
        if ok:
            return jsonify({'success': True, 'message': 'Self reminder sent successfully'})
        else:
            return jsonify({'success': False, 'error': result}), 400
    except Exception as e:
        logger.error(f"Error sending self message: {e}")
        return jsonify({'error': str(e)}), 500


# Bulk message
@messages_bp.route('/api/messages/bulk', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_send_bulk_message():
    data = request.get_json() or {}
    
    customer_ids = data.get('customer_ids', [])
    message = data.get('message')
    channel = data.get('channel', 'whatsapp')
    
    if not customer_ids:
        return jsonify({'error': 'No customers selected'}), 400
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    try:
        results = send_bulk_to_customers(customer_ids, message, channel)
        
        success_count = sum(1 for _, _, ok, _ in results if ok)
        return jsonify({
            'success': True,
            'message': f'Sent {success_count} messages',
            'results': results
        })
    except Exception as e:
        logger.error(f"Error sending bulk message: {e}")
        return jsonify({'error': str(e)}), 500


# Bulk to all
@messages_bp.route('/api/messages/bulk/all', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_send_bulk_to_all():
    data = request.get_json() or {}
    
    message = data.get('message')
    channel = data.get('channel', 'whatsapp')
    
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    
    try:
        scheduler = MessageScheduler()
        results = scheduler.send_bulk_to_all(message, channel)
        
        success_count = sum(1 for _, _, ok, _ in results if ok)
        return jsonify({
            'success': True,
            'message': f'Sent {success_count} messages to all customers',
            'results': results
        })
    except Exception as e:
        logger.error(f"Error sending bulk to all: {e}")
        return jsonify({'error': str(e)}), 500


# Send receipt
@messages_bp.route('/api/messages/sale/<int:sale_id>/send-receipt', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_sales')
def api_send_receipt_for_sale(sale_id):
    data = request.get_json() or {}
    phone = data.get('phone')
    email = data.get('email')
    channel = data.get('channel', 'whatsapp')
    
    try:
        ok, result = send_sale_receipt(sale_id, phone, email, channel)
        
        if ok:
            return jsonify({'success': True, 'message': 'Receipt sent successfully'})
        else:
            if isinstance(result, list):
                for channel_name, success, msg in result:
                    if not success and 'wa.me' in str(msg):
                        return jsonify({'success': True, 'message': 'WhatsApp link generated', 'wa_link': msg})
            return jsonify({'success': False, 'error': str(result)}), 400
    except Exception as e:
        logger.error(f"Error sending receipt: {e}")
        return jsonify({'error': str(e)}), 500


# Get sales for messaging
@messages_bp.route('/api/messages/sales', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_view_sales_history')
def api_get_sales_for_messaging():
    try:
        company_id = get_company_id()
        limit = int(request.args.get('limit', 20))
        
        sales = Sale.query.filter(Sale.company_id == company_id).order_by(Sale.date.desc()).limit(limit).all()
        
        result = []
        for sale in sales:
            result.append({
                'id': sale.id,
                'date': sale.date.strftime('%Y-%m-%d %H:%M'),
                'customer': sale.customer,
                'total': sale.total,
                'payment': sale.payment,
                'items_count': len(sale.items)
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in api_get_sales_for_messaging: {e}")
        return jsonify([])


# Message settings
@messages_bp.route('/api/messages/settings', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_get_message_settings():
    settings = Setting.query.filter_by(setting_category='notifications').all()
    
    result = {}
    for setting in settings:
        result[setting.setting_key] = setting.setting_value
    
    defaults = {
        'auto_send_receipt': 'false',
        'auto_order_alert': 'false',
        'auto_payment_reminder': 'false',
        'auto_delivery_alert': 'false',
        'admin_phone': '',
        'admin_email': '',
        'default_channel': 'whatsapp'
    }
    
    for key, value in defaults.items():
        if key not in result:
            result[key] = value
    
    return jsonify(result)


@messages_bp.route('/api/messages/settings', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_save_message_settings():
    data = request.get_json() or {}
    
    try:
        for key, value in data.items():
            setting = Setting.query.filter_by(
                setting_category='notifications',
                setting_key=key
            ).first()
            
            if setting:
                setting.setting_value = str(value)
            else:
                setting = Setting(
                    setting_category='notifications',
                    setting_key=key,
                    setting_value=str(value)
                )
                db.session.add(setting)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving message settings: {e}")
        return jsonify({'error': str(e)}), 500


# Templates
@messages_bp.route('/api/messages/templates', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_messages')
def api_get_message_templates():
    templates = [
        {'id': 1, 'name': 'Payment Reminder', 'message': 'Dear {customer_name},\n\nThis is a friendly reminder that you have an outstanding balance of {balance} at {business_name}.\n\nPlease clear your payment at your earliest convenience.\n\nThank you!'},
        {'id': 2, 'name': 'Order Confirmed', 'message': 'Dear {customer_name},\n\nYour order #{order_id} has been confirmed!\n\nTotal: {total}\n\nThank you for your purchase.'},
        {'id': 3, 'name': 'Order Shipped', 'message': 'Dear {customer_name},\n\nGreat news! Your order #{order_id} has been shipped and is on its way.\n\nTrack your delivery for updates.'},
        {'id': 4, 'name': 'Out for Delivery', 'message': 'Dear {customer_name},\n\nYour order #{order_id} is out for delivery today! Please be available to receive your order.'},
        {'id': 5, 'name': 'Order Delivered', 'message': 'Dear {customer_name},\n\nYour order #{order_id} has been delivered!\n\nThank you for shopping with us. We hope to see you again soon!'},
        {'id': 6, 'name': 'Thank You', 'message': 'Dear {customer_name},\n\nThank you for your recent purchase at {business_name}!\n\nWe appreciate your business and look forward to serving you again.'},
        {'id': 7, 'name': 'Loyalty Points', 'message': 'Dear {customer_name},\n\nYou have {loyalty_points} loyalty points! Use them on your next purchase to get exciting rewards.\n\nThank you for being a valued customer!'},
        {'id': 8, 'name': 'Custom Message', 'message': ''}
    ]
    
    return jsonify(templates)


# WhatsApp link generator
@messages_bp.route('/api/messages/generate-whatsapp-link', methods=['POST'])
@csrf.exempt
@login_required
def api_generate_whatsapp_link():
    data = request.get_json() or {}
    phone = data.get('phone', '')
    message = data.get('message', '')
    
    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400
    
    from app.utils.whatsapp_sender import generate_whatsapp_link
    link = generate_whatsapp_link(phone, message)
    
    return jsonify({
        'success': True,
        'wa_link': link,
        'phone': phone,
        'message': message
    })
