"""
Message Scheduler - Handles automated and manual messaging features
Supports WhatsApp (via Twilio) and Email notifications
"""

from datetime import datetime, timedelta
from flask import current_app
from app.models import db, Customer, Sale, Setting
from app.utils.whatsapp_twilio import send_whatsapp_via_twilio
from app.utils.whatsapp_sender import generate_whatsapp_link
from app.utils.email_sender import send_email
import logging

logger = logging.getLogger(__name__)


class MessageScheduler:
    """Handles sending various types of messages to customers"""
    
    def __init__(self):
        self.whatsapp_enabled = self._is_whatsapp_enabled()
        self.email_enabled = self._is_email_enabled()
    
    def _is_whatsapp_enabled(self):
        """Check if WhatsApp is configured"""
        return current_app.config.get('TWILIO_ACCOUNT_SID') and \
               current_app.config.get('TWILIO_AUTH_TOKEN') and \
               current_app.config.get('TWILIO_WHATSAPP_FROM')
    
    def _is_email_enabled(self):
        """Check if email is configured"""
        return current_app.config.get('SMTP_SERVER') and \
               current_app.config.get('SMTP_USERNAME')
    
    def _get_setting(self, key, default=''):
        """Get setting value from database"""
        setting = Setting.query.filter_by(
            setting_category='notifications',
            setting_key=key
        ).first()
        return setting.setting_value if setting and setting.setting_value else default
    
    def _get_business_name(self):
        """Get business name for messages"""
        setting = Setting.query.filter_by(
            setting_category='general',
            setting_key='business_name'
        ).first()
        return setting.setting_value if setting and setting.setting_value else 'POS System'
    
    # ========== Customer Receipts ==========
    
    def send_receipt(self, sale_id, phone=None, email=None, channel='whatsapp', cashier_name='', paid_amount=0.0, balance=0.0, receipt_link=''):
        """
        Send receipt to customer after sale
        Args:
            sale_id: Sale ID
            phone: Customer phone number (optional, will lookup from sale)
            email: Customer email (optional)
            channel: 'whatsapp', 'email', or 'both'
            cashier_name: Name of cashier (from current_user)
            paid_amount: Amount paid by customer (e.g. cash_given)
            balance: Remaining balance
            receipt_link: Link to full digital receipt
        """
        sale = Sale.query.get(sale_id)
        if not sale:
            return False, "Sale not found"
        
        # Get customer contact info
        if not phone and sale.customer != 'Walk-in Customer':
            customer = Customer.query.filter_by(name=sale.customer).first()
            if customer:
                phone = customer.phone
                email = customer.email
        
        if not phone and not email:
            return False, "No customer contact information available"
        
        # Build receipt message with enhanced params (defaults for backward compat)
        business_name = self._get_business_name()
        payment_method = getattr(sale, 'payment_method', sale.payment if hasattr(sale, 'payment') else 'Cash')
        message = self._build_receipt_message(
            sale, business_name, cashier_name, payment_method, paid_amount, balance, receipt_link
        )
        
        results = []
        
        # Send via WhatsApp
        if channel in ['whatsapp', 'both'] and phone:
            ok, msg = self._send_whatsapp(phone, message)
            results.append(('whatsapp', ok, msg))
        
        # Send via Email
        if channel in ['email', 'both'] and email:
            subject = f"Receipt from {business_name} - Sale #{sale.id}"
            body = message + "\n\n" + self._get_receipt_email_footer()
            ok, msg = self._send_email(email, subject, body)
            results.append(('email', ok, msg))
        
        # Check if at least one succeeded
        success = any(ok for _, ok, _ in results)
        return success, results
    
    def _build_receipt_message(self, sale, business_name, cashier_name='', payment_method='', paid_amount=0.0, balance=0.0, receipt_link=''):
        """Build receipt text message"""
        items_text = "\n".join([
            f"• {item.product.name} x{int(item.quantity)} = {item.quantity * item.price:.2f}"
            for item in sale.items
        ])
        
        message = f"🧾 *Receipt - {business_name}*\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Receipt #: {sale.id}\n"
        message += f"Date: {sale.date.strftime('%Y-%m-%d %H:%M')}\n"
        message += f"Customer: {sale.customer}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Items:\n{items_text}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"*Total: {sale.total:.2f}*\n"
        message += f"Payment: {sale.payment}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Thank you for your business! 🙏"
        
        return message
    
    def _get_receipt_email_footer(self):
        """Get email footer for receipts"""
        return "\n\n---\nThis is an automated receipt. Please keep this for your records."
    
    # ========== Order Alerts ==========
    
    def send_order_alert(self, sale_id, channel='whatsapp'):
        """
        Send order alert to staff/admin when new order is placed
        """
        sale = Sale.query.get(sale_id)
        if not sale:
            return False, "Sale not found"
        
        # Get admin phone from settings
        admin_phone = self._get_setting('admin_phone')
        if not admin_phone:
            return False, "Admin phone not configured"
        
        business_name = self._get_business_name()
        
        message = f"🔔 *New Order Alert*\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Order #: {sale.id}\n"
        message += f"Customer: {sale.customer}\n"
        message += f"Total: {sale.total:.2f}\n"
        message += f"Payment: {sale.payment}\n"
        message += f"Time: {sale.date.strftime('%Y-%m-%d %H:%M')}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Please process this order."
        
        return self._send_whatsapp(admin_phone, message)
    
    # ========== Payment Reminders ==========
    
    def send_payment_reminder(self, customer_id, days_overdue=0):
        """
        Send payment reminder to customer with credit/balance
        """
        customer = Customer.query.get(customer_id)
        if not customer or customer.current_balance <= 0:
            return False, "No outstanding balance"
        
        if not customer.phone:
            return False, "No phone number"
        
        business_name = self._get_business_name()
        
        message = f"⏰ *Payment Reminder*\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Dear {customer.name},\n\n"
        message += f"This is a friendly reminder that you have an outstanding balance of *{customer.current_balance:.2f}* at {business_name}.\n\n"
        
        if days_overdue > 0:
            message += f"Your payment is {days_overdue} day(s) overdue.\n\n"
        
        message += f"Please clear your payment at your earliest convenience.\n\n"
        message += f"Thank you for your cooperation! 🙏"
        
        return self._send_whatsapp(customer.phone, message)

    def send_bulk_payment_reminders(self):
        """
        Send payment reminders to all customers with overdue balances
        Called by scheduler
        """
        # Get customers with credit balances
        if hasattr(Customer, 'is_active'):
            customers = Customer.query.filter(
                Customer.current_balance > 0,
                Customer.is_active == True
            ).all()
        else:
            customers = Customer.query.filter(
                Customer.current_balance > 0
            ).all()
        
        results = []
        for customer in customers:
            ok, msg = self.send_payment_reminder(customer.id)
            results.append((customer.id, ok, msg))
        
        return results
    
    # ========== Delivery Alerts ==========
    
    def send_delivery_alert(self, sale_id, status='pending'):
        """
        Send delivery status update to customer
        Status: 'pending', 'shipped', 'out_for_delivery', 'delivered'
        """
        sale = Sale.query.get(sale_id)
        if not sale:
            return False, "Sale not found"
        
        # Get customer phone
        if sale.customer == 'Walk-in Customer':
            return False, "Walk-in customer, no delivery needed"
        
        customer = Customer.query.filter_by(name=sale.customer).first()
        if not customer or not customer.phone:
            return False, "No customer phone"
        
        business_name = self._get_business_name()
        
        status_emoji = {
            'pending': '📦',
            'shipped': '🚚',
            'out_for_delivery': '🏃',
            'delivered': '✅'
        }
        
        status_text = {
            'pending': 'Preparing',
            'shipped': 'Shipped',
            'out_for_delivery': 'Out for Delivery',
            'delivered': 'Delivered'
        }
        
        emoji = status_emoji.get(status, '📦')
        text = status_text.get(status, 'Processing')
        
        message = f"{emoji} *Delivery Update*\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Dear {customer.name},\n\n"
        message += f"Your order #{sale.id} from {business_name} is now: *{text}*\n\n"
        
        if status == 'delivered':
            message += f"Thank you for your purchase! We hope to serve you again soon.\n\n"
            message += f"Please rate your experience with us."
        elif status == 'out_for_delivery':
            message += f"Expected delivery today. Please be available to receive your order."
        elif status == 'shipped':
            message += f"Your order is on its way! Track your delivery for updates."
        else:
            message += f"We are preparing your order and will update you soon."
        
        message += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        message += f"Total: {sale.total:.2f}"
        
        return self._send_whatsapp(customer.phone, message)
    
    # ========== Custom Reminders ==========
    
    def send_custom_reminder(self, customer_id, message_text):
        """
        Send custom reminder to a specific customer
        """
        customer = Customer.query.get(customer_id)
        if not customer or not customer.phone:
            return False, "Customer not found or no phone"
        
        return self._send_whatsapp(customer.phone, message_text)
    
    def send_reminder_to_self(self, message_text, channel='whatsapp'):
        """
        Send a reminder/message to the admin's own number
        """
        admin_phone = self._get_setting('admin_phone')
        if not admin_phone:
            return False, "Admin phone not configured"
        
        business_name = self._get_business_name()
        full_message = f"📝 *Self Reminder*\n"
        full_message += f"━━━━━━━━━━━━━━━━━━━━\n"
        full_message += f"{message_text}\n"
        full_message += f"━━━━━━━━━━━━━━━━━━━━\n"
        full_message += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        if channel == 'email':
            admin_email = self._get_setting('admin_email')
            if admin_email:
                subject = f"Self Reminder from {business_name}"
                return self._send_email(admin_email, subject, full_message)
            return False, "Admin email not configured"
        
        return self._send_whatsapp(admin_phone, full_message)
    
    # ========== Bulk Messaging ==========
    
    def send_bulk_message(self, customer_ids, message_text, channel='whatsapp'):
        """
        Send message to multiple customers
        Args:
            customer_ids: List of customer IDs
            message_text: Message to send
            channel: 'whatsapp' or 'email'
        """
        customers = Customer.query.filter(
            Customer.id.in_(customer_ids),
            Customer.is_active == True
        ).all()
        
        results = []
        for customer in customers:
            if channel == 'whatsapp' and customer.phone:
                ok, msg = self._send_whatsapp(customer.phone, message_text)
                results.append((customer.id, customer.name, ok, msg))
            elif channel == 'email' and customer.email:
                subject = f"Message from {self._get_business_name()}"
                ok, msg = self._send_email(customer.email, subject, message_text)
                results.append((customer.id, customer.name, ok, msg))
        
        return results
    
    def send_bulk_to_all(self, message_text, channel='whatsapp'):
        """
        Send message to all active customers
        """
        customers = Customer.query.filter(
            Customer.is_active == True
        ).all()
        
        customer_ids = [c.id for c in customers]
        return self.send_bulk_message(customer_ids, message_text, channel)
    
    # ========== Helper Methods ==========
    
    def _send_whatsapp(self, phone, message):
        """Send WhatsApp message"""
        if not self.whatsapp_enabled:
            # Fallback to wa.me link
            link = generate_whatsapp_link(phone, message)
            return False, f"WhatsApp not configured. Link: {link}"
        
        ok, result = send_whatsapp_via_twilio(phone, message)
        return ok, result
    
    def _send_email(self, email, subject, body):
        """Send email"""
        if not self.email_enabled:
            return False, "Email not configured"
        
        ok, result = send_email(email, subject, body)
        return ok, result
    
    # ========== Auto-Send Methods ==========
    
    def check_and_send_auto_messages(self, sale_id):
        """
        Check auto-send settings and send appropriate messages after a sale
        Called automatically after sale creation
        """
        # Check if auto-send receipt is enabled
        auto_receipt = self._get_setting('auto_send_receipt', 'false').lower() == 'true'
        if auto_receipt:
            self.send_receipt(sale_id, channel='whatsapp')
        
        # Check if order alert is enabled
        auto_order_alert = self._get_setting('auto_order_alert', 'false').lower() == 'true'
        if auto_order_alert:
            self.send_order_alert(sale_id)
        
        return True


