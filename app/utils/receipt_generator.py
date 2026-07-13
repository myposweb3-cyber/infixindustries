from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from io import BytesIO
import os
from datetime import datetime
from app.models import Setting
import qrcode
from PIL import Image as PILImage

class ReceiptGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        """Set up custom styles for the receipt."""
        # Primary color - deep blue
        self.primary_color = colors.HexColor('#1a365d')
        # Accent color - gold/amber
        self.accent_color = colors.HexColor('#d69e2e')
        # Light gray for backgrounds
        self.light_gray = colors.HexColor('#f7fafc')
        self.border_color = colors.HexColor('#cbd5e0')
        
        self.title_style = ParagraphStyle(
            'Title',
            parent=self.styles['Heading1'],
            fontSize=20,
            spaceAfter=6,
            alignment=1,  # Center alignment
            fontName='Helvetica-Bold',
            textColor=self.primary_color
        )

        self.business_info_style = ParagraphStyle(
            'BusinessInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=2,
            alignment=1,  # Center alignment
            textColor=colors.HexColor('#4a5568')
        )

        self.normal_style = ParagraphStyle(
            'Normal',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=4,
            textColor=colors.HexColor('#2d3748')
        )

        self.small_style = ParagraphStyle(
            'Small',
            parent=self.styles['Normal'],
            fontSize=7,
            spaceAfter=2,
            alignment=1,
            textColor=colors.HexColor('#718096')
        )

        self.bold_style = ParagraphStyle(
            'Bold',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            spaceAfter=4,
            textColor=colors.HexColor('#1a365d')
        )

        self.header_style = ParagraphStyle(
            'Header',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            spaceAfter=4,
            alignment=1,
            textColor=self.primary_color,
            borderPadding=(0, 0, 5, 0),
            borderWidth=0,
            borderColor=self.primary_color,
            border=0
        )

        self.section_style = ParagraphStyle(
            'Section',
            parent=self.styles['Normal'],
            fontSize=8,
            fontName='Helvetica-Bold',
            spaceAfter=3,
            textColor=self.primary_color,
            borderPadding=(0, 0, 3, 0),
            borderWidth=0,
        )

    def _get_business_settings(self):
        """Get business settings from database."""
        settings = {}
        all_settings = Setting.query.all()
        for setting in all_settings:
            if setting.setting_category not in settings:
                settings[setting.setting_category] = {}
            settings[setting.setting_category][setting.setting_key] = setting.setting_value
        return settings

    def _generate_qr_code(self, sale_data, business_settings):
        """Generate QR code for the receipt."""
        try:
            # Business name - ALWAYS use 'receipt' category if available (user updates receipt tab settings)
            qr_business_name = business_settings.get('receipt', {}).get('business_name', '').strip()
            if not qr_business_name:
                qr_business_name = business_settings.get('general', {}).get('business_name', '').strip()
            if not qr_business_name:
                qr_business_name = 'POS System'
            
            # Create QR code content
            qr_content = f"""
Sale Receipt
Receipt #: {sale_data['sale_id']}
Date: {sale_data['date']}
Customer: {sale_data['customer']}
Total: ₨ {sale_data['total']:.2f}
Payment: {sale_data['payment']}
Business: {qr_business_name}
""".strip()

            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=3,
                border=1,
            )
            qr.add_data(qr_content)
            qr.make(fit=True)

            # Create image
            qr_image = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to bytes
            buffer = BytesIO()
            qr_image.save(buffer, format='PNG')
            buffer.seek(0)
            
            return buffer
        except Exception as e:
            print(f"Error generating QR code: {e}")
            return None

    def generate_receipt(self, sale_data, business_settings=None):
        """
        Generate a professional PDF receipt for a sale.

        Args:
            sale_data (dict): Sale information including items, totals, etc.
            business_settings (dict): Business configuration settings

        Returns:
            BytesIO: PDF content as bytes
        """
        buffer = BytesIO()

        # Use default settings if not provided
        if business_settings is None:
            business_settings = self._get_business_settings()

        # Get receipt-specific settings
        receipt_settings = business_settings.get('receipt', {})
        
        # Create the PDF document (80mm thermal receipt width)
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(80*mm, 300*mm),  # Thermal receipt width, variable height
            rightMargin=5*mm,
            leftMargin=5*mm,
            topMargin=5*mm,
            bottomMargin=5*mm
        )

        # Build the receipt content
        story = []

        # ===== HEADER SECTION =====
        # Logo - Check if show_logo is enabled in printing settings
        show_logo = business_settings.get('printing', {}).get('show_logo', 'true').lower() == 'true'
        if show_logo:
            logo_path = business_settings.get('general', {}).get('logo_path', '')
            if logo_path:
                try:
                    from flask import current_app
                    # Get the project root (parent of app folder)
                    project_root = os.path.dirname(current_app.root_path)
                    # Build the full path - logo_path starts with /static/
                    full_logo_path = os.path.join(project_root, logo_path.lstrip('/'))
                    
                    # Also check app/static/uploads as fallback
                    app_static_path = os.path.join(current_app.root_path, 'static/uploads', os.path.basename(logo_path))
                    
                    if os.path.exists(full_logo_path):
                        logo = Image(full_logo_path, width=40*mm, height=20*mm)
                        logo.hAlign = 'CENTER'
                        story.append(logo)
                        story.append(Spacer(1, 3))
                    elif os.path.exists(app_static_path):
                        logo = Image(app_static_path, width=40*mm, height=20*mm)
                        logo.hAlign = 'CENTER'
                        story.append(logo)
                        story.append(Spacer(1, 3))
                    else:
                        print(f"Logo file not found at: {full_logo_path} or {app_static_path}")
                except Exception as e:
                    print(f"Error loading logo: {e}")

        # Business Name - ALWAYS use 'receipt' category if available (user updates receipt tab settings)
        # Only fall back to 'general' if receipt is empty AND general is not empty
        business_name = business_settings.get('receipt', {}).get('business_name', '').strip()
        if not business_name:
            # Fallback to general only if receipt is truly empty
            business_name = business_settings.get('general', {}).get('business_name', '').strip()
        if not business_name:
            # Final fallback to default
            business_name = 'POS System'
        story.append(Paragraph(business_name, self.title_style))

        # Business Address
        business_address = receipt_settings.get('business_address', '')
        if business_address:
            story.append(Paragraph(business_address, self.business_info_style))

        # Business Phone
        business_phone = receipt_settings.get('business_phone', '')
        if business_phone:
            story.append(Paragraph(f"Phone: {business_phone}", self.business_info_style))

        # Business Email
        business_email = receipt_settings.get('business_email', '')
        if business_email:
            story.append(Paragraph(f"Email: {business_email}", self.business_info_style))

        # Business GST/Tax Number
        business_gst = receipt_settings.get('business_gst', '')
        if business_gst:
            story.append(Paragraph(f"GST/Tax #: {business_gst}", self.business_info_style))

        story.append(Spacer(1, 5))

        # Professional double-line divider
        story.append(Paragraph("═══════════════════════════════════", self.small_style))
        story.append(Spacer(1, 3))

        # ===== RECEIPT INFO =====
        # Receipt Number and Date/Time
        receipt_info = [
            [Paragraph(f"<b>Receipt #</b>", self.normal_style), Paragraph(f"{sale_data['sale_id']}", self.bold_style)],
            [Paragraph(f"<b>Date</b>", self.normal_style), Paragraph(f"{sale_data['date']}", self.normal_style)],
            [Paragraph(f"<b>Time</b>", self.normal_style), Paragraph(f"{sale_data.get('time', '')}", self.normal_style)],
        ]
        
        receipt_table = Table(receipt_info, colWidths=[25*mm, 40*mm])
        receipt_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(receipt_table)
        story.append(Spacer(1, 5))

        # Customer Name
        if sale_data.get('customer'):
            story.append(Paragraph(f"<b>Customer:</b> {sale_data['customer']}", self.normal_style))

        # Divider
        story.append(Paragraph("───────────────────────────────────", self.small_style))
        story.append(Spacer(1, 5))

        # ===== ITEMS SECTION =====
        story.append(Paragraph("ITEMS PURCHASED", self.header_style))
        story.append(Spacer(1, 3))

        # Items header
        items_header = [
            Paragraph("<b>Item</b>", self.normal_style),
            Paragraph("<b>Qty</b>", self.normal_style),
            Paragraph("<b>Price</b>", self.normal_style),
            Paragraph("<b>Total</b>", self.normal_style)
        ]
        
        items_table_data = [items_header]
        
        for item in sale_data['items']:
            items_table_data.append([
                item['name'][:25],  # Truncate long names
                str(item['quantity']),
                f"₨{item['price']:.2f}",
                f"₨{item['total']:.2f}"
            ])

        # Create items table with professional styling
        items_table = Table(items_table_data, colWidths=[28*mm, 10*mm, 16*mm, 16*mm])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.3, self.border_color),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.light_gray]),
        ]))
        story.append(items_table)
        story.append(Spacer(1, 8))

        # ===== TOTALS SECTION =====
        story.append(Paragraph("───────────────────────────────────", self.small_style))
        story.append(Spacer(1, 3))

        # Calculate tax amount correctly: total - (subtotal_before - discount_total)
        discount_total = sale_data.get('discount_total', sale_data.get('discount', 0) or 0)
        taxable_base = max(0.0, sale_data.get('subtotal', 0) - discount_total)
        tax_amount = max(0.0, sale_data.get('total', 0) - (sale_data.get('subtotal', 0) - discount_total))

        # Check if show_tax_in_sales setting is enabled (default to True)
        show_tax_in_sales = business_settings.get('tax', {}).get('show_tax_in_sales', 'true').lower() == 'true'
        
        totals_data = [
            [Paragraph("Subtotal:", self.normal_style), Paragraph(f"₨ {sale_data.get('subtotal', 0):.2f}", self.normal_style)],
        ]

        # Only show tax if enabled and tax amount > 0
        if show_tax_in_sales and tax_amount > 0:
            totals_data.append([
                Paragraph(f"Tax ({sale_data.get('tax_rate', 18)}%)", self.normal_style), 
                Paragraph(f"₨ {tax_amount:.2f}", self.normal_style)
            ])

        # Show discount if any (per-item discounts aggregated or overall sale discount)
        if discount_total and discount_total > 0:
            totals_data.append([
                Paragraph("Discount", self.normal_style), 
                Paragraph(f"-₨ {discount_total:.2f}", self.normal_style)
            ])

        # Grand Total - highlighted with background
        totals_data.append([
            Paragraph("<b>GRAND TOTAL</b>", self.bold_style), 
            Paragraph(f"<b>₨ {sale_data['total']:.2f}</b>", self.bold_style)
        ])

        totals_table = Table(totals_data, colWidths=[40*mm, 30*mm])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -2), 9),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, -1), (-1, -1), self.primary_color),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.white),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))
        story.append(totals_table)
        story.append(Spacer(1, 8))

        # ===== PAYMENT INFO =====
        story.append(Paragraph("───────────────────────────────────", self.small_style))
        story.append(Spacer(1, 3))

        payment_data = [
            [Paragraph("<b>Payment Method</b>", self.normal_style), Paragraph(f"{sale_data['payment']}", self.bold_style)],
        ]

        if sale_data.get('payment') == 'Cash':
            payment_data.append([
                Paragraph("Cash Tendered", self.normal_style), 
                Paragraph(f"₨ {sale_data.get('cash_given', 0):.2f}", self.normal_style)
            ])
            
            change = sale_data.get('cash_given', 0) - sale_data.get('total', 0)
            if change > 0:
                payment_data.append([
                    Paragraph("<b>Change</b>", self.bold_style), 
                    Paragraph(f"<b>₨ {change:.2f}</b>", self.bold_style)
                ])

        payment_table = Table(payment_data, colWidths=[35*mm, 35*mm])
        payment_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(payment_table)
        story.append(Spacer(1, 10))

        # ===== QR CODE =====
        if receipt_settings.get('show_qr_code', 'true').lower() == 'true':
            qr_buffer = self._generate_qr_code(sale_data, business_settings)
            if qr_buffer:
                qr_image = Image(qr_buffer, width=22*mm, height=22*mm)
                qr_image.hAlign = 'CENTER'
                story.append(qr_image)
                story.append(Spacer(1, 3))
                story.append(Paragraph("Scan for digital receipt", self.small_style))
                story.append(Spacer(1, 8))

        # ===== WARRANTY INFO =====
        warranty_info = receipt_settings.get('warranty_info', '')
        if warranty_info:
            story.append(Paragraph("───────────────────────────────────", self.small_style))
            story.append(Spacer(1, 3))
            story.append(Paragraph("<b>WARRANTY & RETURNS</b>", self.small_style))
            story.append(Paragraph(warranty_info, self.small_style))
            story.append(Spacer(1, 5))

        # ===== FOOTER =====
        story.append(Paragraph("═══════════════════════════════════", self.small_style))
        story.append(Spacer(1, 5))

        # Thank you message
        thank_you = receipt_settings.get('thank_you_message', 'Thank you for your business!')
        story.append(Paragraph(f"<b>{thank_you}</b>", self.small_style))
        
        # Footer text
        footer = receipt_settings.get('footer_text', 'Generated by POS System')
        story.append(Paragraph(footer, self.small_style))

        # ===== BUILD PDF =====
        doc.build(story)

        buffer.seek(0)
        return buffer

    def generate_receipt_from_sale(self, sale, items, business_settings=None):
        """
        Generate receipt from Sale model instance.

        Args:
            sale: Sale model instance
            items: List of SaleItem instances
            business_settings: Business settings dict

        Returns:
            BytesIO: PDF content
        """
        # Format date and time
        date_str = sale.date.strftime('%Y-%m-%d')
        time_str = sale.date.strftime('%H:%M:%S')
        
        sale_data = {
            'sale_id': sale.id,
            'date': date_str,
            'time': time_str,
            'customer': sale.customer,
            'items': [],
            # 'subtotal' will be the pre-discount subtotal (sum of unit_price * qty)
            'subtotal': 0.0,
            'total': sale.total,
            # overall sale discount (if any); per-item discounts aggregated below into discount_total
            'discount': getattr(sale, 'discount', 0) or 0,
            'discount_total': 0.0,
            'payment': sale.payment if hasattr(sale, 'payment') else 'Cash',
            'cash_given': getattr(sale, 'cash_given', 0) or 0,
            'balance': getattr(sale, 'balance', 0) or 0,
            'tax_rate': 18,  # Default tax rate
            'tax_total': 0.0
        }

        for item in items:
            qty = item.quantity
            unit_price = item.price
            item_discount = getattr(item, 'discount', 0) or 0
            item_tax = getattr(item, 'tax', 0) or 0
            item_price_before = unit_price * qty
            item_total = item_price_before - item_discount + item_tax

            item_data = {
                'name': item.product.name if item.product else 'Unknown',
                'quantity': qty,
                'price': unit_price,
                'discount': item_discount,
                'tax_amount': item_tax,
                'total': item_total
            }
            sale_data['items'].append(item_data)
            sale_data['subtotal'] += item_price_before
            sale_data['discount_total'] += item_discount
            sale_data['tax_total'] += item_tax

        # Include any overall sale.discount (if set) in discount_total
        sale_data['discount_total'] = sale_data.get('discount_total', 0.0) + (sale_data.get('discount', 0.0) or 0.0)

        # Calculate tax rate from totals (relative to taxable base)
        taxable_base = max(0.0, sale_data['subtotal'] - sale_data['discount_total'])
        if sale_data['tax_total'] > 0 and taxable_base > 0:
            sale_data['tax_rate'] = round((sale_data['tax_total'] / taxable_base) * 100, 2)

        return self.generate_receipt(sale_data, business_settings)
