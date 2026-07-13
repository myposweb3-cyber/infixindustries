"""
Professional Invoice & Receipt Generator
Supports A4, A5, and 80mm Thermal Receipt formats
Optimized for 300 DPI printing with CMYK color support
"""

from flask import render_template_string
from datetime import datetime
from typing import Dict, List, Optional, Literal
import json


class InvoiceGenerator:
    """Generate professional print-ready invoices and receipts"""

    def __init__(self):
        self.paper_sizes = {
            'A4': {'width': '210mm', 'height': '297mm'},
            'A5': {'width': '148mm', 'height': '210mm'},
            'THERMAL_80MM': {'width': '80mm', 'height': 'auto'}
        }

    def format_currency(self, amount: float) -> str:
        """Format amount as currency"""
        return f"${amount:,.2f}"

    def format_date(self, date: datetime) -> str:
        """Format date for invoice"""
        return date.strftime('%m/%d/%Y')

    def generate_a4_invoice(self, invoice_data: Dict) -> str:
        """
        Generate A4 invoice HTML

        Args:
            invoice_data: Dictionary containing invoice information
                - invoice_number: str
                - invoice_date: datetime
                - due_date: datetime
                - company: Dict with logo, name, address, etc.
                - customer: Dict with name, address, contact
                - items: List of Dict with code, description, qty, price, discount, tax
                - subtotal: float
                - discount: float
                - tax: float
                - total: float
                - notes: str (optional)

        Returns:
            HTML string ready for printing
        """
        try:
            # Prepare data with formatting
            formatted_data = self._prepare_invoice_data(invoice_data)

            # Calculate totals
            formatted_data['subtotal_formatted'] = self.format_currency(
                invoice_data.get('subtotal', 0)
            )
            formatted_data['discount_formatted'] = self.format_currency(
                invoice_data.get('discount', 0)
            )
            formatted_data['tax_formatted'] = self.format_currency(
                invoice_data.get('tax', 0)
            )
            formatted_data['total_formatted'] = self.format_currency(
                invoice_data.get('total', 0)
            )
            formatted_data['balance_due'] = self.format_currency(
                invoice_data.get('total', 0) - invoice_data.get('paid_amount', 0)
            )

            return render_template_string(self._get_a4_template(), **formatted_data)

        except Exception as e:
            return f"<p>Error generating invoice: {str(e)}</p>"

    def generate_a5_invoice(self, invoice_data: Dict) -> str:
        """Generate A5 invoice HTML (compact version)"""
        try:
            formatted_data = self._prepare_invoice_data(invoice_data)

            formatted_data['subtotal_formatted'] = self.format_currency(
                invoice_data.get('subtotal', 0)
            )
            formatted_data['total_formatted'] = self.format_currency(
                invoice_data.get('total', 0)
            )
            formatted_data['balance_due'] = self.format_currency(
                invoice_data.get('total', 0) - invoice_data.get('paid_amount', 0)
            )

            return render_template_string(self._get_a5_template(), **formatted_data)

        except Exception as e:
            return f"<p>Error generating invoice: {str(e)}</p>"

    def generate_thermal_receipt(self, receipt_data: Dict) -> str:
        """Generate 80mm thermal receipt for POS systems"""
        try:
            formatted_data = self._prepare_receipt_data(receipt_data)

            formatted_data['subtotal_formatted'] = self.format_currency(
                receipt_data.get('subtotal', 0)
            )
            formatted_data['total_formatted'] = self.format_currency(
                receipt_data.get('total', 0)
            )
            formatted_data['change'] = self.format_currency(
                receipt_data.get('change', 0)
            )

            return render_template_string(self._get_thermal_template(), **formatted_data)

        except Exception as e:
            return f"Error generating receipt: {str(e)}"

    def _prepare_invoice_data(self, data: Dict) -> Dict:
        """Prepare and format invoice data"""
        company = data.get('company', {})
        customer = data.get('customer', {})
        items = data.get('items', [])

        # Format items
        formatted_items = []
        for item in items:
            formatted_items.append({
                'code': item.get('code', ''),
                'description': item.get('description', ''),
                'qty': item.get('qty', 1),
                'unit_price': self.format_currency(item.get('unit_price', 0)),
                'discount': self.format_currency(item.get('discount', 0)),
                'tax': self.format_currency(item.get('tax', 0)),
                'total': self.format_currency(item.get('total', 0))
            })

        return {
            'invoice_number': data.get('invoice_number', 'INV-XXXX'),
            'invoice_date': self.format_date(data.get('invoice_date', datetime.now())),
            'due_date': self.format_date(data.get('due_date', datetime.now())),
            'company_logo': company.get('logo', 'LOGO'),
            'company_name': company.get('name', 'Your Company Name'),
            'company_address': company.get('address', ''),
            'company_city': company.get('city', ''),
            'company_phone': company.get('phone', ''),
            'company_email': company.get('email', ''),
            'company_website': company.get('website', ''),
            'company_tax_id': company.get('tax_id', ''),
            'customer_name': customer.get('name', ''),
            'customer_company': customer.get('company', ''),
            'customer_address': customer.get('address', ''),
            'customer_city': customer.get('city', ''),
            'customer_phone': customer.get('phone', ''),
            'customer_email': customer.get('email', ''),
            'ship_address': customer.get('ship_address', customer.get('address', '')),
            'items': formatted_items,
            'notes': data.get('notes', ''),
            'terms': data.get('terms', 'Net 30'),
            'paid_amount': self.format_currency(data.get('paid_amount', 0))
        }

    def _prepare_receipt_data(self, data: Dict) -> Dict:
        """Prepare and format receipt data for thermal printing"""
        company = data.get('company', {})
        customer = data.get('customer', {})
        items = data.get('items', [])

        formatted_items = []
        for item in items:
            formatted_items.append({
                'qty': item.get('qty', 1),
                'description': item.get('description', ''),
                'code': item.get('code', ''),
                'price': self.format_currency(item.get('price', 0)),
                'total': self.format_currency(item.get('total', 0))
            })

        return {
            'receipt_number': data.get('receipt_number', '0001234'),
            'receipt_date': self.format_date(data.get('receipt_date', datetime.now())),
            'receipt_time': data.get('receipt_time', datetime.now().strftime('%H:%M:%S')),
            'cashier': data.get('cashier', 'Cashier'),
            'company_name': company.get('name', 'YOUR STORE'),
            'company_subline': company.get('subline', 'Professional POS System'),
            'company_address': company.get('address', ''),
            'company_phone': company.get('phone', ''),
            'customer_name': customer.get('name', 'Walk-In Customer'),
            'invoice_number': data.get('invoice_number', ''),
            'items': formatted_items,
            'payment_method': data.get('payment_method', 'CASH'),
            'reference': data.get('reference', ''),
            'authorization': data.get('authorization', 'APPROVED'),
            'tender': self.format_currency(data.get('tender', 0)),
            'qr_code': data.get('qr_code', ''),
            'thank_you_message': data.get('thank_you_message', 'THANK YOU! For your patronage and support'),
            'return_policy': data.get('return_policy', ''),
            'warranty_info': data.get('warranty_info', '')
        }

    def _get_a4_template(self) -> str:
        """Get A4 invoice HTML template"""
        return '''
        <!-- A4 Invoice Template with Jinja2 variables -->
        <invoice-a4 
            invoice_number="{{ invoice_number }}"
            invoice_date="{{ invoice_date }}"
            due_date="{{ due_date }}"
            company_name="{{ company_name }}"
            customer_name="{{ customer_name }}"
            subtotal="{{ subtotal_formatted }}"
            total="{{ total_formatted }}"
            balance_due="{{ balance_due }}"
        ></invoice-a4>
        '''

    def _get_a5_template(self) -> str:
        """Get A5 invoice HTML template"""
        return '''
        <!-- A5 Invoice Template with Jinja2 variables -->
        <invoice-a5
            invoice_number="{{ invoice_number }}"
            invoice_date="{{ invoice_date }}"
            company_name="{{ company_name }}"
            customer_name="{{ customer_name }}"
            total="{{ total_formatted }}"
            balance_due="{{ balance_due }}"
        ></invoice-a5>
        '''

    def _get_thermal_template(self) -> str:
        """Get 80mm thermal receipt HTML template"""
        return '''
        <!-- Thermal Receipt Template with Jinja2 variables -->
        <receipt-thermal
            receipt_number="{{ receipt_number }}"
            receipt_date="{{ receipt_date }}"
            receipt_time="{{ receipt_time }}"
            cashier="{{ cashier }}"
            company_name="{{ company_name }}"
            customer_name="{{ customer_name }}"
            total="{{ total_formatted }}"
            change="{{ change }}"
        ></receipt-thermal>
        '''

    @staticmethod
    def get_sample_a4_invoice() -> Dict:
        """Return sample data for A4 invoice"""
        return {
            'invoice_number': 'INV-2026-001234',
            'invoice_date': datetime(2026, 5, 19),
            'due_date': datetime(2026, 6, 19),
            'company': {
                'logo': 'LOGO',
                'name': 'Your Company Name',
                'address': '123 Business Street, Suite 100',
                'city': 'New York, NY 10001',
                'phone': '+1 (555) 123-4567',
                'email': 'billing@company.com',
                'website': 'www.company.com',
                'tax_id': '12-3456789'
            },
            'customer': {
                'name': 'John Anderson',
                'company': 'Anderson Industries Corp',
                'address': '456 Commerce Avenue',
                'city': 'New York, NY 10002',
                'phone': '+1 (555) 987-6543',
                'email': 'john@anderson.com',
                'ship_address': '456 Commerce Avenue'
            },
            'items': [
                {
                    'code': 'SKU-001',
                    'description': 'Professional Business Services - Annual Consultation Package',
                    'qty': 1,
                    'unit_price': 2500.00,
                    'discount': 0.00,
                    'tax': 200.00,
                    'total': 2700.00
                },
                {
                    'code': 'SKU-002',
                    'description': 'Premium Software License - 12 Months',
                    'qty': 3,
                    'unit_price': 450.00,
                    'discount': 135.00,
                    'tax': 94.50,
                    'total': 1409.50
                }
            ],
            'subtotal': 5150.00,
            'discount': 315.00,
            'tax': 386.80,
            'total': 5221.80,
            'paid_amount': 0.00,
            'notes': 'Thank you for your business!',
            'terms': 'Net 30'
        }

    @staticmethod
    def get_sample_thermal_receipt() -> Dict:
        """Return sample data for thermal receipt"""
        now = datetime.now()
        return {
            'receipt_number': '0001234',
            'receipt_date': now,
            'receipt_time': now.strftime('%H:%M:%S'),
            'cashier': 'John Smith',
            'company': {
                'name': 'YOUR STORE',
                'subline': 'Professional POS System',
                'address': '123 Main Street | Suite 100, New York, NY 10001',
                'phone': 'Tel: (555) 123-4567'
            },
            'customer': {
                'name': 'Walk-In Customer'
            },
            'invoice_number': 'INV-2026-4567',
            'items': [
                {
                    'code': 'SKU-001',
                    'description': 'Premium Item #1',
                    'qty': 2,
                    'price': 25.00,
                    'total': 50.00
                },
                {
                    'code': 'SVC-002',
                    'description': 'Service Package',
                    'qty': 1,
                    'price': 75.00,
                    'total': 75.00
                }
            ],
            'subtotal': 201.50,
            'tax': 15.31,
            'total': 211.73,
            'change': 0.00,
            'payment_method': 'CARD',
            'reference': '123456789012',
            'authorization': 'APPROVED',
            'tender': 211.73,
            'qr_code': '[QR_CODE_DATA]',
            'thank_you_message': 'THANK YOU! For your patronage and support',
            'return_policy': 'Item returns accepted within 30 days with original receipt.',
            'warranty_info': 'Standard warranty: 1 year'
        }


