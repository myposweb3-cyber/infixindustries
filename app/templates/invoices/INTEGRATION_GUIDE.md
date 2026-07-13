# Flask Integration Guide - Professional Invoice Templates

## 🔧 Quick Integration Steps

### Step 1: Update Your Routes

Add these endpoints to your `app/routes/invoices.py` or main routes file:

```python
from flask import render_template, url_for, abort
from app.models import Invoice, Receipt, Company, Customer

# ===== A4 PROFESSIONAL INVOICE =====
@app.route('/invoice/<int:invoice_id>/print-a4')
@login_required
def print_invoice_a4(invoice_id):
    """Print invoice in professional A4 format (CMYK 300 DPI)"""
    invoice = Invoice.query.get_or_404(invoice_id)
    
    # Permission check
    if not can_access_invoice(invoice):
        abort(403)
    
    return render_template('invoices/invoice_a4_cmyk.html',
                         invoice=invoice,
                         company=invoice.company,
                         customer=invoice.customer)

# ===== A5 COMPACT INVOICE =====
@app.route('/invoice/<int:invoice_id>/print-a5')
@login_required
def print_invoice_a5(invoice_id):
    """Print invoice in compact A5 format (CMYK 300 DPI)"""
    invoice = Invoice.query.get_or_404(invoice_id)
    
    if not can_access_invoice(invoice):
        abort(403)
    
    return render_template('invoices/invoice_a5_cmyk.html',
                         invoice=invoice,
                         company=invoice.company,
                         customer=invoice.customer)

# ===== 80MM THERMAL RECEIPT =====
@app.route('/receipt/<int:receipt_id>/print-thermal')
@login_required
def print_receipt_thermal(receipt_id):
    """Print receipt in 80mm thermal format (POS)"""
    receipt = Receipt.query.get_or_404(receipt_id)
    
    if not can_access_receipt(receipt):
        abort(403)
    
    return render_template('invoices/thermal_receipt_80mm_cmyk.html',
                         receipt=receipt,
                         company=receipt.company,
                         customer=receipt.customer)

# Helper function
def can_access_invoice(invoice):
    """Check if user can access this invoice"""
    if current_user.is_super_admin():
        return True
    if invoice.company_id == session.get('company_id'):
        return True
    return False

def can_access_receipt(receipt):
    """Check if user can access this receipt"""
    if current_user.is_super_admin():
        return True
    if receipt.company_id == session.get('company_id'):
        return True
    return False
```

---

## 📊 Data Model Requirements

### Invoice Model Fields

```python
class Invoice(db.Model):
    """Invoice model with print template support"""
    __tablename__ = 'invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic Info
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    
    # Dates
    date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime)
    
    # Amounts
    subtotal = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    
    # Status
    status = db.Column(db.String(20), default='Pending')  # Pending, Paid, Cancelled
    
    # Relationships
    company = db.relationship('Company', backref='invoices')
    customer = db.relationship('Customer', backref='invoices')
    items = db.relationship('InvoiceItem', backref='invoice', cascade='all, delete-orphan')
    
    @property
    def balance(self):
        """Calculate remaining balance"""
        return self.total - self.paid_amount
    
    @property
    def qr_code(self):
        """Generate QR code URL for this invoice"""
        return url_for('view_invoice', invoice_id=self.id, _external=True)


class InvoiceItem(db.Model):
    """Line items for invoices"""
    __tablename__ = 'invoice_items'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    
    product = db.relationship('Product', backref='invoice_items')
    
    @property
    def total(self):
        """Calculate line item total"""
        return (self.quantity * self.unit_price) - self.discount + self.tax
```

### Receipt Model Fields