# ========== Standalone Functions for Easy Import ==========

def send_sale_receipt(sale_id, phone=None, email=None, channel='whatsapp', cashier_name='', paid_amount=0.0, balance=0.0, receipt_link=''):
    """Convenience function to send receipt"""
    scheduler = MessageScheduler()
    return scheduler.send_receipt(sale_id, phone, email, channel, cashier_name, paid_amount, balance, receipt_link)


def send_order_notification(sale_id):
    """Convenience function to send order notification"""
    scheduler = MessageScheduler()
    return scheduler.send_order_alert(sale_id)


def send_delivery_update(sale_id, status):
    """Convenience function to send delivery update"""
    scheduler = MessageScheduler()
    return scheduler.send_delivery_alert(sale_id, status)


def send_payment_due_reminder(customer_id):
    """Convenience function to send payment reminder"""
    scheduler = MessageScheduler()
    return scheduler.send_payment_reminder(customer_id)


def send_bulk_to_customers(customer_ids, message, channel='whatsapp'):
    """Convenience function for bulk messaging"""
    scheduler = MessageScheduler()
    return scheduler.send_bulk_message(customer_ids, message, channel)


def send_reminder_to_self(message, channel='whatsapp'):
    """Convenience function to send self reminder"""
    scheduler = MessageScheduler()
    return scheduler.send_reminder_to_self(message, channel)
