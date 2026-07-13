# Receipt Settings Integration Guide

## Overview

This document explains how receipt settings are dynamically integrated throughout the Web POS system. When you update receipt settings, they automatically appear on all printed receipts without requiring code changes.

## How It Works

### 1. **Settings Storage (Database Layer)**

All receipt settings are stored in the `Setting` model with:
- **Category**: `receipt` or `terminal` (for receipt-related configurations)
- **Key**: The setting name (e.g., `business_name`, `thank_you_message`)
- **Value**: The setting value (stored as text)
- **Company ID**: Multi-company support - settings are isolated per company

**Database Fields:**
```
id, setting_category, setting_key, setting_value, updated_at, company_id
```

**Unique Constraint:**
```
(setting_category, setting_key, company_id) - prevents duplicate settings per company
```

### 2. **Settings Retrieval (`get_receipt_settings` function)**

**Location:** `app/routes/invoices.py` (lines 17-82)

**How it works:**
```python
def get_receipt_settings(company_id=None):
    # 1. Gets global settings (company_id = None)
    # 2. Overlays company-specific settings
    # 3. Returns merged dict with defaults
```

**Returns a dictionary with these keys:**
- `business_name`: Company name on receipt
- `business_address`: Company address
- `business_city`: City
- `business_phone`: Phone number
- `business_email`: Email address
- `business_gst`: Tax/GST number
- `thank_you_message`: Thank you text on receipt
- `warranty_info`: Warranty information
- `footer_text`: Footer message
- `show_qr_code`: Whether to display QR code
- `default_receipt_format`: Default template (thermal/a4/a5)
- `receipt_logo`: Logo file path

### 3. **Settings UI (Frontend)**

**Location:** `app/templates/settings/settings.html` (lines 549-648)

Two forms handle receipt settings:

#### Receipt Settings Tab (lines 549-648)
- Business Information
  - Business Name
  - Business Logo (with upload)
  - Business Address
  - Business Phone
  - Business Email
  - GST/Tax Number
  
- Receipt Options
  - Default Receipt Format (thermal/A4/A5)
  - Show QR Code (checkbox)
  - Thank You Message
  - Warranty Information
  - Footer Text

#### Terminal Settings Tab (lines 648-750)
- Receipt Format
  - Receipt Type
  - Receipt Theme
  
- Print Settings
  - Auto-print after sale
  - Show business logo
  - Show barcode
  - Show terms & conditions
  
- Paper Size
  - Paper Width (mm)
  - Font Size

- Terms & Conditions
  - Terms & Conditions text
  - Return Policy

### 4. **Settings API Endpoints**

**Save Settings:**
```
POST /api/settings
Body: {
    "receipt": {
        "business_name": "Your Store",
        "business_address": "123 Main St",
        "thank_you_message": "Thank you!",
        ...
    }
}
```

**Get Settings for Category:**
```
GET /api/settings/categories/receipt
Response: {
    "success": true,
    "settings": {
        "business_name": "Your Store",
        ...
    }
}
```

**Get All Settings:**
```
GET /api/settings
```

### 5. **Receipt Rendering Routes**

When a receipt is printed, the renderer retrieves current settings:

**Thermal Receipt (80mm):**
```python
@sales_bp.route('/<int:sale_id>/receipt/html')
def receipt_html(sale_id):
    receipt_settings = get_receipt_settings(company_id)
    context = {
        'business_name': receipt_settings.get('company_name'),
        'business_address': receipt_settings.get('business_address'),
        'thank_you_message': receipt_settings.get('thank_you_message'),
        ...
    }
    return render_template('invoices/thermal_receipt_80mm_professional.html', **context)
```

**Preview Routes:**
- `/invoices/preview/receipt` - Preview thermal receipt
- `/invoices/preview/a4` - Preview A4 invoice
- `/invoices/preview/a5` - Preview A5 invoice

### 6. **Template Integration**

Receipt templates use Jinja2 variables that are passed from the backend:

**Example from `thermal_receipt_80mm_professional.html`:**
```html
<!-- Business Name -->
<div class="company-name">{{ business_name }}</div>

<!-- Address -->
<div class="company-address">{{ business_address }}</div>

<!-- Thank You Message -->
<div class="thank-you">{{ thank_you_message }}</div>

<!-- Footer -->
<div class="footer">{{ business_name }}<br>{{ footer_text }}</div>
```

## Complete Data Flow

### When Updating Receipt Settings:

1. **User Updates Settings** in Settings > Receipt Configuration
2. **JavaScript handler** sends POST request to `/api/settings`
3. **Backend (`save_settings`)** validates and saves to database
4. **Success notification** shown to user

### When Printing a Receipt:

1. **User clicks Print** on a sale
2. **Backend route** calls `get_receipt_settings(company_id)`
3. **Function retrieves** current settings from database
4. **Settings passed** to receipt template as context variables
5. **Template renders** with dynamic values
6. **Receipt displays** all updated settings

## Settings Persistence

- **Automatic**: Settings persist across application restarts
- **Per-Company**: Each company has isolated settings
- **Real-time**: No caching delays - always retrieves latest

## JavaScript Form Handlers

### Receipt Settings Form (`receiptSettingsForm`)
- **Load Function**: `loadReceiptSettings()` - Retrieves current settings from `/api/settings/categories/receipt`
- **Save Endpoint**: `POST /api/settings`
- **Data Structure**:
```javascript
{
    "receipt": {
        "business_name": "...",
        "business_address": "...",
        "footer_text": "..."
    }
}
```

