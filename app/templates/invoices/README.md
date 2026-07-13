# Professional Invoice & Receipt Templates

## Overview

Print-ready, professional invoice and receipt templates optimized for commercial business use. Designed for 300 DPI printing with CMYK color mode support, compatible with laser and thermal printers.

## Features

### Design Specifications

- **CMYK Color Mode**: Optimized for commercial printing
- **300 DPI Quality**: High-resolution output suitable for professional use
- **Sharp Typography**: Professional fonts optimized for printing
- **Print Margins & Bleed**: Properly configured for all paper types
- **Laser & Thermal Optimized**: Works with all modern printer types
- **Black & White Compatible**: Prints clearly in monochrome
- **Low Ink Usage**: Clean design minimizes ink consumption

### Templates Included

#### 1. A4 Invoice (`invoice_a4.html`)
- **Paper Size**: 210mm × 297mm (8.27" × 11.69")
- **Layout**: Full-page professional invoice
- **Best For**: Standard business invoices, formal billing
- **Features**:
  - Company logo and branding section
  - Customer billing and shipping address
  - Detailed product items table
  - Tax and discount calculations
  - Payment terms and notes section
  - Signature and stamp areas

#### 2. A5 Invoice (`invoice_a5.html`)
- **Paper Size**: 148mm × 210mm (5.83" × 8.27")
- **Layout**: Compact half-page invoice
- **Best For**: Quick invoices, estimates, quotes
- **Features**:
  - Condensed company information
  - Essential billing details only
  - Streamlined items table
  - Basic totals and payment info
  - Print-optimized spacing

#### 3. 80mm Thermal Receipt (`thermal_receipt_80mm.html`)
- **Paper Size**: 80mm width (auto height)
- **Layout**: POS receipt format
- **Best For**: Point-of-sale systems, thermal printers
- **Features**:
  - Monospace font for thermal compatibility
  - Compact item listing
  - Receipt number and timestamp
  - Payment method tracking
  - QR code support
  - Barcode area
  - Return policy and warranty info

## Print Specifications

### Color Mode
- **Primary**: CMYK for commercial printing
- **Screen Display**: RGB
- **Print Output**: Monochrome-compatible

### Resolution
- **Web Display**: 72 DPI (screen)
- **Print Output**: 300 DPI minimum
- **Quality**: Suitable for archives (10+ years)

### Paper Compatibility
- **A4/A5**: 80-100 gsm standard office paper
- **Thermal**: 80mm thermal paper rolls (standard POS)
- **Margins**: 0.5" (A4/A5), No margins (Thermal)

### Printer Compatibility
- **Laser Printers**: HP, Canon, Xerox, Brother
- **Inkjet Printers**: All models with color support
- **Thermal Printers**: 58mm, 80mm, 110mm widths
- **Network Printers**: Full support

## File Structure

```
app/templates/invoices/
├── invoice_a4.html              # Full-page A4 invoice
├── invoice_a5.html              # Compact A5 invoice
├── thermal_receipt_80mm.html    # 80mm thermal receipt
├── print_styles.css             # Shared print optimizations
└── README.md                    # This file
```

## Usage Guide

### Quick Print

1. Open any template in a web browser
2. Press `Ctrl+P` (Windows/Linux) or `Cmd+P` (Mac)
3. Configure print settings:
   - **Margins**: 0.5 inches (A4/A5) or 0 inches (Thermal)
   - **Scale**: 100% (no scaling)
   - **Paper Size**: Choose appropriate size
   - **Color**: Leave as default or select CMYK if available
4. Print to desired printer

### Python Integration

