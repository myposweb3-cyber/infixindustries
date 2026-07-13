from flask import Blueprint, render_template, request, jsonify, flash, send_file, current_app
from flask_login import login_required, current_user
from app.models import db, Setting
from app.utils.permissions import require_permission
from app.utils.security import get_company_id
from app import csrf
from sqlalchemy import or_
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
import os

quotation_bp = Blueprint('quotation', __name__, template_folder='../../templates')

@quotation_bp.route('/quotation')
@login_required
@require_permission('can_access_quotations')
def quotation():
    """Main quotation/cover note page."""
    return render_template('settings/quotation.html')

@quotation_bp.route('/api/quotation/generate', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_quotations')
def generate_quotation():
    """Generate a quotation/cover note based on form data."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Extract quotation data
    customer_name = data.get('customer_name', '')
    customer_address = data.get('customer_address', '')
    customer_phone = data.get('customer_phone', '')
    customer_email = data.get('customer_email', '')
    quotation_date = data.get('quotation_date', datetime.now().strftime('%Y-%m-%d'))
    quotation_number = data.get('quotation_number', f'QN-{datetime.now().strftime("%Y%m%d")}-{datetime.now().strftime("%H%M")}')
    valid_until = data.get('valid_until', '')
    items = data.get('items', [])
    notes = data.get('notes', '')
    discount_percent = float(data.get('discount_percent', 0))
    tax_percent = float(data.get('tax_percent', 0))
    
    # Calculate totals
    subtotal = sum(item.get('quantity', 1) * item.get('price', 0) for item in items)
    discount_amount = subtotal * (discount_percent / 100)
    after_discount = subtotal - discount_amount
    tax_amount = after_discount * (tax_percent / 100)
    total = after_discount + tax_amount
    
    # Get business settings
    business_name = get_setting('general', 'business_name', 'POS System')
    business_address = get_setting('receipt', 'business_address', '')
    business_phone = get_setting('receipt', 'business_phone', '')
    business_email = get_setting('receipt', 'business_email', '')
    business_gst = get_setting('receipt', 'business_gst', '')
    logo_path = get_setting('general', 'logo_path', '')
    
    # Prepare quotation data for template
    quotation_data = {
        'business_name': business_name,
        'business_address': business_address,
        'business_phone': business_phone,
        'business_email': business_email,
        'business_gst': business_gst,
        'logo_path': logo_path,
        'customer_name': customer_name,
        'customer_address': customer_address,
        'customer_phone': customer_phone,
        'customer_email': customer_email,
        'quotation_date': quotation_date,
        'quotation_number': quotation_number,
        'valid_until': valid_until,
        'items': items,
        'subtotal': subtotal,
        'discount_percent': discount_percent,
        'discount_amount': discount_amount,
        'tax_percent': tax_percent,
        'tax_amount': tax_amount,
        'total': total,
        'notes': notes,
        'currency_symbol': get_setting('general', 'currency_symbol', '₨')
    }
    
    return jsonify({
        'success': True,
        'quotation_data': quotation_data
    })

@quotation_bp.route('/api/quotation/pdf', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def generate_quotation_pdf():
    """Generate a PDF quotation/cover note."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Extract data
    customer_name = data.get('customer_name', '')
    customer_address = data.get('customer_address', '')
    customer_phone = data.get('customer_phone', '')
    customer_email = data.get('customer_email', '')
    quotation_date = data.get('quotation_date', datetime.now().strftime('%Y-%m-%d'))
    quotation_number = data.get('quotation_number', f'QN-{datetime.now().strftime("%Y%m%d")}-{datetime.now().strftime("%H%M")}')
    valid_until = data.get('valid_until', '')
    items = data.get('items', [])
    notes = data.get('notes', '')
    discount_percent = float(data.get('discount_percent', 0))
    tax_percent = float(data.get('tax_percent', 0))
    
    # Calculate totals
    subtotal = sum(item.get('quantity', 1) * item.get('price', 0) for item in items)
    discount_amount = subtotal * (discount_percent / 100)
    after_discount = subtotal - discount_amount
    tax_amount = after_discount * (tax_percent / 100)
    total = after_discount + tax_amount
    
    # Get business settings
    business_name = get_setting('general', 'business_name', 'POS System')
    business_address = get_setting('receipt', 'business_address', '')
    business_phone = get_setting('receipt', 'business_phone', '')
    business_email = get_setting('receipt', 'business_email', '')
    business_gst = get_setting('receipt', 'business_gst', '')
    logo_path = get_setting('general', 'logo_path', '')
    currency_symbol = get_setting('general', 'currency_symbol', '₨')
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, spaceAfter=20, alignment=1)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, spaceBefore=15, spaceAfter=10)
    normal_style = styles['Normal']
    
    # Header with logo and business info
    if logo_path:
        # Try to add logo
        try:
            full_logo_path = os.path.join(current_app.root_path, '..', logo_path.lstrip('/'))
            if os.path.exists(full_logo_path):
                logo = Image(full_logo_path, width=1.5*inch, height=0.75*inch)
                elements.append(logo)
        except:
            pass
    
    # Business Name
    elements.append(Paragraph(business_name, title_style))
    
    # Business details
    business_info = []
    if business_address:
        business_info.append(f"Address: {business_address}")
    if business_phone:
        business_info.append(f"Phone: {business_phone}")
    if business_email:
        business_info.append(f"Email: {business_email}")
    if business_gst:
        business_info.append(f"GST/Tax No: {business_gst}")
    
    for info in business_info:
        elements.append(Paragraph(f"<font size='10'>{info}</font>", normal_style))
    
    elements.append(Spacer(1, 20))
    
    # Quotation title
    elements.append(Paragraph("QUOTATION / COVER NOTE", title_style))
    elements.append(Spacer(1, 10))
    
    # Quotation details table
    quote_info = [
        ['Quotation Number:', quotation_number, 'Date:', quotation_date],
        ['Valid Until:', valid_until if valid_until else 'N/A', 'Customer:', customer_name]
    ]
    
    quote_table = Table(quote_info, colWidths=[1.5*inch, 2*inch, 1*inch, 2*inch])
    quote_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(quote_table)
    
    elements.append(Spacer(1, 20))
    
    # Customer details
    if customer_name or customer_address or customer_phone or customer_email:
        elements.append(Paragraph("Customer Details", heading_style))
        customer_details = []
        if customer_name:
            customer_details.append(f"Name: {customer_name}")
        if customer_address:
            customer_details.append(f"Address: {customer_address}")
        if customer_phone:
            customer_details.append(f"Phone: {customer_phone}")
        if customer_email:
            customer_details.append(f"Email: {customer_email}")
        
        for detail in customer_details:
            elements.append(Paragraph(f"<font size='10'>{detail}</font>", normal_style))
        elements.append(Spacer(1, 15))
    
    # Items table
    if items:
        elements.append(Paragraph("Items", heading_style))
        
        # Table headers
        table_data = [['#', 'Description', 'Qty', 'Unit Price', 'Total']]
        for idx, item in enumerate(items, 1):
            description = item.get('description', item.get('name', 'Item'))
            quantity = item.get('quantity', 1)
            unit_price = item.get('price', 0)
            line_total = quantity * unit_price
            table_data.append([
                str(idx),
                description,
                str(quantity),
                f"{currency_symbol} {unit_price:,.2f}",
                f"{currency_symbol} {line_total:,.2f}"
            ])
        
        items_table = Table(table_data, colWidths=[0.3*inch, 3.5*inch, 0.7*inch, 1.2*inch, 1.2*inch])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f4f6')]),
        ]))
        elements.append(items_table)
        
        elements.append(Spacer(1, 20))
    
    # Totals
    totals_data = []
    totals_data.append(['', 'Subtotal:', f"{currency_symbol} {subtotal:,.2f}"])
    if discount_percent > 0:
        totals_data.append(['', f'Discount ({discount_percent}%):', f"- {currency_symbol} {discount_amount:,.2f}"])
    if tax_percent > 0:
        totals_data.append(['', f'Tax ({tax_percent}%):', f"{currency_symbol} {tax_amount:,.2f}"])
    totals_data.append(['', 'TOTAL:', f"{currency_symbol} {total:,.2f}"])
    
    totals_table = Table(totals_data, colWidths=[3.5*inch, 2*inch, 1.5*inch])
    totals_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('FONTNAME', (1, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (1, -1), (-1, -1), 2, colors.black),
        ('FONTSIZE', (1, -1), (-1, -1), 14),
    ]))
    elements.append(totals_table)
    
    elements.append(Spacer(1, 30))
    
    # Notes
    if notes:
        elements.append(Paragraph("Notes", heading_style))
        elements.append(Paragraph(f"<font size='10'>{notes}</font>", normal_style))
        elements.append(Spacer(1, 20))
    
    # Terms and conditions
    elements.append(Paragraph("Terms & Conditions", heading_style))
    terms = [
        "1. This quotation is valid until the date specified above.",
        "2. Prices are exclusive of applicable taxes unless stated otherwise.",
        "3. Payment terms: 50% advance, 50% on delivery/installation.",
        "4. Installation and training included within the quoted price.",
        "5. Technical support provided as per agreement."
    ]
    for term in terms:
        elements.append(Paragraph(f"<font size='10'>{term}</font>", normal_style))
    
    elements.append(Spacer(1, 30))
    
    # Footer
    elements.append(Paragraph("<i>Thank you for your business!</i>", ParagraphStyle('Footer', parent=normal_style, alignment=1)))
    
    # Build PDF
    doc.build(elements)
    
    # Return PDF
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'quotation_{quotation_number}.pdf',
        mimetype='application/pdf'
    )

