# Professional Print-Ready Invoice & Receipt Templates

## 📋 Overview

This package contains enterprise-grade, print-ready invoice and receipt templates optimized for professional business use. All templates are designed to meet commercial printing standards with CMYK color mode support, 300 DPI high resolution, and compatibility with both laser and thermal printers.

## 📁 Template Files

### 1. **A4 Invoice (Professional)**
- **File:** `invoice_a4_cmyk.html`
- **Size:** 210mm × 297mm (Standard A4)
- **Best For:** Corporate invoices, professional billing, multi-page documents
- **Features:**
  - Full-page layout with proper margins (12.7mm)
  - Dedicated company header with logo
  - Separate customer and ship-to sections
  - Detailed item table with 7 columns
  - Comprehensive totals section
  - Professional footer with T&C, signature, and stamp areas
  - Watermark background (non-intrusive)

### 2. **A5 Invoice (Compact)**
- **File:** `invoice_a5_cmyk.html`
- **Size:** 148mm × 210mm (Half-page)
- **Best For:** Compact invoices, printing multiple per page, quick reference
- **Features:**
  - Space-efficient layout (10mm margins)
  - Condensed company header
  - Streamlined item table with 6 columns
  - Simplified footer with essential info
  - Optimized for printing 2 invoices per A4 sheet

### 3. **80mm Thermal Receipt**
- **File:** `thermal_receipt_80mm_cmyk.html`
- **Size:** 80mm width (continuous feed)
- **Best For:** Point of Sale (POS), instant receipts, thermal printers
- **Features:**
  - Monochrome optimized for thermal printers
  - Fast print optimization with minimal formatting
  - QR code support for invoice reference
  - Compact item listing with essential info
  - Receipt number and cashier tracking
  - Professional footer with terms and thank you message

### 4. **Universal Print Stylesheet**
- **File:** `print_styles_cmyk_300dpi.css`
- **Purpose:** Common printing styles for all templates
- **Features:**
  - CMYK color mode optimization
  - 300 DPI print quality settings
  - Grayscale compatibility
  - Print-specific margins and page breaks
  - Font optimization for readability

---

## 🎨 Design Specifications

### Color Mode: CMYK
- **Purpose:** Professional printing standard
- **Compatibility:** All commercial printers
- **Black Text:** Pure K (Key) = 100 for maximum contrast
- **Grays:** 
  - Dark: K=20 (header backgrounds)
  - Medium: K=30 (totals section)
  - Light: K=5 (alternating rows)

### Resolution: 300 DPI
- **Quality Level:** Professional grade (suitable for framing)
- **Font Rendering:** Sharp and crisp
- **Image Quality:** High detail
- **Print Device:** Laser and thermal printers

### Typography
- **Primary Font:** Segoe UI / Helvetica Neue / Arial (professional sans-serif)
- **Monospace Font:** Courier New (for numbers and codes)
- **Font Sizes:**
  - Invoice titles: 18-22pt
  - Headers: 14-16pt
  - Body text: 8.5-9pt
  - Details: 7-8pt
  - Tables: 7.5-9pt
  - Receipt text: 6.5-10pt

### Margins & Bleed
- **A4 Document:** 12.7mm margins + 3mm bleed area
- **A5 Document:** 10mm margins
- **Thermal Receipt:** 2-3mm padding (no bleed)

---

## 📐 Layout Sections

### Header Section
```
┌─────────────────────────────────────┐
│ [LOGO] Company Name   │  INVOICE #  │
│ Address               │  Date       │
│ Phone, Email, Tax ID  │  Due Date   │
└─────────────────────────────────────┘
```

### Billing Section
```
┌──────────────────┬──────────────────┐
│ BILL TO          │ SHIP TO          │
│ Customer Name    │ Company Name     │
│ Address          │ Address          │
│ Phone, Email     │ Details          │
└──────────────────┴──────────────────┘
```

### Items Table
```
┌─────┬────────────┬─────┬───────┬───────┬─────┬───────┐
│Code │Description │ Qty │ Price │Discount│Tax │ Total │
├─────┼────────────┼─────┼───────┼───────┼─────┼───────┤
│ SKU │ Product    │  1  │$100.00│ $0.00 │$8  │$108.00│
└─────┴────────────┴─────┴───────┴───────┴─────┴───────┘
```

### Totals Section
```
                    Subtotal:    $5,150.00
                    Discount:     -$315.00
                    Tax:           $386.80
                    ──────────────────────
                    TOTAL DUE:   $5,221.80
                    Paid Amount:    $0.00
                    BALANCE DUE: $5,221.80
```