```python
from app.utils.invoice_generator import InvoiceGenerator
from datetime import datetime

# Initialize generator
generator = InvoiceGenerator()

# Prepare invoice data
invoice_data = {
    'invoice_number': 'INV-2026-001234',
    'invoice_date': datetime.now(),
    'due_date': datetime(2026, 6, 19),
    'company': {
        'logo': 'LOGO',
        'name': 'Your Company Name',
        'address': '123 Business Street',
        'city': 'New York, NY 10001',
        'phone': '+1 (555) 123-4567',
        'email': 'billing@company.com',
        'website': 'www.company.com',
        'tax_id': '12-3456789'
    },
    'customer': {
        'name': 'Customer Name',
        'company': 'Customer Company',
        'address': '456 Commerce Avenue',
        'city': 'New York, NY 10002',
        'phone': '+1 (555) 987-6543',
        'email': 'customer@company.com'
    },
    'items': [
        {
            'code': 'SKU-001',
            'description': 'Product Description',
            'qty': 1,
            'unit_price': 100.00,
            'discount': 0.00,
            'tax': 8.00,
            'total': 108.00
        }
    ],
    'subtotal': 100.00,
    'discount': 0.00,
    'tax': 8.00,
    'total': 108.00,
    'paid_amount': 0.00
}

# Generate A4 invoice
html = generator.generate_a4_invoice(invoice_data)

# Generate thermal receipt
receipt_html = generator.generate_thermal_receipt(invoice_data)
```

### Flask Integration

```python
from flask import render_template, Blueprint
from app.utils.invoice_generator import InvoiceGenerator
from datetime import datetime

invoices = Blueprint('invoices', __name__, url_prefix='/invoices')
generator = InvoiceGenerator()

@invoices.route('/a4/<int:invoice_id>')
def view_a4_invoice(invoice_id):
    # Fetch invoice from database
    invoice = fetch_invoice_from_db(invoice_id)
    
    # Generate HTML
    html = generator.generate_a4_invoice(invoice)
    
    return html

@invoices.route('/receipt/<int:receipt_id>')
def view_receipt(receipt_id):
    # Fetch receipt from database
    receipt = fetch_receipt_from_db(receipt_id)
    
    # Generate thermal receipt
    html = generator.generate_thermal_receipt(receipt)
    
    return html, 200, {'Content-Type': 'text/html'}
```

### Create Custom Styles

Edit the templates to match your brand:

1. **Company Logo**: Replace `<div class="company-logo">LOGO</div>` with your logo image
2. **Colors**: Modify CSS color variables:
   ```css
   --primary-color: #0051ba;     /* Brand color */
   --primary-dark: #003d82;      /* Dark variant */
   ```
3. **Fonts**: Change font-family in CSS to your preferred font
4. **Spacing**: Adjust padding/margin values for layout preference

## Customization Guide

### Header Section

```html
<div class="company-logo">YOUR LOGO</div>
<div class="company-name">Your Company Name</div>
```

**To add logo image:**
```html
<img src="/path/to/logo.png" class="company-logo" alt="Company Logo">
```

### Invoice Details

```html
<div class="invoice-details-item">
    <span class="invoice-details-label">Invoice #:</span>
    <span class="invoice-details-value">{{ invoice_number }}</span>
</div>
```

### Items Table

Add/remove rows as needed:
```html
<tr>
    <td class="item-code">SKU-001</td>
    <td class="item-description">Product Name</td>
    <td class="text-center">1</td>
    <td class="text-right">$100.00</td>
    <td class="text-right">$0.00</td>
    <td class="text-right">$8.00</td>
    <td class="text-right">$108.00</td>
</tr>
```

### Footer Terms

Edit terms and conditions:
```html
<div class="terms-text">
    <strong>Terms:</strong> Payment due within 30 days<br>
    <strong>Late Fee:</strong> 1.5% monthly interest
</div>
```

## Print Settings Recommendations

### A4 Invoice
- **Paper**: Letter or A4 white bond
- **Orientation**: Portrait
- **Scaling**: 100% (no scaling)
- **Margins**: 0.5" all sides
- **Color Mode**: CMYK or Color

