# Production thermal receipt findings

Inspected `https://pos.infixindustries.com/sales/2/receipt/html?format=thermal` on 2026-08-24.

Observed in the rendered output:

- The item header has four columns (Item, Qty, Price, Total), but each item row renders only a name line and a two-part quantity/price-plus-total line, so the columns do not align.
- The product name and numeric values appear visually cramped and the item total is not aligned under the Total column.
- The receipt includes a large empty `[QR CODE] Scan for details` placeholder instead of a real QR code; this wastes thermal paper and looks unfinished.
- The receipt number appears once in the metadata and again as an oversized barcode-like text block, which is redundant.
- The current layout uses excessive separators and a large QR placeholder for an 80mm receipt.
- Sale values themselves appeared internally consistent for the sample: subtotal Rs. 1500.00, tax Rs. 270.00, total Rs. 1770.00, cash given Rs. 2000.00, change Rs. 230.00.

Repository path: `app/templates/invoices/thermal_receipt_80mm_professional.html`.
Route path: `app/routes/sales.py`, `receipt_html` renders that template for `format=thermal`.