@quotation_bp.route('/api/quotation/items', methods=['GET'])
@csrf.exempt
@login_required
def get_quotation_items():
    """Get predefined items for quotation (POS software packages)."""
    # Default POS packages - can be customized
    items = [
        {
            'id': 1,
            'name': 'POS Software License (Single Store)',
            'description': 'Complete POS software license for single store location',
            'price': 25000,
            'quantity': 1
        },
        {
            'id': 2,
            'name': 'POS Software License (Multi-Store)',
            'description': 'Complete POS software license for multiple store locations',
            'price': 50000,
            'quantity': 1
        },
        {
            'id': 3,
            'name': 'Cloud/Server Setup',
            'description': 'Cloud or local server setup and configuration',
            'price': 15000,
            'quantity': 1
        },
        {
            'id': 4,
            'name': 'Installation & Training',
            'description': 'On-site installation and staff training',
            'price': 10000,
            'quantity': 1
        },
        {
            'id': 5,
            'name': 'Hardware Setup (Per Terminal)',
            'description': 'Hardware installation and configuration per terminal',
            'price': 5000,
            'quantity': 1
        },
        {
            'id': 6,
            'name': 'Annual Support & Maintenance',
            'description': 'Annual technical support and software maintenance',
            'price': 12000,
            'quantity': 1
        },
        {
            'id': 7,
            'name': 'Barcode Scanner',
            'description': 'Handheld barcode scanner',
            'price': 3500,
            'quantity': 1
        },
        {
            'id': 8,
            'name': 'Receipt Printer',
            'description': 'Thermal receipt printer',
            'price': 8000,
            'quantity': 1
        },
        {
            'id': 9,
            'name': 'Cash Drawer',
            'description': 'Cash drawer with drawer kick',
            'price': 4500,
            'quantity': 1
        },
        {
            'id': 10,
            'name': 'Weighing Scale',
            'description': 'Digital weighing scale for products sold by weight',
            'price': 12000,
            'quantity': 1
        }
    ]
    
    return jsonify(items)

def get_setting(category, key, default=''):
    """Helper function to get setting value."""
    company_id = get_company_id()
    setting = Setting.query.filter(
        Setting.setting_category == category,
        Setting.setting_key == key,
        Setting.company_id == company_id
    ).first()
    return setting.setting_value if setting else default