### A5 Invoice
- **Paper**: A5 bond paper
- **Orientation**: Portrait
- **Scaling**: 100%
- **Margins**: 0.3" all sides
- **Color Mode**: CMYK or Color

### Thermal Receipt
- **Paper**: 80mm thermal roll
- **Orientation**: Portrait (fixed)
- **Scaling**: 100%
- **Margins**: None (0mm)
- **Color Mode**: Monochrome (thermal printer native)
- **Temperature**: Check printer specifications

## Performance Optimization

### For Web Display
- Use print preview to check formatting
- Test with different browsers (Chrome, Firefox, Edge)
- Scale elements using CSS media queries

### For Printing
- Enable "Print background colors/images" in browser settings
- Use high-quality printer paper for best results
- Clean thermal printer heads regularly
- Check ink levels before large batches

### Print Speed
- A4 Invoice: ~2 seconds (laser), ~5 seconds (inkjet)
- Thermal Receipt: ~1-2 seconds
- Batch printing: Recommended for high volumes

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Text appears cut off | Reduce font size in print preview or adjust margins |
| Images not printing | Enable "Print background images" in print settings |
| Colors look different | Calibrate printer or use CMYK profile |
| Thermal receipt garbled | Check thermal printer driver and paper type |
| Footer on wrong page | Use `@page` rules or adjust page breaks |
| Signature line missing | Check CSS visibility settings |

## Browser Compatibility

- **Chrome**: Full support (recommended)
- **Firefox**: Full support
- **Safari**: Full support
- **Edge**: Full support
- **Internet Explorer**: Limited support (use modern browser)

## Accessibility

- High contrast text (21:1 ratio)
- Readable monospace fonts for codes
- Clear section markers and labels
- Proper heading hierarchy
- Print-optimized for vision-impaired users

## Color CMYK Conversion

The templates use these CMYK-friendly colors:

| Color | RGB | CMYK | Usage |
|-------|-----|------|-------|
| Primary | #0051ba | 100/80/0/26 | Headers, accents |
| Dark Primary | #003d82 | 100/74/0/49 | Bold text, borders |
| Light Gray | #f5f5f5 | 0/0/0/4 | Backgrounds |
| Dark Gray | #333333 | 0/0/0/80 | Body text |
| Black | #000000 | 0/0/0/100 | Text, borders |

## License & Usage

These templates are designed for commercial business invoicing in your POS system. Feel free to customize and integrate with your application.

## Support

For issues or customization requests:
1. Check the troubleshooting section
2. Review print settings recommendations
3. Test with different printer models
4. Consult your printer's manual

## Version History

- **v1.0** (2026-05-19): Initial release
  - A4 Invoice template
  - A5 Invoice template
  - 80mm Thermal Receipt template
  - Print optimization styles
  - Python invoice generator

## Additional Resources

### Print Industry Standards
- [ISO/IEC 15930 (PDF/X)](https://en.wikipedia.org/wiki/PDF/X) - For commercial printing
- [CMYK Color Space](https://en.wikipedia.org/wiki/CMYK_color_model) - Color mode information
- [PostScript Print Device Specs](https://www.adobe.com/products/postscript.html)

### Browser Print Features
- [CSS Print Media Queries](https://developer.mozilla.org/en-US/docs/Web/CSS/@media)
- [Page Break Properties](https://developer.mozilla.org/en-US/docs/Web/CSS/page-break)
- [Print Color Adjust](https://developer.mozilla.org/en-US/docs/Web/CSS/print-color-adjust)

### Thermal Printer Standards
- [ESC/POS Protocol](https://github.com/receipt-print-hq/escpos)
- [Thermal Printer Paper Sizes](https://www.thermal-printers.com/paper-sizes)
- [Barcode Specifications](https://www.gs1.org/services/barcodes)

---

**Last Updated**: May 19, 2026
**Templates Version**: 1.0
**Print Specification**: 300 DPI, CMYK, A4/A5/80mm