### Terminal Settings Form (`terminalSettingsForm`)
- **Load Function**: `loadTerminalSettings()` - Retrieves from `/api/settings/categories/terminal`
- **Save Endpoint**: `POST /api/settings`
- **Data Structure**:
```javascript
{
    "terminal": {
        "receipt_type": "thermal",
        "auto_print": "true|false",
        "font_size": "10"
    }
}
```

## Setting Keys Reference

### Receipt Category Settings
| Key | Type | Default | Usage |
|-----|------|---------|-------|
| `business_name` | Text | YOUR STORE | Appears at top of receipt |
| `business_address` | Text | 123 Main St | Company address on receipt |
| `business_phone` | Text | (555) 123-4567 | Contact number |
| `business_email` | Text | support@store.com | Contact email |
| `business_gst` | Text | - | Tax/GST number |
| `thank_you_message` | Text | Thank you... | Message at bottom |
| `warranty_info` | Text | - | Warranty details |
| `footer_text` | Text | Generated by POS | Footer message |
| `show_qr_code` | Boolean | true | Display QR code |
| `default_receipt_format` | Select | thermal | Default template to use |
| `receipt_logo` | File Path | - | Business logo |

### Terminal Category Settings
| Key | Type | Default | Usage |
|-----|------|---------|-------|
| `receipt_type` | Select | thermal | Receipt format |
| `receipt_theme` | Select | professional | Visual theme |
| `auto_print` | Boolean | true | Auto-print after sale |
| `show_logo` | Boolean | true | Display business logo |
| `show_barcode` | Boolean | true | Show barcode |
| `show_terms` | Boolean | true | Display terms |
| `paper_width` | Number | 80 | Width in mm |
| `font_size` | Select | 10 | Font size in points |
| `terms_conditions` | Text | - | Terms text |
| `return_policy` | Text | 7 days | Return policy text |

## Templates Updated

The following receipt templates automatically use dynamic settings:

1. **`thermal_receipt_80mm_professional.html`** - Primary thermal receipt
2. **`thermal_receipt_80mm_cmyk.html`** - CMYK print-optimized thermal receipt
3. **`invoice_a4.html`** - A4 professional invoice
4. **`invoice_a4_cmyk.html`** - A4 CMYK printing
5. **`invoice_a5.html`** - A5 compact invoice
6. **`invoice_a5_cmyk.html`** - A5 CMYK printing

## Testing the Integration

### Test 1: Update Business Name
1. Go to **Settings > Receipt Configuration**
2. Change "Business Name" to "My Test Store"
3. Click "Save Receipt Settings"
4. Go to **Sales** and print any receipt
5. **Result**: Receipt should show "My Test Store" at the top

### Test 2: Update Thank You Message
1. Go to **Settings > Receipt Configuration**
2. Change "Thank You Message" to "Thank you for shopping!"
3. Click "Save Receipt Settings"
4. Print a receipt
5. **Result**: New message appears at bottom

### Test 3: Update Footer Text
1. Go to **Settings > Terminal Configuration**
2. Change "Footer Text"
3. Click "Save Terminal Settings"
4. Print a receipt
5. **Result**: New footer appears at bottom

## Troubleshooting

### Settings Not Appearing on Receipt

**Check 1: Verify Settings Saved**
- Go to Settings > Receipt Configuration
- Check that fields have values
- Look at browser console for any JavaScript errors

**Check 2: Verify Database**
```sql
SELECT * FROM setting WHERE setting_category='receipt' AND company_id=<your_company_id>;
```

**Check 3: Check Receipt Route**
- Verify the route is calling `get_receipt_settings(company_id)`
- Ensure company_id is being passed correctly

**Check 4: Template Variables**
- Verify the template has `{{ variable_name }}` with correct variable names
- Check that the route passes the setting with the correct key name

### Settings Loading Slow

- Check database query performance
- Verify company_id filtering is working correctly
- Check for N+1 query problems

### Settings Not Multi-Company Isolated

- Verify `company_id` is set correctly in `get_company_id()`
- Check that routes use `get_company_id()` accurately
- Confirm settings API filters by company_id

## Backend Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Receipt Settings Retrieval | `app/routes/invoices.py` | 17-82 |
| Settings API | `app/routes/settings_new.py` | 365-420 |
| Receipt Rendering (Sales) | `app/routes/sales.py` | 600-850 |
| Settings UI | `app/templates/settings/settings.html` | 549-750 |
| Settings JS Handler | `app/templates/settings/settings.html` | 2330-2485 |
| Receipt Template | `app/templates/invoices/thermal_receipt_80mm_professional.html` | Full |

## Best Practices

1. **Always use `get_receipt_settings(company_id)`** when retrieving settings
2. **Never hardcode** business information - always pull from settings
3. **Test in preview** before printing: `/invoices/preview/receipt`
4. **Use the same key names** in forms and retrieval functions
5. **Verify company_id** isolation for multi-company deployments
6. **Clear browser cache** if settings not updating visually

## Future Enhancements

- [ ] Logo upload and storage
- [ ] Multiple template themes
- [ ] Color customization
- [ ] Custom field mappings
- [ ] Receipt preview with live settings
- [ ] Settings import/export
- [ ] Receipt history with settings used