### Footer Section
```
┌──────────────────┬──────────────┬──────────────┬─────────────┐
│ Terms & Cond.    │ Thank You!   │ Authorized By│ Stamp Area  │
│ • Net 30 days    │              │              │             │
│ • 1.5% interest  │              │ __________   │ ┌─────────┐ │
│ • Full details   │              │ Name & Title │ │COMPANY  │ │
│                  │              │              │ │ STAMP   │ │
└──────────────────┴──────────────┴──────────────┴─────────────┘
```

---

## 🖨️ Printer Compatibility

### Laser Printers
✓ Full CMYK color support  
✓ High resolution (600+ DPI)  
✓ Multiple page sizes (A4, A5)  
✓ Large paper capacity  
✓ Fast printing speed

### Thermal Printers (POS)
✓ Monochrome optimized  
✓ 203-300 DPI native resolution  
✓ 80mm roll width  
✓ Continuous feed  
✓ Fast printing (150-500mm/sec)

### Inkjet Printers
✓ CMYK color mode  
✓ Suitable for small volume  
✓ Good for color branding  
⚠️ Higher ink consumption

---

## 🎯 Usage Instructions

### In Your Flask App

#### 1. **Rendering A4 Invoice**
```python
@app.route('/invoice/<int:invoice_id>/print-a4')
def print_invoice_a4(invoice_id):
    invoice = Invoice.query.get(invoice_id)
    company = invoice.company
    customer = invoice.customer
    return render_template('invoices/invoice_a4_cmyk.html',
                         invoice=invoice,
                         company=company,
                         customer=customer)
```

#### 2. **Rendering A5 Invoice**
```python
@app.route('/invoice/<int:invoice_id>/print-a5')
def print_invoice_a5(invoice_id):
    invoice = Invoice.query.get(invoice_id)
    company = invoice.company
    customer = invoice.customer
    return render_template('invoices/invoice_a5_cmyk.html',
                         invoice=invoice,
                         company=company,
                         customer=customer)
```

#### 3. **Rendering Thermal Receipt**
```python
@app.route('/receipt/<int:receipt_id>/print-thermal')
def print_receipt_thermal(receipt_id):
    receipt = Receipt.query.get(receipt_id)
    company = receipt.company
    customer = receipt.customer
    return render_template('invoices/thermal_receipt_80mm_cmyk.html',
                         receipt=receipt,
                         company=company,
                         customer=customer)
```

### Printing Steps

#### **From Browser**
1. Navigate to invoice/receipt URL
2. Press `Ctrl+P` (or `Cmd+P` on Mac)
3. **Printer Settings:**
   - Orientation: Portrait (A4, A5) or Continuous (80mm)
   - Paper Size: A4 / A5 / Custom 80mm
   - Margins: None (templates include margins)
   - Color Mode: CMYK or Grayscale
   - Quality: Maximum / 300 DPI if available
4. Click **Print**

#### **PDF Export**
1. Printer: "Save as PDF"
2. Quality: Maximum
3. Compression: None
4. Color Space: CMYK (if available)
5. Save and send to professional printer

#### **Direct Thermal Print (POS)**
1. Select thermal receipt template
2. Printer: Thermal Receipt Printer (ESC/POS)
3. Orientation: Portrait
4. Paper: 80mm
5. Quality: Thermal Optimized

---

## 🎨 Customization Guide

### Changing Company Colors
Edit the hex colors in each template's `<style>` section:
```html
/* Change primary brand color from black to your color */
.company-logo {
    background: linear-gradient(135deg, #YourColor1 0%, #YourColor2 100%);
}
```

### Adding Company Logo Image
Replace text logo with actual logo:
```html
<!-- Replace this: -->
<div class="company-logo">{{ company.code or 'LOGO' }}</div>

<!-- With this: -->
<img src="{{ url_for('static', filename='uploads/company_logo.png') }}" 
     class="company-logo-img" alt="Logo">
```

### Adjusting Font Sizes
Edit the font-size properties:
```css
.invoice-title {
    font-size: 22pt;  /* Change this */
}
```

### Modifying Layout Spacing
Adjust margins and padding:
```css
.header {
    margin-bottom: 12mm;  /* Increase/decrease space */
    padding-bottom: 10mm;
}
```

### Custom Footer Text
Update footer content:
```html
<p><strong>Terms:</strong> Custom payment terms here</p>
<p><strong>Contact:</strong> Your contact info</p>
```

---

## ✨ Professional Features

### 1. **Watermark Background**
- Non-intrusive company branding
- Subtle "INVOICE" or "RECEIPT" text
- Doesn't interfere with readability
- Optional (can be disabled in print)

