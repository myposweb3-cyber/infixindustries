from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from app.models import db, Product, Sale, SaleItem, Customer, Setting, HeldBill, Return, ReturnItem, InventoryTransaction
from app.models import Exchange, ExchangeItem
from app.utils.permissions import require_permission
from app.utils.security import get_company_id
from app.utils.company import column_exists_in_db
from datetime import datetime, timedelta
from sqlalchemy import desc, case, or_
import json
from app.utils.email_sender import send_email
from app.utils.whatsapp_sender import generate_whatsapp_link
from app.utils.whatsapp_twilio import send_whatsapp_via_twilio
from app.utils.receipt_generator import ReceiptGenerator
from app import csrf

sales_bp = Blueprint('sales', __name__, template_folder='../../templates')

def get_company_filter(model_class):
    """Get company filter for a model if company_id column exists."""
    company_id = get_company_id()
    if company_id and hasattr(model_class, 'company_id'):
        return model_class.company_id == company_id
    return None

@sales_bp.route('/sales')
@login_required
@require_permission('can_access_sales')
def sales():
    """Main sales page."""
    return render_template('sales/sales.html')

# ... [all other functions unchanged until send-whatsapp] ...

@sales_bp.route('/api/sales/<int:sale_id>/send-whatsapp', methods=['POST'])
@login_required
def send_whatsapp_receipt(sale_id):
    """Generate WhatsApp link to share a receipt summary. Expects JSON { "phone": "..." }"""
    data = request.get_json() or {}
    phone = data.get('phone', '').strip()
    
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number is required'}), 400
    
    # Server-side validation (matches frontend)
    phone_digits = ''.join(c for c in phone if c.isdigit())
    
    if len(phone_digits) < 10:
        return jsonify({'success': False, 'error': 'Invalid phone number. Need 10+ digits (e.g. 94771234567)'}), 400
    
    if not phone_digits.startswith('94'):
        return jsonify({'success': False, 'error': 'Sri Lanka numbers must start with 94 (e.g. 94771234567)'}), 400

    
    sale = Sale.query.get_or_404(sale_id)

    # Professional WhatsApp Receipt - Direct Twilio
    def send_professional_receipt(sale_id, phone_digits):
        sale = Sale.query.get(sale_id)
        cashier = current_user.username
        
        subtotal = sum(item.quantity * item.price for item in sale.items)
        
        items = '\n'.join([
            f"{item.product.name[:20]:<20}x{int(item.quantity)} = Rs.{item.quantity*item.price:>8.2f}"
            for item in sale.items
        ])
        
        text = f"""*POS SYSTEM*
📞 +94 77 123 4567

🧾 *RECEIPT # {sale.id}*
Date: {sale.date.strftime('%Y-%m-%d %H:%M')}
Cashier: {cashier}
Payment: {sale.payment}

ITEMS:
{items}

Subtotal     Rs.{subtotal:>9.2f}
*Total       Rs.{sale.total:>9.2f}*
Paid:        Rs.{sale.cash_given:>9.2f}
Balance:     Rs.{sale.balance:>9.2f}

Thank you for shopping!
View: http://localhost:5000/sales/{sale.id}/receipt/html"""
        
        return send_whatsapp_via_twilio(phone_digits, text)
    
    # Prefer Twilio if configured
    twilio_enabled = current_app.config.get('TWILIO_ACCOUNT_SID') and current_app.config.get('TWILIO_AUTH_TOKEN') and current_app.config.get('TWILIO_WHATSAPP_FROM')
    if twilio_enabled:
        ok, res = send_professional_receipt(sale_id, phone_digits)
        if ok:
            return jsonify({'success': True, 'twilio_sid': res})
        else:
            # fallback to link if Twilio fails
            link = generate_whatsapp_link(phone_digits, text)
            return jsonify({'success': False, 'error': f'Twilio failed: {res}', 'wa_link': link}), 500

    # Fallback: return wa.me link
    link = generate_whatsapp_link(phone_digits, text)
    if not link:
        return jsonify({'success': False, 'error': 'Failed to generate WhatsApp link'}), 500

    return jsonify({'success': True, 'wa_link': link})

# ... [rest of the file unchanged - all other functions remain the same]