```python
class Receipt(db.Model):
    """POS Receipt model for thermal printing"""
    __tablename__ = 'receipts'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Basic Info
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    
    # Dates & Times
    date = db.Column(db.DateTime, default=datetime.utcnow)
    time = db.Column(db.String(10))  # HH:MM:SS format
    
    # Amounts
    subtotal = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    total = db.Column(db.Float, default=0.0)
    
    # Payment
    payment_method = db.Column(db.String(20))  # CASH, CARD, TRANSFER
    payment_received = db.Column(db.Float, default=0.0)
    change = db.Column(db.Float, default=0.0)
    
    # Metadata
    cashier = db.Column(db.String(50))
    register_id = db.Column(db.String(20))
    
    # Relationships
    company = db.relationship('Company', backref='receipts')
    customer = db.relationship('Customer', backref='receipts')
    items = db.relationship('ReceiptItem', backref='receipt', cascade='all, delete-orphan')
    
    @property
    def qr_code(self):
        """Generate QR code URL for this receipt"""
        return url_for('view_receipt', receipt_id=self.id, _external=True)


class ReceiptItem(db.Model):
    """Line items for receipts"""
    __tablename__ = 'receipt_items'
    
    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('receipts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    
    product = db.relationship('Product', backref='receipt_items')
```

### Company Model (Required Fields)

```python
class Company(db.Model):
    """Company model with print info"""
    __tablename__ = 'companies'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(10))  # 3-4 letter code for logo
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    website = db.Column(db.String(255))
    tax_id = db.Column(db.String(50))  # VAT/Tax number
```

### Customer Model (Required Fields)

```python
class Customer(db.Model):
    """Customer model with billing info"""
    __tablename__ = 'customers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(255))  # Customer's company name
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
```

---

## 🎯 Template Rendering Examples

### Example 1: Invoice with Dynamic Data

```python
@app.route('/sales/<int:sale_id>/invoice/print-a4')
def print_sale_invoice(sale_id):
    """Convert sale to invoice and print"""
    sale = Sale.query.get_or_404(sale_id)
    
    # Create invoice data from sale
    invoice = type('Invoice', (), {
        'invoice_number': f"INV-{sale.id:05d}",
        'date': sale.date.strftime('%Y-%m-%d'),
        'due_date': (sale.date + timedelta(days=30)).strftime('%Y-%m-%d'),
        'status': 'Pending',
        'subtotal': sale.subtotal,
        'discount': sale.discount,
        'tax': sale.tax,
        'total': sale.total,
        'paid_amount': sale.paid_amount,
        'items': sale.items
    })()
    
    return render_template('invoices/invoice_a4_cmyk.html',
                         invoice=invoice,
                         company=sale.company,
                         customer=sale.customer)
```

### Example 2: Generate Multiple Receipts

```python
@app.route('/pos/print-receipt/<int:sale_id>')
def print_pos_receipt(sale_id):
    """Print POS receipt from sale"""
    sale = Sale.query.get_or_404(sale_id)
    
    # Convert to receipt format
    receipt = type('Receipt', (), {
        'receipt_number': f"REC-{sale.id:08d}",
        'date': sale.date.strftime('%Y-%m-%d'),
        'time': sale.date.strftime('%H:%M:%S'),
        'subtotal': sale.subtotal,
        'discount': sale.discount,
        'tax': sale.tax,
        'total': sale.total,
        'payment_method': sale.payment_method,
        'payment_received': sale.payment_received,
        'change': sale.payment_received - sale.total,
        'cashier': current_user.username,
        'items': sale.items
    })()
    
    return render_template('invoices/thermal_receipt_80mm_cmyk.html',
                         receipt=receipt,
                         company=sale.company,
                         customer=sale.customer)
```

---

## 🖨️ Print Button Integration

### Add to Your HTML Templates