### 2. **QR Code Support**
- Receipt includes automatic QR code generation
- Links to invoice details
- Requires qrcode.js library
- Optional barcode generation

### 3. **Payment Status Tracking**
- Status badge (Pending/Paid)
- Paid amount vs. balance due
- Visual hierarchy for important amounts

### 4. **Professional Dividers**
- Solid borders for section separation
- Dashed lines for visual breaks
- Print-friendly line weights

### 5. **Signature & Stamp Areas**
- Designated spaces for authorization
- Professional alignment
- Clearly marked sections

---

## 🔧 Troubleshooting

### Issue: Colors look different when printing
**Solution:** 
- Ensure CMYK mode is selected in printer settings
- Check that "Color Management" is set to automatic
- Use "Exact Colors" printing option

### Issue: Text is blurry
**Solution:**
- Increase print quality to 300 DPI
- Check browser zoom is set to 100%
- Try exporting to PDF first, then print

### Issue: Page breaks in wrong places
**Solution:**
- Don't print with browser scaling
- Check margins are set to "None"
- Templates have built-in print optimization

### Issue: Thermal receipt not printing correctly
**Solution:**
- Select 80mm thermal printer from device list
- Set orientation to Portrait
- Disable margins/scaling
- Test with ESC/POS driver

### Issue: Images not printing
**Solution:**
- Ensure image files are accessible
- Use absolute URLs if using external CDN
- Test with simple SVG backgrounds first

---

## 📊 Performance & Quality Metrics

| Metric | Standard | Professional |
|--------|----------|--------------|
| DPI | 72-150 | **300** |
| Color Mode | RGB | **CMYK** |
| Font Quality | Screen | **Print Optimized** |
| Margins | None | **12.7mm + 3mm Bleed** |
| Ink Usage | Standard | **Optimized Low** |
| Printer Support | Limited | **Laser + Thermal** |
| Commercial Grade | ✗ | **✓** |

---

## 📝 Template Data Requirements

### Invoice Object Required Fields
```python
invoice.invoice_number    # "INV-2024-001"
invoice.date              # "May 21, 2024"
invoice.due_date          # "June 20, 2024"
invoice.status            # "Pending" or "Paid"
invoice.subtotal          # 5150.00
invoice.discount          # 315.00
invoice.tax               # 386.80
invoice.total             # 5221.80
invoice.paid_amount       # 0.00
invoice.balance           # 5221.80
invoice.items             # List of line items
```

### Company Object Required Fields
```python
company.name              # "Your Company Inc."
company.address           # "123 Business St"
company.city              # "Business City"
company.phone             # "+1-555-0123"
company.email             # "info@company.com"
company.website           # "www.company.com"
company.tax_id            # "TAX123456789"
company.code              # "YCI" (for logo)
```

### Customer Object Required Fields
```python
customer.name             # "John Doe"
customer.company          # "ABC Corporation"
customer.address          # "456 Client Ave"
customer.city             # "Client City"
customer.phone            # "+1-555-9876"
customer.email            # "john@abc.com"
```

---

## 🚀 Best Practices

### ✓ DO:
- Use 300 DPI print quality
- Set CMYK color mode
- Disable scaling/margins in print dialog
- Test print on target printer first
- Use monospace fonts for numbers
- Include all required company info
- Maintain 12.7mm margins on A4

### ✗ DON'T:
- Print with browser scaling enabled
- Use RGB color mode
- Enable "fit to page" option
- Print with borders or headers
- Use display fonts for body text
- Omit company branding
- Print at reduced DPI

---

## 📞 Support & Maintenance

### File Locations
- Templates: `/app/templates/invoices/`
- Styles: `/app/templates/invoices/print_styles_cmyk_300dpi.css`
- Static Assets: `/app/static/uploads/`

### Regular Updates
- Test with new printer models quarterly
- Update CMYK color profiles annually
- Review font rendering with browser updates
- Update paper size standards as needed

---

## 📄 License & Usage

These templates are designed for professional business use. You may:
- ✓ Customize with your company branding
- ✓ Use with your Flask application
- ✓ Print and distribute invoices/receipts
- ✓ Export to PDF for archival

You should:
- ✓ Maintain proper margins and spacing
- ✓ Include all required legal information
- ✓ Use for legitimate business purposes
- ✓ Test before production use

---

**Version:** 1.0.0  
**Created:** May 21, 2024  
**Last Updated:** May 21, 2024  
**Format:** Professional CMYK 300 DPI  
**Printer Support:** Laser & Thermal  

---

For questions or customization needs, refer to the template HTML files directly or contact your development team.