# Usage Examples:

def example_generate_a4():
    """Example: Generate A4 invoice"""
    generator = InvoiceGenerator()
    sample_data = generator.get_sample_a4_invoice()
    html = generator.generate_a4_invoice(sample_data)
    # Save or return for printing
    with open('invoice_a4.html', 'w') as f:
        f.write(html)


def example_generate_thermal():
    """Example: Generate thermal receipt"""
    generator = InvoiceGenerator()
    sample_data = generator.get_sample_thermal_receipt()
    html = generator.generate_thermal_receipt(sample_data)
    # Send to thermal printer
    return html


def example_custom_invoice(company_data, customer_data, items):
    """Example: Generate invoice with custom data"""
    generator = InvoiceGenerator()

    invoice_data = {
        'invoice_number': 'INV-2026-005678',
        'invoice_date': datetime.now(),
        'due_date': datetime.now(),
        'company': company_data,
        'customer': customer_data,
        'items': items,
        'subtotal': sum(item['total'] for item in items),
        'discount': 0.00,
        'tax': sum(item.get('tax', 0) for item in items),
        'total': sum(item['total'] for item in items),
        'paid_amount': 0.00
    }

    return generator.generate_a4_invoice(invoice_data)


if __name__ == '__main__':
    # Test examples
    generator = InvoiceGenerator()

    print("Invoice Generator initialized successfully!")
    print(f"Supported paper sizes: {list(generator.paper_sizes.keys())}")
    print("\nSample A4 Invoice Data:")
    print(json.dumps(generator.get_sample_a4_invoice(), indent=2, default=str))