```html
<!-- Invoice Print Buttons -->
<div class="print-actions">
    <a href="{{ url_for('print_invoice_a4', invoice_id=invoice.id) }}" 
       class="btn btn-primary" target="_blank">
        <i class="fa fa-print"></i> Print A4 Invoice
    </a>
    
    <a href="{{ url_for('print_invoice_a5', invoice_id=invoice.id) }}" 
       class="btn btn-secondary" target="_blank">
        <i class="fa fa-print"></i> Print A5 Invoice
    </a>
    
    <button onclick="printDirect('a4')" class="btn btn-info">
        <i class="fa fa-print"></i> Print Now (A4)
    </button>
</div>

<!-- Receipt Print Button -->
<div class="receipt-actions">
    <a href="{{ url_for('print_receipt_thermal', receipt_id=receipt.id) }}" 
       class="btn btn-primary" target="_blank">
        <i class="fa fa-print"></i> Print Receipt
    </a>
    
    <button onclick="printThermal()" class="btn btn-warning">
        <i class="fa fa-print"></i> Print to POS Printer
    </button>
</div>
```

### JavaScript for Direct Printing

```javascript
function printDirect(size) {
    // Get the appropriate print URL
    const printUrl = size === 'a4' 
        ? `/invoice/${invoiceId}/print-a4`
        : `/invoice/${invoiceId}/print-a5`;
    
    const printWindow = window.open(printUrl, '_blank');
    printWindow.addEventListener('load', function() {
        printWindow.print();
        printWindow.close();
    });
}

function printThermal() {
    const printWindow = window.open(
        `/receipt/${receiptId}/print-thermal`,
        '_blank'
    );
    printWindow.addEventListener('load', function() {
        printWindow.print();
    });
}
```

---

## 🔒 Security Considerations

### Access Control

```python
def check_print_access(invoice_id):
    """Verify user has permission to print invoice"""
    invoice = Invoice.query.get_or_404(invoice_id)
    
    # Super admin can print any invoice
    if current_user.is_super_admin():
        return invoice
    
    # Regular users can only print from their company
    if invoice.company_id != session.get('company_id'):
        abort(403, "Access denied")
    
    # Check specific permissions
    if not current_user.can_access_sales:
        abort(403, "Permission denied")
    
    return invoice
```

### Audit Logging

```python
def log_print_action(invoice_id, format_type):
    """Log when invoice is printed"""
    audit_log = AuditLog(
        user_id=current_user.id,
        action='print_invoice',
        resource_type='invoice',
        resource_id=invoice_id,
        details={
            'format': format_type,  # a4, a5, thermal
            'timestamp': datetime.utcnow(),
            'ip_address': request.remote_addr
        }
    )
    db.session.add(audit_log)
    db.session.commit()
```

---

## 📋 Testing Checklist

- [ ] Test A4 invoice on laser printer
- [ ] Test A5 invoice on laser printer
- [ ] Test 80mm receipt on thermal printer
- [ ] Verify CMYK color rendering
- [ ] Check 300 DPI output quality
- [ ] Confirm margins are correct
- [ ] Test with different paper sizes
- [ ] Verify QR codes generate
- [ ] Check dynamic data rendering
- [ ] Test with special characters
- [ ] Verify pagination on long invoices
- [ ] Test access control/permissions

---

## 📞 Troubleshooting

### Issue: Template not found
```
Solution: Ensure file path is correct and templates directory is in FLASK_TEMPLATE_FOLDER
```

### Issue: Data not rendering
```
Solution: Check that all required fields are passed to render_template
```

### Issue: Print page margins incorrect
```
Solution: Check browser print settings - disable "Headers and footers"
```

### Issue: Thermal printer prints wrong size
```
Solution: Select correct paper size (80mm) in printer settings
```

---

## ✅ Next Steps

1. **Test Templates:** Print a test invoice in all formats
2. **Customize Branding:** Update company logo and colors
3. **Integrate Routes:** Add the routes to your Flask app
4. **Test Security:** Verify access control works
5. **Documentation:** Update your internal docs
6. **User Training:** Show users how to print invoices
7. **Monitoring:** Track print usage via audit logs

---

**Happy Printing! 🖨️**
