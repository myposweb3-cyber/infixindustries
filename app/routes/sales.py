from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from app.models import db, Product, Sale, SaleItem, Customer, Setting, HeldBill, Return, ReturnItem, InventoryTransaction
from app.models import Exchange, ExchangeItem, Cheque
from app.utils.permissions import require_permission
from app.utils.security import get_company_id, require_company_context
from app.utils.company import column_exists_in_db
from datetime import datetime, timedelta
from sqlalchemy import desc, case, or_
import json
from app.utils.email_sender import send_email
from app.utils.whatsapp_sender import generate_whatsapp_link
# Optional Twilio import - only if available
try:
    from app.utils.whatsapp_twilio import send_whatsapp_via_twilio
except ImportError:
    send_whatsapp_via_twilio = None
from app.utils.receipt_generator import ReceiptGenerator
from app import csrf

sales_bp = Blueprint('sales', __name__, template_folder='../../templates')

def get_company_filter(model_class):
    """Get company filter for a model if company_id column exists."""
    company_id = get_company_id()
    if company_id and hasattr(model_class, 'company_id'):
        return model_class.company_id == company_id
    return None

def get_sale_secure(sale_id):
    """Get a sale with company_id verification (security check).
    Returns None if sale_id doesn't belong to current company."""
    company_id = get_company_id()
    if company_id and hasattr(Sale, 'company_id'):
        sale = Sale.query.filter(
            Sale.id == sale_id,
            Sale.company_id == company_id
        ).first()
    else:
        sale = Sale.query.get(sale_id)
    return sale

@sales_bp.route('/sales')
@login_required
@require_company_context
@require_permission('can_access_sales')
def sales():
    """Main sales page."""
    return render_template('sales/sales.html')

@sales_bp.route('/api/products/search')
@csrf.exempt
@login_required
@require_company_context
def search_products():
    """API endpoint for product search with optional category filter."""
    query = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    company_id = get_company_id()

    products_query = Product.query
    
    # Apply company filter
    if company_id and hasattr(Product, 'company_id'):
        products_query = products_query.filter(Product.company_id == company_id)

    if query:
        # Prioritize exact barcode match at the top of the results
        order_logic = case(
            (Product.barcode.ilike(query), 0),
            else_=1
        )
        products_query = products_query.filter(
            db.or_(
                Product.name.ilike(f'%{query}%'),
                Product.barcode.ilike(query)
            )
        ).order_by(order_logic, Product.name)
    else:
        # Default sort by name if no query
        products_query = products_query.order_by(Product.name)
    
    if category:
        products_query = products_query.filter(Product.category == category)

    products = products_query.limit(50).all()

    result = []
    for product in products:
        result.append({
            'id': product.id,
            'name': product.name,
            'price': float(product.price) if product.price else 0,
            'stock': float(product.stock) if product.stock else 0,
            'unit_type': product.unit_type or '',
            'image_path': product.image_path or '',
            'category': product.category or '',
            'price_per_kg': float(product.price_per_kg) if hasattr(product, 'price_per_kg') and product.price_per_kg else None
        })

    return jsonify(result)

@sales_bp.route('/api/products/barcode/parse', methods=['POST'])
@csrf.exempt
@login_required
def parse_weighted_barcode():
    """
    Parse weighted product barcode and extract embedded data.
    
    Barcode format: P{pCode}W{weight_in_grams}T{total_price}
    Example: P001W07500900 = Product 001, 750g, Rs 900
    
    Also supports direct barcode lookup for regular products.
    """
    data = request.get_json()
    barcode = data.get('barcode', '').strip()
    
    if not barcode:
        return jsonify({'error': 'Barcode is required'}), 400
    
    try:
        company_id = get_company_id()
        # First, try to find product by direct barcode match
        product_query = Product.query.filter_by(barcode=barcode)
        if company_id and hasattr(Product, 'company_id'):
            product_query = product_query.filter(Product.company_id == company_id)
        product = product_query.first()
        
        if product:
            # Regular product found
            return jsonify({
                'success': True,
                'type': 'regular',
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'price': product.price,
                    'stock': product.stock,
                    'unit_type': product.unit_type,
                    'price_per_kg': product.price_per_kg if hasattr(product, 'price_per_kg') else None
                },
                'quantity': 1,
                'total': product.price
            })
        
        # Try to parse weighted product barcode
        # Format: P{pcode}W{weight_grams}T{total_price}
        # Example: PPROD001W07500900 = Product Code: PROD001, Weight: 750g, Total: 900 LKR
        
        parsed_data = parse_weighted_barcode_format(barcode)
        
        if parsed_data:
            # Find product by product code
            product = Product.query.filter_by(product_code=parsed_data['product_code']).first()
            
            if not product:
                # Try searching by name/code
                product = Product.query.filter(
                    db.or_(
                        Product.name.ilike(f'%{parsed_data["product_code"]}%'),
                        Product.barcode.ilike(f'%{parsed_data["product_code"]}%')
                    )
                ).first()
            
            if product:
                weight_kg = parsed_data['weight_kg']
                total_price = parsed_data['total_price']
                
                # Calculate price per kg from embedded data
                if weight_kg > 0:
                    calculated_price_per_kg = total_price / weight_kg
                else:
                    calculated_price_per_kg = product.price_per_kg if hasattr(product, 'price_per_kg') and product.price_per_kg else product.price
                
                return jsonify({
                    'success': True,
                    'type': 'weighted',
                    'product': {
                        'id': product.id,
                        'name': product.name,
                        'price': product.price,
                        'price_per_kg': product.price_per_kg if hasattr(product, 'price_per_kg') else calculated_price_per_kg,
                        'stock': product.stock,
                        'unit_type': 'kg'
                    },
                    'weight_kg': weight_kg,
                    'weight_grams': parsed_data['weight_grams'],
                    'total': total_price,
                    'is_weighted_product': True
                })
        
        # Product not found
        return jsonify({
            'success': False,
            'error': 'Product not found',
            'barcode': barcode
        }), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def parse_weighted_barcode_format(barcode):
    """
    Parse weighted product barcode format.
    
    Supported formats:
    1. P{pcode}W{weight_grams}T{total_price} - Full format
       Example: P001W07500900 -> {product_code: '001', weight_grams: 750, total_price: 900}
    2. {product_code}{weight_grams}{price} - Compact format
       Example: 00107500900 -> {product_code: '001', weight_grams: 750, total_price: 900}
    3. EAN-13 with embedded weight/price (first 2 digits = weight indicator)
    """
    import re
    
    barcode = barcode.strip()
    
    # Try full format: P{pcode}W{weight_grams}T{total_price}
    match = re.match(r'^P(.+?)W(\d+)T(\d+)$', barcode)
    if match:
        product_code = match.group(1)
        weight_grams = int(match.group(2))
        total_price = int(match.group(3))
        weight_kg = weight_grams / 1000.0
        return {
            'product_code': product_code,
            'weight_grams': weight_grams,
            'weight_kg': weight_kg,
            'total_price': total_price
        }
    
    # Try compact format (numeric only, assume first N digits = product code)
    # Heuristic: weight is usually 4-5 digits, price is 3-5 digits
    if barcode.isdigit() and len(barcode) >= 10:
        # Try different parsing strategies
        for code_len in range(3, 8):  # Product code length 3-7
            remaining = barcode[code_len:]
            if len(remaining) >= 7:
                # Try: weight (4 digits) + price (3+ digits)
                for weight_len in [4, 5]:
                    if len(remaining) > weight_len + 3:
                        weight_str = remaining[:weight_len]
                        price_str = remaining[weight_len:]
                        if weight_str.isdigit() and price_str.isdigit():
                            try:
                                weight_grams = int(weight_str)
                                total_price = int(price_str)
                                if weight_grams > 0 and weight_grams <= 99999 and total_price > 0:
                                    return {
                                        'product_code': barcode[:code_len],
                                        'weight_grams': weight_grams,
                                        'weight_kg': weight_grams / 1000.0,
                                        'total_price': total_price
                                    }
                            except:
                                pass
    
    # EAN-13 format (for scales that output EAN-13)
    # EAN-13 format: usually starts with 2 for variable weight items
    if barcode.isdigit() and len(barcode) == 13:
        first_two = int(barcode[:2])
        if 20 <= first_two <= 29:  # Variable weight indicator
            # EAN-13: [2X][XXXXX][XXX][X]
            # 2X = weight indicator (20-29)
            # XXXXX = product code (5 digits)
            # XXX = weight (3 digits in grams)
            # X = check digit
            try:
                weight_indicator = int(barcode[:2]) - 20  # 0-9
                product_code = barcode[2:7]  # 5 digit product code
                weight_grams = int(barcode[7:10])  # 3 digit weight
                # Note: price is not typically embedded in EAN-13, only weight
                if weight_grams > 0:
                    return {
                        'product_code': product_code,
                        'weight_grams': weight_grams,
                        'weight_kg': weight_grams / 1000.0,
                        'total_price': None  # Price not embedded in EAN-13
                    }
            except:
                pass
    
    return None

@sales_bp.route('/api/customers/search')
@csrf.exempt
@login_required
def search_customers():
    """API endpoint for customer search."""
    query = request.args.get('search', '').strip()
    company_id = get_company_id()

    customers_query = Customer.query
    
    # Filter by company
    if company_id and hasattr(Customer, 'company_id'):
        customers_query = customers_query.filter(Customer.company_id == company_id)

    if query:
        customers_query = customers_query.filter(
            db.or_(
                Customer.name.ilike(f'%{query}%'),
                Customer.phone.ilike(f'%{query}%')
            )
        )

    customers = customers_query.order_by(Customer.name).limit(20).all()
    result = []
    for customer in customers:
        result.append({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone or '',
            'loyalty_points': int(customer.loyalty_points) if customer.loyalty_points else 0
        })

    return jsonify(result)

@sales_bp.route('/api/sales/create', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_sales')
def create_sale():
    """API endpoint to create a new sale."""
    data = request.get_json()
    
    # Log incoming data for debugging
    current_app.logger.info(f"SALES CREATE - Received data: {data}")
    if not data:
        current_app.logger.error("SALES CREATE ERROR: No JSON data received")
        return jsonify({'error': 'Invalid sale data - no data'}), 400
    
    if 'items' not in data:
        current_app.logger.error(f"SALES CREATE ERROR: Missing 'items' key. Keys present: {list(data.keys())}")
        return jsonify({'error': 'Invalid sale data - missing items'}), 400
    
    if not data['items'] or len(data['items']) == 0:
        current_app.logger.error("SALES CREATE ERROR: Items list is empty")
        return jsonify({'error': 'Cart is empty'}), 400

    try:
        # Validate payment method and amount first
        payment_method = data.get('payment_method', 'Cash')
        total = float(data.get('total', 0.0))
        current_app.logger.info(f"SALES CREATE - Payment method: {payment_method}, Total: {total}")
        current_app.logger.info(f"SALES CREATE - Full payment data received: {{'payment_method': '{payment_method}', 'balance': {data.get('balance', 0)}, 'cash_given': {data.get('cash_given', 0)}}}")
        
        if payment_method == 'Cash':
            cash_given = float(data.get('cash_given', 0.0))
            if cash_given < total:
                return jsonify({'error': 'Insufficient cash payment'}), 400

        # Fetch all products in one query
        product_ids = [item['product_id'] for item in data['items']]
        current_app.logger.info(f"SALES CREATE - Product IDs: {product_ids}")
        # Get company_id from session if available
        company_id = get_company_id()
        products_query = Product.query.filter(Product.id.in_(product_ids))
        if company_id and hasattr(Product, 'company_id'):
            products_query = products_query.filter(Product.company_id == company_id)
        products = {p.id: p for p in products_query.all()}
        current_app.logger.info(f"SALES CREATE - Found {len(products)} products (requested {len(product_ids)})")
        
        # Validate stock for all items
        for item in data['items']:
            product = products.get(item['product_id'])
            if not product:
                current_app.logger.error(f"SALES CREATE ERROR: Product {item['product_id']} not found in DB")
                return jsonify({'error': f'Product {item["product_id"]} not found'}), 404
            if product.stock < item['quantity']:
                current_app.logger.error(f"SALES CREATE ERROR: Insufficient stock for {product.name}. Requested: {item['quantity']}, Available: {product.stock}")
                return jsonify({'error': f'Insufficient stock for {product.name}. Available: {product.stock}'}), 400
        
        # Create sale record
        sale = Sale(
            customer=data.get('customer', 'Walk-in Customer'),
            payment=payment_method,
            cash_given=float(data.get('cash_given', 0.0)),
            total=float(data.get('total', 0.0)),
            discount=float(data.get('discount', 0.0)),
            tax=float(data.get('tax', 0.0)),
            # Set balance correctly: 0 for paid sales (Cash/Cheque), balance_due for credit
            balance=0.0 if payment_method in ['Cash', 'Cheque'] else float(data.get('balance', 0.0)),
            user_id=current_user.id,
            company_id=company_id
        )

        db.session.add(sale)
        db.session.flush()  # Get sale ID

        # Create cheque record if payment method is cheque
        if payment_method == 'Cheque':
            cheque_number = data.get('cheque_number', '').strip()
            bank_name = data.get('bank_name', '').strip()
            cheque_date = data.get('cheque_date', '').strip()
            
            # Validate cheque details are provided
            if not cheque_number or not bank_name or not cheque_date:
                current_app.logger.warning(f"Cheque sale created but cheque details incomplete: "
                                  f"cheque_number={cheque_number}, bank_name={bank_name}, cheque_date={cheque_date}")
            else:
                try:
                    # Try to get customer ID if customer is selected
                    customer_id = None
                    if data.get('customer') and data['customer'] != 'Walk-in Customer':
                        customer_query = Customer.query.filter_by(name=data['customer'])
                        if company_id and hasattr(Customer, 'company_id'):
                            customer_query = customer_query.filter(Customer.company_id == company_id)
                        customer = customer_query.first()
                        if customer:
                            customer_id = customer.id
                    
                    cheque = Cheque(
                        cheque_number=cheque_number,
                        bank_name=bank_name,
                        cheque_date=datetime.strptime(cheque_date, '%Y-%m-%d').date() if cheque_date else datetime.utcnow().date(),
                        amount=total,
                        payer_name=data.get('customer', 'Walk-in Customer'),
                        customer_id=customer_id,
                        status='pending',
                        sale_id=sale.id,
                        created_by=current_user.id,
                        company_id=company_id
                    )
                    db.session.add(cheque)
                except Exception as e:
                    # Log error but don't fail the sale if cheque creation fails
                    current_app.logger.error(f"Failed to create cheque record for sale {sale.id}: {type(e).__name__}: {e}")


        # Prepare bulk data for sale items and inventory transactions
        customer_name = data.get('customer', 'Walk-in')
        sale_items = []
        inventory_transactions = []
        
        for item in data['items']:
            product = products[item['product_id']]
            previous_stock = product.stock
            new_stock = previous_stock - item['quantity']
            
            # Prepare sale item data
            sale_items.append({
                'sale_id': sale.id,
                'product_id': item['product_id'],
                'quantity': item['quantity'],
                'price': item['price'],
                'discount': item.get('discount', 0.0),
                'tax': item.get('tax', 0.0),
                'company_id': company_id
            })
            
            # Update product stock in memory
            product.stock = new_stock
            
            # Prepare inventory transaction data
            inventory_transactions.append({
                'product_id': item['product_id'],
                'transaction_type': 'sale',
                'quantity': item['quantity'],
                'previous_stock': previous_stock,
                'new_stock': new_stock,
                'reference_id': sale.id,
                'company_id': company_id,
                'notes': f'Sold to {customer_name}'
            })
        
        # Bulk insert sale items
        db.session.bulk_insert_mappings(SaleItem, sale_items)
        
        # Bulk insert inventory transactions
        db.session.bulk_insert_mappings(InventoryTransaction, inventory_transactions)
        
        # Bulk update product stocks using a single query
        stock_updates = [
            {'id': product.id, 'stock': product.stock} 
            for product in products.values()
        ]
        if stock_updates:
            db.session.bulk_update_mappings(Product, stock_updates)

        # Update customer loyalty points and balance if applicable
        if data.get('customer') and data['customer'] != 'Walk-in Customer':
            customer_query = Customer.query.filter_by(name=data['customer'])
            if company_id and hasattr(Customer, 'company_id'):
                customer_query = customer_query.filter(Customer.company_id == company_id)
            customer = customer_query.first()
            if customer:
                # Award points (1 point per Rs 10 spent)
                points_earned = int(data.get('subtotal', 0) // 10)
                customer.loyalty_points += points_earned
                customer.total_purchases += float(data.get('subtotal', 0))
                customer.last_purchase_date = datetime.utcnow()

                # Redeem points if used
                if data.get('points_redeemed', 0) > 0:
                    customer.loyalty_points -= data.get('points_redeemed', 0)
                
                # Update customer current_balance if there's a credit/balance
                credit_balance = float(data.get('balance', 0.0))
                if credit_balance > 0:
                    # Add to customer's current balance
                    customer.current_balance += credit_balance
                    
                    # Recalculate aging buckets
                    from datetime import timedelta
                    now = datetime.utcnow()
                    thirty_days_ago = now - timedelta(days=30)
                    sixty_days_ago = now - timedelta(days=60)
                    ninety_days_ago = now - timedelta(days=90)
                    
                    # Get all unpaid sales for this customer to recalculate aging
                    unpaid_sales_query = Sale.query.filter(
                        Sale.customer == customer.name,
                        Sale.balance > 0
                    )
                    if company_id and hasattr(Sale, 'company_id'):
                        unpaid_sales_query = unpaid_sales_query.filter(Sale.company_id == company_id)
                    unpaid_sales = unpaid_sales_query.all()
                    
                    outstanding_0_30 = 0.0
                    outstanding_30_60 = 0.0
                    outstanding_60_90 = 0.0
                    outstanding_90_plus = 0.0
                    
                    for s in unpaid_sales:
                        days_old = (now - s.date).days
                        if days_old <= 30:
                            outstanding_0_30 += s.balance
                        elif days_old <= 60:
                            outstanding_30_60 += s.balance
                        elif days_old <= 90:
                            outstanding_60_90 += s.balance
                        else:
                            outstanding_90_plus += s.balance
                    
                    customer.outstanding_0_30 = outstanding_0_30
                    customer.outstanding_30_60 = outstanding_30_60
                    customer.outstanding_60_90 = outstanding_60_90
                    customer.outstanding_90_plus = outstanding_90_plus
                    customer.last_balance_update = now
                    
                    # Auto-stop supply if overdue > 90 days
                    if outstanding_90_plus > 0:
                        customer.supply_stopped = True

        db.session.commit()

        return jsonify({
            'success': True,
            'sale_id': sale.id,
            'message': f'Sale completed successfully! Sale #{sale.id}',
            'receipt_html_url': f'/sales/{sale.id}/receipt/html?format=a4',
            'receipt_pdf_url': f'/api/sales/{sale.id}/receipt/pdf?format=a4',
            'receipt_print_url': f'/api/sales/{sale.id}/print-receipt'
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"SALES CREATE EXCEPTION: {type(e).__name__}: {str(e)}", exc_info=True)
        return jsonify({'error': f'Error creating sale: {str(e)}'}), 500

@sales_bp.route('/api/sales/<int:sale_id>/receipt')
@login_required
def get_receipt(sale_id):
    """Get receipt data for a sale."""
    from app.routes.invoices import get_receipt_settings
    
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404

    receipt_data = {
        'sale_id': sale.id,
        'date': sale.date.strftime('%Y-%m-%d %H:%M:%S'),
        'customer': sale.customer,
        'items': [],
        'subtotal': 0,
        'total': sale.total,
        'payment': sale.payment,
        'cash_given': sale.cash_given,
        'balance': sale.balance
    }

    for item in sale.items:
        item_data = {
            'name': item.product.name,
            'quantity': item.quantity,
            'price': item.price,
            'total': item.quantity * item.price
        }
        receipt_data['items'].append(item_data)
        receipt_data['subtotal'] += item_data['total']

    # Get receipt settings using the integrated function
    company_id = get_company_id()
    receipt_settings = get_receipt_settings(company_id)
    
    receipt_data['business_name'] = receipt_settings.get('company_name', 'POS System')
    receipt_data['footer'] = receipt_settings.get('thank_you_message', 'Thank you for your business!')

    return jsonify(receipt_data)

@sales_bp.route('/<int:sale_id>/receipt/html')
def receipt_html(sale_id):
    """Serve HTML receipt template - Professional Invoice."""
    from app.routes.invoices import get_receipt_settings
    from datetime import datetime, timedelta

    # Helper: safely convert receipt setting values to boolean
    def _bool_setting(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        try:
            return str(val).strip().lower() in ('true', '1', 'yes')
        except Exception:
            return False
    
    sale = Sale.query.get(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404
    
    # Get format from query parameter, default to thermal
    receipt_format = request.args.get('format', 'thermal').lower()
    if receipt_format not in ['thermal', 'a4', 'a5']:
        receipt_format = 'thermal'
    
    # Get sale items
    items = SaleItem.query.filter_by(sale_id=sale.id).all()
    
    # Prepare item data for template
    items_data = []
    subtotal_before = 0.0
    subtotal_after = 0.0
    for item in items:
        # Get product name with fallback
        product_name = item.product.name if hasattr(item, 'product') and item.product else 'Unknown Product'

        # Use product ID as item code (fallback to sale_item.product_id or 'N/A')
        if hasattr(item, 'product') and item.product and getattr(item.product, 'id', None):
            product_code = str(item.product.id)
        else:
            product_code = str(getattr(item, 'product_id', 'N/A') or 'N/A')

        # Calculate item totals using actual SaleItem attributes
        item_discount = item.discount if hasattr(item, 'discount') and item.discount else 0
        item_tax = item.tax if hasattr(item, 'tax') and item.tax else 0
        item_price_before_discount = item.price * item.quantity
        item_total = item_price_before_discount - item_discount + item_tax

        item_data = {
            'code': product_code,
            'name': product_name,
            'quantity': item.quantity,
            'unit_price': item.price,
            'discount': item_discount,
            'tax_amount': item_tax,
            'total': item_total
        }
        items_data.append(item_data)
        subtotal_before += item_price_before_discount
        subtotal_after += item_total
    
    # Calculate derived values
    discount_total = sum(item['discount'] for item in items_data) + (getattr(sale, 'discount', 0) or 0)
    tax_total = sum(item['tax_amount'] for item in items_data)

    # Determine taxable base (pre-discount)
    taxable_base = max(0.0, subtotal_before - discount_total)

    # Calculate tax rate from totals (relative to taxable base)
    tax_rate = 0
    if tax_total > 0 and taxable_base > 0:
        tax_rate = round((tax_total / taxable_base) * 100, 1)
    
    change = sale.cash_given - sale.total if sale.payment == 'Cash' else 0
    
    # Calculate paid amount correctly
    # For Cash/Cheque: always fully paid
    # For Credit: paid_amount = total - balance
    if sale.payment in ['Cash', 'Cheque']:
        paid_amount = sale.total
        balance_due = 0.0
    else:
        paid_amount = sale.total - (sale.balance if sale.balance > 0 else 0)
        balance_due = max(0, sale.balance)
    
    # Get receipt settings using the integrated function
    company_id = get_company_id()
    # Fallback to sale's company_id if get_company_id() returns None
    if not company_id and hasattr(sale, 'company_id'):
        company_id = sale.company_id
    current_app.logger.info(f"[RECEIPT DEBUG] company_id: {company_id}, sale.company_id: {sale.company_id}")
    receipt_settings = get_receipt_settings(company_id)
    current_app.logger.info(f"[RECEIPT DEBUG] Retrieved settings - business_name: {receipt_settings.get('business_name')}, thank_you: {receipt_settings.get('thank_you_message')}")
    
    # Get currency symbol from settings
    from app.models import Setting
    currency_symbol = Setting.query.filter_by(
        setting_category='currency',
        setting_key='symbol',
        company_id=company_id
    ).first()
    
    if not currency_symbol:
        # Fallback to general category
        currency_symbol = Setting.query.filter_by(
            setting_category='general',
            setting_key='currency_symbol',
            company_id=company_id
        ).first()
    
    currency_symbol_value = currency_symbol.setting_value if currency_symbol else 'Rs. '
    
    # Logo path resolution - convert to base64 data URI for xhtml2pdf
    import os
    import base64
    from app.models import Setting
    logo_data_uri = ''
    
    # Try to get logo from general settings first (upload-logo saves here)
    logo_setting = Setting.query.filter_by(
        setting_category='general',
        setting_key='logo_path',
        company_id=company_id
    ).first()
    
    if not logo_setting:
        # Fallback to receipt settings
        logo_setting = Setting.query.filter_by(
            setting_category='receipt',
            setting_key='receipt_logo',
            company_id=company_id
        ).first()
    
    # Convert to base64 if logo setting exists
    if logo_setting and logo_setting.setting_value:
        logo_path_raw = logo_setting.setting_value.strip()
        
        # Remove leading '/' or '/static/uploads/' if present
        if logo_path_raw.startswith('/static/uploads/'):
            logo_path_raw = logo_path_raw[16:]
        elif logo_path_raw.startswith('/'):
            logo_path_raw = logo_path_raw[1:]
        elif logo_path_raw.startswith('static/uploads/'):
            logo_path_raw = logo_path_raw[15:]
        elif logo_path_raw.startswith('uploads/'):
            logo_path_raw = logo_path_raw[8:]
        
        # Build absolute path
        logo_abs_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'static', 'uploads', os.path.basename(logo_path_raw)
        ))
        
        # Convert to base64 if file exists
        if os.path.isfile(logo_abs_path):
            try:
                # Try to use PIL for better image handling and optimization
                try:
                    from PIL import Image
                    from io import BytesIO
                    
                    # Open image with PIL
                    img = Image.open(logo_abs_path)
                    
                    # Convert RGBA to RGB if necessary (for JPEG)
                    if img.mode == 'RGBA':
                        # Create white background
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Optimize image - don't resize, just encode at high quality
                    img_bytes = BytesIO()
                    ext = os.path.splitext(logo_abs_path)[1].lower()
                    
                    if ext in ['.jpg', '.jpeg']:
                        img.save(img_bytes, format='JPEG', quality=95, optimize=False)
                        mime_type = 'image/jpeg'
                    else:  # PNG
                        img.save(img_bytes, format='PNG', optimize=True)
                        mime_type = 'image/png'
                    
                    logo_bytes = img_bytes.getvalue()
                    logo_b64 = base64.b64encode(logo_bytes).decode('utf-8')
                    logo_data_uri = f'data:{mime_type};base64,{logo_b64}'
                    current_app.logger.info(f"Logo optimized and encoded as data URI from {logo_abs_path}, size: {len(logo_data_uri)} bytes")
                    
                except ImportError:
                    # Fallback to direct file encoding if PIL not available
                    current_app.logger.warning("PIL not available, encoding logo directly")
                    with open(logo_abs_path, 'rb') as f:
                        logo_bytes = f.read()
                        logo_b64 = base64.b64encode(logo_bytes).decode('utf-8')
                        ext = os.path.splitext(logo_abs_path)[1].lower()
                        mime_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}
                        mime_type = mime_types.get(ext, 'image/jpeg')
                        logo_data_uri = f'data:{mime_type};base64,{logo_b64}'
                        current_app.logger.info(f"Logo encoded as data URI from {logo_abs_path}, size: {len(logo_data_uri)} bytes")
                
            except Exception as e:
                current_app.logger.warning(f"Failed to encode logo: {str(e)}")
                logo_data_uri = ''
        else:
            current_app.logger.warning(f"Logo file not found: {logo_abs_path}")
            logo_data_uri = ''
    
    # Pass to template as logo_url (will be used in img src)
    logo_url = logo_data_uri
    
    # Cashier name from user
    cashier_name = getattr(getattr(sale, 'user', None), 'username', 'Cashier')
    
    # Payment status determination
    if balance_due == 0 and sale.total > 0:
        payment_status = 'Paid'
    elif balance_due > 0 and getattr(sale, 'paid_amount', 0) > 0:
        payment_status = 'Partial'
    else:
        payment_status = 'Pending'
    
    # Convert UTC time to local time (add 6 hours for Asia/Kolkata timezone)
    local_sale_date = sale.date + timedelta(hours=6)
    
    # Due date calculation (30 days from invoice date)
    due_date = (local_sale_date + timedelta(days=30)).strftime('%Y-%m-%d')
    
    context = {
        # Basic sale info
        'sale': sale,
        'invoice_number': f"INV-{sale.id}",
        'invoice_date': local_sale_date.strftime('%Y-%m-%d'),
        'due_date': due_date,
        'payment_status': payment_status,
        'status': payment_status,  # Alias for template compatibility
        'sale_date': local_sale_date.strftime('%Y-%m-%d'),
        'sale_time': local_sale_date.strftime('%H:%M'),
        
        # Customer info
        'customer_name': sale.customer or 'Walk-in Customer',
        'customer_address': getattr(sale, 'customer_address', ''),
        'customer_phone': getattr(sale, 'customer_phone', ''),
        'customer_email': getattr(sale, 'customer_email', ''),
        
        # Shipping info (if applicable)
        'shipping_name': getattr(sale, 'shipping_name', ''),
        'shipping_address': getattr(sale, 'shipping_address', ''),
        'shipping_phone': getattr(sale, 'shipping_phone', ''),
        
        # Payment info
        'payment_method': sale.payment,
        'cashier_name': cashier_name,
        
        # Items
        'items': items_data,

        # Totals
        'subtotal': subtotal_before,
        'subtotal_after_discount': subtotal_after,
        'discount': discount_total,
        'discount_total': discount_total,
        'tax_amount': tax_total,
        'tax_total': tax_total,
        'tax_rate': tax_rate,
        'total': sale.total,
        'paid_amount': paid_amount,
        'balance_due': balance_due,
        'cash_given': sale.cash_given,
        'change': max(0, change),
        'balance': getattr(sale, 'balance', 0),
        
        # Business info - Use business_name key which is now available from get_receipt_settings
        'business_name': receipt_settings.get('business_name', 'POS SYSTEM'),
        'business_address': receipt_settings.get('business_address'),
        'business_phone': receipt_settings.get('business_phone'),
        'business_email': receipt_settings.get('business_email'),
        'business_gst': receipt_settings.get('business_gst'),
        'website': receipt_settings.get('website', ''),
        'logo_url': logo_url,
        
        # Template content
        'thank_you_message': receipt_settings.get('thank_you_message', 'Thank You for Your Business!'),
        'warranty_info': receipt_settings.get('warranty_info'),
        'footer_text': receipt_settings.get('footer_text', 'Generated by Web POS System'),
        'notes': receipt_settings.get('invoice_notes'),
        'terms': receipt_settings.get('invoice_terms'),
        
        # Currency
        'currency': currency_symbol_value,
        'currency_symbol': currency_symbol_value,
        # Whether to show QR code on receipt
        'show_qr_code': _bool_setting(receipt_settings.get('show_qr_code', 'true'))
    }
    
    # Select template based on format
    if receipt_format == 'a4':
        template = 'invoices/invoice_a4.html'
    elif receipt_format == 'a5':
        template = 'invoices/invoice_a5.html'
    else:  # thermal
        template = 'invoices/thermal_receipt_80mm_professional.html'
    
    return render_template(template, **context)


@sales_bp.route('/api/sales/<int:sale_id>/receipt/pdf')
@login_required
def download_receipt_pdf(sale_id):
    """Download receipt as PDF in specified format."""
    from xhtml2pdf import pisa
    from io import BytesIO
    from app.routes.invoices import get_receipt_settings
    
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404
    
    try:
        # Get format from query parameter, default to 'a4'
        format_type = request.args.get('format', 'a4').lower()
        
        # Validate format
        if format_type not in ['thermal', 'a4', 'a5']:
            format_type = 'a4'
        
        # Get receipt settings
        company_id = get_company_id()
        receipt_settings = get_receipt_settings(company_id)
        
        # Prepare template data matching the invoice template variables
        business_name = receipt_settings.get('business_name', 'YOUR STORE')
        
        # Build items list
        items = []
        for sale_item in sale.items:
            # Get product name from relationship
            product_name = sale_item.product.name if hasattr(sale_item, 'product') and sale_item.product else 'Unknown Product'
            
            # Use product ID as item code (fallback to sale_item.product_id or 'N/A')
            if hasattr(sale_item, 'product') and sale_item.product and getattr(sale_item.product, 'id', None):
                product_code = str(sale_item.product.id)
            else:
                product_code = str(getattr(sale_item, 'product_id', 'N/A') or 'N/A')
            
            # Get price from SaleItem (correct attribute name)
            unit_price = float(sale_item.price) if hasattr(sale_item, 'price') else 0.0
            qty = float(sale_item.quantity)
            discount = float(sale_item.discount) if sale_item.discount else 0.0
            tax = float(sale_item.tax) if sale_item.tax else 0.0
            line_total = (unit_price * qty) - discount + tax
            
            items.append({
                'code': product_code,
                'description': product_name,
                'qty': qty,
                'unit_price': unit_price,
                'discount': discount,
                'tax': tax,
                'total': line_total
            })
        
        # Calculate totals from actual sale item values
        subtotal = sum(item['unit_price'] * item['qty'] for item in items)
        discount_total = sum(item['discount'] for item in items)
        tax_total = sum(item['tax'] for item in items)
        total = sale.total
        
        # Calculate paid amount correctly
        # For Cash/Cheque: always fully paid
        # For Credit: paid_amount = total - balance
        if sale.payment in ['Cash', 'Cheque']:
            paid_amount = sale.total
            balance_due = 0.0
        else:
            paid_amount = sale.total - (sale.balance if sale.balance > 0 else 0)
            balance_due = max(0, sale.balance)
        
        # Build template data
        template_data = {
            'company': {
                'name': business_name,
                'address': receipt_settings.get('business_address', ''),
                'city': receipt_settings.get('business_city', ''),
                'phone': receipt_settings.get('business_phone', ''),
                'email': receipt_settings.get('business_email', ''),
                'website': receipt_settings.get('business_website', ''),
                'tax_id': receipt_settings.get('business_gst', ''),
            },
            'customer': {
                'name': sale.customer.name if (hasattr(sale, 'customer') and hasattr(sale.customer, 'name')) else (str(sale.customer) if sale.customer else 'Walk-in Customer'),
                'company': sale.customer.company_name if sale.customer and hasattr(sale.customer, 'company_name') else '',
                'address': sale.customer.address if sale.customer and hasattr(sale.customer, 'address') else '',
                'city': sale.customer.city if sale.customer and hasattr(sale.customer, 'city') else '',
                'phone': sale.customer.phone if sale.customer and hasattr(sale.customer, 'phone') else '',
                'email': sale.customer.email if sale.customer and hasattr(sale.customer, 'email') else '',
            },
            'invoice_number': f"RECEIPT-{sale.id}",
            'invoice_date': sale.date.strftime('%m/%d/%Y') if sale.date else datetime.now().strftime('%m/%d/%Y'),
            'due_date': '',
            'status': 'Paid',
            'items': items,
            'subtotal': f"Rs. {subtotal:.2f}",
            'discount': f"Rs. {discount_total:.2f}",
            'tax': f"Rs. {tax_total:.2f}",
            'total': f"Rs. {total:.2f}",
            'paid_amount': f"Rs. {paid_amount:.2f}",
            'balance_due': f"Rs. {balance_due:.2f}",
            'show_qr_code': _bool_setting(receipt_settings.get('show_qr_code', 'true'))
        }
        
        # Select template based on format
        if format_type == 'a4':
            template_name = 'invoices/invoice_a4_professional.html'
        elif format_type == 'a5':
            template_name = 'invoices/invoice_a5_professional.html'
        else:  # thermal
            template_name = 'invoices/thermal_receipt_80mm.html'
        
        # Render HTML template
        html_content = render_template(template_name, **template_data)
        
        # Convert HTML to PDF using xhtml2pdf
        pdf_buffer = BytesIO()
        pisa.CreatePDF(
            BytesIO(html_content.encode('utf-8')),
            pdf_buffer,
            encoding='UTF-8'
        )
        pdf_buffer.seek(0)
        
        # Return PDF with cache-busting headers
        filename = f'receipt_{sale_id}_{format_type}.pdf'
        response = send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
        # Prevent browser caching
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"PDF generation failed: {str(e)}", exc_info=True)
        return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500


@sales_bp.route('/api/sales/<int:sale_id>/receipt/html-public')
def receipt_html_public(sale_id):
    """Serve HTML receipt template without authentication (public link for WhatsApp/Email)."""
    from app.routes.invoices import get_receipt_settings
    from datetime import datetime, timedelta
    
    # Get sale without company restriction for public access
    sale = Sale.query.get(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404
    
    # Get format from query parameter, default to thermal
    receipt_format = request.args.get('format', 'thermal').lower()
    if receipt_format not in ['thermal', 'a4', 'a5']:
        receipt_format = 'thermal'
    
    # Get sale items
    items = SaleItem.query.filter_by(sale_id=sale.id).all()
    
    # Prepare item data for template (same as receipt_html)
    items_data = []
    subtotal = 0
    for item in items:
        product_name = item.product.name if hasattr(item, 'product') and item.product else 'Unknown Product'
        product_code = 'N/A'
        if hasattr(item, 'product') and item.product:
            if hasattr(item.product, 'product_code') and item.product.product_code:
                product_code = item.product.product_code
            elif hasattr(item.product, 'barcode') and item.product.barcode:
                product_code = item.product.barcode
        
        item_discount = item.discount if hasattr(item, 'discount') and item.discount else 0
        item_tax = item.tax if hasattr(item, 'tax') and item.tax else 0
        item_price_before_discount = item.price * item.quantity
        item_total = item_price_before_discount - item_discount + item_tax
        
        item_data = {
            'code': product_code,
            'name': product_name,
            'quantity': item.quantity,
            'unit_price': item.price,
            'discount': item_discount,
            'tax_amount': item_tax,
            'total': item_total
        }
        items_data.append(item_data)
        subtotal += item_total
    
    discount_total = sum(item['discount'] for item in items_data)
    tax_total = sum(item['tax_amount'] for item in items_data)
    
    tax_rate = 0
    if tax_total > 0 and subtotal > 0:
        tax_rate = round((tax_total / subtotal) * 100, 1)
    
    change = sale.cash_given - sale.total if sale.payment == 'Cash' else 0
    
    if sale.payment in ['Cash', 'Cheque']:
        paid_amount = sale.total
        balance_due = 0.0
    else:
        paid_amount = sale.total - (sale.balance if sale.balance > 0 else 0)
        balance_due = max(0, sale.balance)
    
    # Get receipt settings using company_id from sale
    company_id = sale.company_id if hasattr(sale, 'company_id') else None
    receipt_settings = get_receipt_settings(company_id)
    
    # Get currency symbol
    from app.models import Setting
    currency_symbol = Setting.query.filter_by(
        setting_category='currency',
        setting_key='symbol',
        company_id=company_id
    ).first()
    
    if not currency_symbol:
        currency_symbol = Setting.query.filter_by(
            setting_category='general',
            setting_key='currency_symbol',
            company_id=company_id
        ).first()
    
    currency_symbol_value = currency_symbol.setting_value if currency_symbol else 'Rs. '
    
    # Logo path resolution
    import os
    import base64
    logo_data_uri = ''
    
    logo_setting = Setting.query.filter_by(
        setting_category='general',
        setting_key='logo_path',
        company_id=company_id
    ).first()
    
    if not logo_setting:
        logo_setting = Setting.query.filter_by(
            setting_category='receipt',
            setting_key='receipt_logo',
            company_id=company_id
        ).first()
    
    if logo_setting and logo_setting.setting_value:
        logo_path_raw = logo_setting.setting_value.strip()
        if logo_path_raw.startswith('/static/uploads/'):
            logo_path_raw = logo_path_raw[16:]
        elif logo_path_raw.startswith('/'):
            logo_path_raw = logo_path_raw[1:]
        elif logo_path_raw.startswith('static/uploads/'):
            logo_path_raw = logo_path_raw[15:]
        elif logo_path_raw.startswith('uploads/'):
            logo_path_raw = logo_path_raw[8:]
        
        logo_abs_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'static', 'uploads', os.path.basename(logo_path_raw)
        ))
        
        if os.path.isfile(logo_abs_path):
            try:
                try:
                    from PIL import Image
                    from io import BytesIO
                    img = Image.open(logo_abs_path)
                    if img.mode == 'RGBA':
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    img_bytes = BytesIO()
                    ext = os.path.splitext(logo_abs_path)[1].lower()
                    if ext in ['.jpg', '.jpeg']:
                        img.save(img_bytes, format='JPEG', quality=95, optimize=False)
                        mime_type = 'image/jpeg'
                    else:
                        img.save(img_bytes, format='PNG', optimize=True)
                        mime_type = 'image/png'
                    
                    logo_bytes = img_bytes.getvalue()
                    logo_b64 = base64.b64encode(logo_bytes).decode('utf-8')
                    logo_data_uri = f'data:{mime_type};base64,{logo_b64}'
                except ImportError:
                    with open(logo_abs_path, 'rb') as f:
                        logo_bytes = f.read()
                        logo_b64 = base64.b64encode(logo_bytes).decode('utf-8')
                        ext = os.path.splitext(logo_abs_path)[1].lower()
                        mime_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}
                        mime_type = mime_types.get(ext, 'image/jpeg')
                        logo_data_uri = f'data:{mime_type};base64,{logo_b64}'
            except Exception as e:
                current_app.logger.warning(f"Failed to encode logo: {str(e)}")
                logo_data_uri = ''
    
    logo_url = logo_data_uri
    
    # Cashier name
    cashier_name = getattr(getattr(sale, 'user', None), 'username', 'Cashier')
    
    # Payment status
    if balance_due == 0 and sale.total > 0:
        payment_status = 'Paid'
    elif balance_due > 0 and getattr(sale, 'paid_amount', 0) > 0:
        payment_status = 'Partial'
    else:
        payment_status = 'Pending'
    
    # Convert UTC to local time
    local_sale_date = sale.date + timedelta(hours=6)
    due_date = (local_sale_date + timedelta(days=30)).strftime('%Y-%m-%d')
    
    context = {
        'sale': sale,
        'invoice_number': f"INV-{sale.id}",
        'invoice_date': local_sale_date.strftime('%Y-%m-%d'),
        'due_date': due_date,
        'payment_status': payment_status,
        'status': payment_status,
        'sale_date': local_sale_date.strftime('%Y-%m-%d'),
        'sale_time': local_sale_date.strftime('%H:%M'),
        
        'customer_name': sale.customer or 'Walk-in Customer',
        'customer_address': getattr(sale, 'customer_address', ''),
        'customer_phone': getattr(sale, 'customer_phone', ''),
        'customer_email': getattr(sale, 'customer_email', ''),
        
        'shipping_name': getattr(sale, 'shipping_name', ''),
        'shipping_address': getattr(sale, 'shipping_address', ''),
        'shipping_phone': getattr(sale, 'shipping_phone', ''),
        
        'payment_method': sale.payment,
        'cashier_name': cashier_name,
        
        'items': items_data,
        
        'subtotal': subtotal,
        'discount': discount_total,
        'discount_total': discount_total,
        'tax_amount': tax_total,
        'tax_total': tax_total,
        'tax_rate': tax_rate,
        'total': sale.total,
        'paid_amount': paid_amount,
        'balance_due': balance_due,
        'cash_given': sale.cash_given,
        'change': max(0, change),
        'balance': getattr(sale, 'balance', 0),
        
        'business_name': receipt_settings.get('business_name', 'POS SYSTEM'),
        'business_address': receipt_settings.get('business_address'),
        'business_phone': receipt_settings.get('business_phone'),
        'business_email': receipt_settings.get('business_email'),
        'business_gst': receipt_settings.get('business_gst'),
        'website': receipt_settings.get('website', ''),
        'logo_url': logo_url,
        
        'thank_you_message': receipt_settings.get('thank_you_message', 'Thank You for Your Business!'),
        'warranty_info': receipt_settings.get('warranty_info'),
        'footer_text': receipt_settings.get('footer_text', 'Generated by Web POS System'),
        'notes': receipt_settings.get('invoice_notes'),
        'terms': receipt_settings.get('invoice_terms'),
        
        'currency': currency_symbol_value,
        'currency_symbol': currency_symbol_value
    }
    
    # Select template based on format
    if receipt_format == 'a4':
        template = 'invoices/invoice_a4.html'
    elif receipt_format == 'a5':
        template = 'invoices/invoice_a5.html'
    else:
        template = 'invoices/thermal_receipt_80mm_professional.html'
    
    return render_template(template, **context)

@sales_bp.route('/api/sales/<int:sale_id>/receipt/pdf-public')
def download_receipt_pdf_public(sale_id):
    """Download receipt as PDF without authentication (public link for WhatsApp/Email)."""
    from xhtml2pdf import pisa
    from io import BytesIO
    from app.routes.invoices import get_receipt_settings
    
    try:
        # Get sale without company restriction for public access
        sale = Sale.query.get(sale_id)
        if not sale:
            return jsonify({'error': 'Sale not found'}), 404
        
        # Get format from query parameter, default to 'a4'
        format_type = request.args.get('format', 'a4').lower()
        
        # Validate format
        if format_type not in ['thermal', 'a4', 'a5']:
            format_type = 'a4'
        
        # Get receipt settings for the sale's company
        company_id = sale.company_id
        receipt_settings = get_receipt_settings(company_id)
        
        # Prepare template data matching the invoice template variables
        business_name = receipt_settings.get('business_name', 'YOUR STORE')
        
        # Build items list
        items = []
        for sale_item in sale.items:
            # Get product name from relationship
            product_name = sale_item.product.name if hasattr(sale_item, 'product') and sale_item.product else 'Unknown Product'
            
            # Use product ID as item code (fallback to sale_item.product_id or 'N/A')
            if hasattr(sale_item, 'product') and sale_item.product and getattr(sale_item.product, 'id', None):
                product_code = str(sale_item.product.id)
            else:
                product_code = str(getattr(sale_item, 'product_id', 'N/A') or 'N/A')
            
            # Get price from SaleItem (correct attribute name)
            unit_price = float(sale_item.price) if hasattr(sale_item, 'price') else 0.0
            qty = float(sale_item.quantity)
            discount = float(sale_item.discount) if sale_item.discount else 0.0
            tax = float(sale_item.tax) if sale_item.tax else 0.0
            line_total = (unit_price * qty) - discount + tax
            
            items.append({
                'code': product_code,
                'description': product_name,
                'qty': qty,
                'unit_price': unit_price,
                'discount': discount,
                'tax': tax,
                'total': line_total
            })
        
        # Calculate totals from actual sale item values
        subtotal = sum(item['unit_price'] * item['qty'] for item in items)
        discount_total = sum(item['discount'] for item in items)
        tax_total = sum(item['tax'] for item in items)
        total = sale.total
        
        # Calculate paid amount correctly
        # For Cash/Cheque: always fully paid
        # For Credit: paid_amount = total - balance
        if sale.payment in ['Cash', 'Cheque']:
            paid_amount = sale.total
            balance_due = 0.0
        else:
            paid_amount = sale.total - (sale.balance if sale.balance > 0 else 0)
            balance_due = max(0, sale.balance)
        
        # Build template data
        template_data = {
            'company': {
                'name': business_name,
                'address': receipt_settings.get('business_address', ''),
                'city': receipt_settings.get('business_city', ''),
                'phone': receipt_settings.get('business_phone', ''),
                'email': receipt_settings.get('business_email', ''),
                'website': receipt_settings.get('business_website', ''),
                'tax_id': receipt_settings.get('business_gst', ''),
            },
            'customer': {
                'name': sale.customer.name if (hasattr(sale, 'customer') and hasattr(sale.customer, 'name')) else (str(sale.customer) if sale.customer else 'Walk-in'),
                'company': sale.customer.company_name if sale.customer and hasattr(sale.customer, 'company_name') else '',
                'address': sale.customer.address if sale.customer and hasattr(sale.customer, 'address') else '',
                'city': sale.customer.city if sale.customer and hasattr(sale.customer, 'city') else '',
                'phone': sale.customer.phone if sale.customer and hasattr(sale.customer, 'phone') else '',
                'email': sale.customer.email if sale.customer and hasattr(sale.customer, 'email') else '',
            },
            'invoice_number': f"RECEIPT-{sale.id}",
            'invoice_date': sale.date.strftime('%m/%d/%Y') if sale.date else datetime.now().strftime('%m/%d/%Y'),
            'due_date': '',
            'status': 'Paid',
            'items': items,
            'subtotal': f"Rs. {subtotal:.2f}",
            'discount': f"Rs. {discount_total:.2f}",
            'tax': f"Rs. {tax_total:.2f}",
            'total': f"Rs. {total:.2f}",
            'paid_amount': f"Rs. {paid_amount:.2f}",
            'balance_due': f"Rs. {balance_due:.2f}"
        }
        
        # Select template based on format
        if format_type == 'a4':
            template_name = 'invoices/invoice_a4_professional.html'
        elif format_type == 'a5':
            template_name = 'invoices/invoice_a5_professional.html'
        else:  # thermal
            template_name = 'invoices/thermal_receipt_80mm.html'
        
        # Render HTML template
        html_content = render_template(template_name, **template_data)
        
        # Convert HTML to PDF using xhtml2pdf
        pdf_buffer = BytesIO()
        pisa.CreatePDF(
            BytesIO(html_content.encode('utf-8')),
            pdf_buffer,
            encoding='UTF-8'
        )
        pdf_buffer.seek(0)
        
        # Return PDF with cache-busting headers
        filename = f'receipt_sale_{sale_id}_{format_type}.pdf'
        response = send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
        
        # Prevent browser caching
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Public PDF generation failed: {str(e)}", exc_info=True)
        return jsonify({'error': f'PDF generation failed: {str(e)}'}), 500

@sales_bp.route('/api/sales/<int:sale_id>/print-receipt', methods=['GET', 'POST'])
@csrf.exempt
@login_required
def print_receipt(sale_id):
    """Print receipt in various formats.
    
    Accepts format via query parameter or JSON body:
        GET: /print-receipt?format=thermal|a4|a5
        POST: {"format": "thermal|a4|a5"}
    
    Uses default format from Settings > Receipt Settings if not specified.
    """
    from xhtml2pdf import pisa
    from io import BytesIO
    from app.routes.invoices import get_receipt_settings
    
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404
    
    # Get format from query parameter first, then JSON body, then default
    format_type = request.args.get('format')
    
    if not format_type:
        try:
            data = request.get_json() or {}
            format_type = data.get('format')
        except:
            pass
    
    # If no format specified, use default from settings
    if not format_type:
        company_id = get_company_id()
        receipt_settings = get_receipt_settings(company_id)
        format_type = receipt_settings.get('default_receipt_format', 'thermal')
    
    if format_type not in ['thermal', 'a4', 'a5']:
        format_type = 'thermal'

    # Get receipt settings using integrated function
    company_id = get_company_id()
    receipt_settings = get_receipt_settings(company_id)
    
    try:
        # Prepare template data matching the invoice template variables
        business_name = receipt_settings.get('business_name', 'YOUR STORE')
        
        # Build items list
        items = []
        for sale_item in sale.items:
            # Get product name from relationship
            product_name = sale_item.product.name if hasattr(sale_item, 'product') and sale_item.product else 'Unknown Product'
            
            # Use product ID as item code (fallback to sale_item.product_id or 'N/A')
            if hasattr(sale_item, 'product') and sale_item.product and getattr(sale_item.product, 'id', None):
                product_code = str(sale_item.product.id)
            else:
                product_code = str(getattr(sale_item, 'product_id', 'N/A') or 'N/A')
            
            # Get price from SaleItem (correct attribute name)
            unit_price = float(sale_item.price) if hasattr(sale_item, 'price') else 0.0
            qty = float(sale_item.quantity)
            discount = float(sale_item.discount) if sale_item.discount else 0.0
            tax = float(sale_item.tax) if sale_item.tax else 0.0
            line_total = (unit_price * qty) - discount + tax
            
            items.append({
                'code': product_code,
                'description': product_name,
                'qty': qty,
                'unit_price': unit_price,
                'discount': discount,
                'tax': tax,
                'total': line_total
            })
        
        # Calculate totals from numeric values
        subtotal = sum(item['unit_price'] * item['qty'] for item in items)
        discount_total = sum(item['discount'] for item in items)
        tax_total = sum(item['tax'] for item in items)
        total = sale.total
        
        # Calculate paid amount correctly
        # For Cash/Cheque: always fully paid
        # For Credit: paid_amount = total - balance
        if sale.payment in ['Cash', 'Cheque']:
            paid_amount = sale.total
            balance_due = 0.0
        else:
            paid_amount = sale.total - (sale.balance if sale.balance > 0 else 0)
            balance_due = max(0, sale.balance)
        
        # Build template data
        template_data = {
            'company': {
                'name': business_name,
                'address': receipt_settings.get('business_address', ''),
                'city': receipt_settings.get('business_city', ''),
                'phone': receipt_settings.get('business_phone', ''),
                'email': receipt_settings.get('business_email', ''),
                'website': receipt_settings.get('business_website', ''),
                'tax_id': receipt_settings.get('business_gst', ''),
            },
            'customer': {
                'name': sale.customer.name if (hasattr(sale, 'customer') and hasattr(sale.customer, 'name')) else (str(sale.customer) if sale.customer else 'Walk-in Customer'),
                'company': sale.customer.company_name if sale.customer and hasattr(sale.customer, 'company_name') else '',
                'address': sale.customer.address if sale.customer and hasattr(sale.customer, 'address') else '',
                'city': sale.customer.city if sale.customer and hasattr(sale.customer, 'city') else '',
                'phone': sale.customer.phone if sale.customer and hasattr(sale.customer, 'phone') else '',
                'email': sale.customer.email if sale.customer and hasattr(sale.customer, 'email') else '',
            },
            'invoice_number': f"RECEIPT-{sale.id}",
            'invoice_date': sale.date.strftime('%m/%d/%Y') if sale.date else datetime.now().strftime('%m/%d/%Y'),
            'due_date': '',
            'status': 'Paid',
            'items': items,
            'subtotal': f"Rs. {subtotal:.2f}",
            'discount': f"Rs. {discount_total:.2f}",
            'tax': f"Rs. {tax_total:.2f}",
            'total': f"Rs. {total:.2f}",
            'paid_amount': f"Rs. {paid_amount:.2f}",
            'balance_due': f"Rs. {balance_due:.2f}"
        }
        
        # Select template based on format
        if format_type == 'a4':
            template_name = 'invoices/invoice_a4_professional.html'
        elif format_type == 'a5':
            template_name = 'invoices/invoice_a5_professional.html'
        else:  # thermal
            template_name = 'invoices/thermal_receipt_80mm_professional.html'
        
        # Build template context with proper variable types (not formatted strings)
        template_context = {
            'company': template_data['company'],
            'customer': template_data['customer'],
            'invoice_number': template_data['invoice_number'],
            'invoice_date': template_data['invoice_date'],
            'due_date': template_data['due_date'],
            'status': template_data['status'],
            'items': items,
            'subtotal': subtotal,
            'discount_total': discount_total,
            'tax_amount': tax_total,
            'tax_total': tax_total,
            'tax_rate': tax_total / subtotal * 100 if subtotal > 0 else 0,
            'total': total,
            'paid_amount': paid_amount,
            'balance_due': balance_due,
            'cash_given': sale.cash_given,
            'change': max(0, sale.cash_given - total) if sale.payment == 'Cash' else 0,
            'payment_method': sale.payment,
            'currency_symbol': 'Rs. ',
            'thank_you_message': receipt_settings.get('thank_you_message', 'Thank You'),
            'business_name': business_name,
            'website': receipt_settings.get('business_website', ''),
            'footer_text': 'Receipt',
            'sale_time': (sale.date + timedelta(hours=6)).strftime('%H:%M') if sale.date else '',
            'show_qr_code': _bool_setting(receipt_settings.get('show_qr_code', 'true'))
        }
        
        # Render HTML template
        html_content = render_template(template_name, **template_context)
        
        # Return HTML with JavaScript to trigger print dialog
        from flask import Response
        html_with_print = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @media print {{
            body {{ margin: 0; padding: 0; }}
        }}
    </style>
</head>
<body>
{html_content}
<script>
    window.addEventListener('load', function() {{
        setTimeout(function() {{
            window.print();
        }}, 500);
    }});
</script>
</body>
</html>'''
        
        return Response(html_with_print, mimetype='text/html')
        
    except Exception as e:
        current_app.logger.error(f"Print receipt generation failed: {str(e)}", exc_info=True)
        return jsonify({'error': f'Print receipt generation failed: {str(e)}'}), 500

@sales_bp.route('/api/sales/<int:sale_id>/send-receipt-whatsapp', methods=['POST'])
@csrf.exempt
@login_required
def send_receipt_whatsapp(sale_id):
    """Send receipt via WhatsApp to customer.
    
    Expects JSON:
        {
            "phone_number": "+919876543210" or "919876543210",
            "format": "thermal" (default), "a4", or "a5"
        }
    
    Returns receipt via WhatsApp using wa.me link with receipt HTML embedded in message.
    """
    from app.utils.whatsapp_sender import generate_whatsapp_link
    from app.routes.invoices import get_receipt_settings
    import json
    
    try:
        sale = get_sale_secure(sale_id)
        if not sale:
            return jsonify({'success': False, 'error': 'Sale not found'}), 404
        
        data = request.get_json() or {}
        phone_number = data.get('phone_number')
        format_type = data.get('format', 'thermal')
        
        if not phone_number:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400
        
        if format_type not in ['thermal', 'a4', 'a5']:
            format_type = 'thermal'
        
        # Get receipt settings
        company_id = get_company_id()
        receipt_settings = get_receipt_settings(company_id)
        currency_symbol = receipt_settings.get('currency_symbol', 'Rs. ')
        
        # Create a text summary for WhatsApp message
        items_text = "Items:\n"
        subtotal = 0
        for item in sale.items:
            item_total = item.price * item.quantity
            product_name = item.product.name if item.product else 'Unknown Product'
            items_text += f"• {product_name} x{item.quantity} - {currency_symbol}{item_total:.2f}\n"
            subtotal += item_total
        
        # Calculate totals
        discount_total = sale.discount or 0
        tax_amount = sale.tax or 0
        total = sale.total or (subtotal - discount_total + tax_amount)
        
        # Get the base URL for receipt link
        from urllib.parse import urljoin
        base_url = request.host_url.rstrip('/')
        receipt_url = f"{base_url}/sales/{sale_id}/receipt/html?format={format_type}"
        
        # Build message text with receipt link
        message_text = f"""Thank you for your purchase!

Sale #: {sale.id}

{items_text}
Discount: {currency_symbol}{discount_total:.2f}
Tax: {currency_symbol}{tax_amount:.2f}
Total: {currency_symbol}{total:.2f}

Payment: {sale.payment}

View Receipt:
{receipt_url}

{receipt_settings.get('thank_you_message', 'Thank you for shopping with us!')}"""
        
        # Generate WhatsApp link
        whatsapp_link = generate_whatsapp_link(phone_number, message_text)
        
        if not whatsapp_link:
            return jsonify({'success': False, 'error': 'Invalid phone number format'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Receipt ready to send via WhatsApp',
            'whatsapp_link': whatsapp_link,
            'receipt_text': message_text,
            'receipt_url': receipt_url,
            'format': format_type
        }), 200
        
    except Exception as e:
        import traceback
        error_msg = f'{str(e)} - {traceback.format_exc()}'
        print(f'[ERROR send_receipt_whatsapp] {error_msg}', flush=True)
        return jsonify({'success': False, 'error': f'Failed to generate receipt: {str(e)}'}), 500

@sales_bp.route('/api/sales/<int:sale_id>/send-email', methods=['POST'])
@login_required
def send_email_receipt(sale_id):
    """Send receipt PDF to customer's email.
    
    Expects JSON:
        {
            "email": "customer@example.com",
            "format": "thermal" (default), "a4", or "a3"
        }
    
    Uses default format from Settings > Receipt Settings if not specified.
    """
    from app.utils.multi_format_receipt_generator import MultiFormatReceiptGenerator
    from app.routes.invoices import get_receipt_settings
    
    data = request.get_json() or {}
    to_email = data.get('email')
    format_type = data.get('format')
    
    if not to_email:
        return jsonify({'error': 'Email address required'}), 400
    
    company_id = get_company_id()
    # If no format specified, use default from settings
    if not format_type:
        receipt_settings = get_receipt_settings(company_id)
        format_type = receipt_settings.get('default_receipt_format', 'thermal')
    
    if format_type not in ['thermal', 'a4', 'a3']:
        format_type = 'thermal'

    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404

    # Get receipt settings
    receipt_settings = get_receipt_settings(company_id)
    
    # Format business_settings for the generator
    # Map company_name to business_name for generator compatibility
    mapped_settings = receipt_settings.copy()
    if 'company_name' in mapped_settings:
        mapped_settings['business_name'] = mapped_settings.pop('company_name')
    business_settings = {'receipt': mapped_settings}
    
    generator = MultiFormatReceiptGenerator()
    pdf_buffer = generator.generate_receipt_pdf(sale, sale.items, format_type=format_type, business_settings=business_settings)
    pdf_buffer.seek(0)
    pdf_bytes = pdf_buffer.read()

    # Get business name from receipt settings
    business_name = receipt_settings.get('company_name', 'POS System')
    
    subject = f'Receipt from {business_name} - Sale #{sale_id}'
    body = f'Thank you for your purchase. Please find attached your {format_type.upper()} receipt for Sale #{sale_id}.'

    filename = f'receipt_{sale_id}_{format_type}.pdf'
    ok, msg = send_email(to_email, subject, body, attachments=[(filename, pdf_bytes, 'application/pdf')])
    if not ok:
        return jsonify({'error': msg}), 500

    return jsonify({'success': True, 'message': f'Email sent with {format_type} format receipt'})


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

    
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404


    # Professional WhatsApp Receipt - Direct Twilio
    cashier = current_user.username
    
    subtotal = sum(item.quantity * item.price for item in sale.items)
    
    items = '\n'.join([
        f"{item.product.name[:20]:<20}x{int(item.quantity)} = Rs.{item.quantity*item.price:>8.2f}"
        for item in sale.items
    ])
    
    # Get base URL for links
    from urllib.parse import urljoin
    base_url = request.host_url.rstrip('/')
    receipt_html_url = f"{base_url}/sales/{sale.id}/receipt/html?format=a4"
    
    text = f"""*POS SYSTEM*

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

View Receipt (Same as Sales History):
{receipt_html_url}

Thank you for shopping!"""

    # Prefer Twilio if configured and available
    twilio_enabled = (send_whatsapp_via_twilio is not None and 
                     current_app.config.get('TWILIO_ACCOUNT_SID') and 
                     current_app.config.get('TWILIO_AUTH_TOKEN') and 
                     current_app.config.get('TWILIO_WHATSAPP_FROM'))
    if twilio_enabled:
        ok, res = send_whatsapp_via_twilio(phone_digits, text)
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


@sales_bp.route('/api/sales/<int:sale_id>/profit')
@login_required
@require_permission('can_view_profit')
def sale_profit(sale_id):
    """Calculate profit for a sale: sum((price - cost_price) * qty)"""
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404
    profit = 0.0
    details = []
    for it in sale.items:
        cost = it.product.cost_price if it.product and it.product.cost_price else 0.0
        line_profit = (it.price - cost) * it.quantity
        profit += line_profit
        details.append({'product': it.product.name if it.product else 'Unknown', 'qty': float(it.quantity) if it.quantity else 0, 'line_profit': float(line_profit)})

    return jsonify({'sale_id': sale.id, 'profit': float(profit), 'details': details})


@sales_bp.route('/api/sales/<int:sale_id>/exchange', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_sales')
def create_exchange(sale_id):
    """Process an exchange: expects JSON with `returned_items` (or `items`) and `new_items` arrays."""
    data = request.get_json() or {}
    # Accept both 'returned_items' and 'items' for flexibility
    returned = data.get('returned_items') or data.get('items', [])
    new_items = data.get('new_items', [])

    if not returned and not new_items:
        return jsonify({'error': 'No items provided for exchange'}), 400

    try:
        original_sale = get_sale_secure(sale_id)
        if not original_sale:
            return jsonify({'error': 'Sale not found'}), 404
        company_id = get_company_id()

        # Create a return first
        return_record = Return(
            original_sale_id=sale_id,
            customer=original_sale.customer,
            return_reason=data.get('reason', 'Exchange'),
            refund_method='Store Credit',
            refund_amount=0.0,
            status='completed',
            user_id=current_user.id,
            company_id=company_id  # Set company_id
        )
        db.session.add(return_record)
        db.session.flush()

        total_refund = 0.0
        for r in returned:
            sale_item = SaleItem.query.get(r.get('sale_item_id'))
            qty = float(r.get('quantity', 0))
            if sale_item and qty > 0:
                ri = ReturnItem(
                    return_id=return_record.id,
                    product_id=sale_item.product_id,
                    quantity=qty,
                    price=sale_item.price,
                    reason=r.get('reason', 'Exchange'),
                    original_sale_item_id=sale_item.id,
                    company_id=company_id  # Set company_id
                )
                db.session.add(ri)
                product = Product.query.get(sale_item.product_id)
                if product:
                    product.stock += qty
                total_refund += qty * sale_item.price

        # Create new sale for items being exchanged (if any)
        new_sale = None
        if new_items:
            new_sale = Sale(
                customer=original_sale.customer,
                payment='Store Credit',
                cash_given=0.0,
                total=0.0,
                balance=0.0,
                user_id=current_user.id,
                company_id=company_id  # Set company_id
            )
            db.session.add(new_sale)
            db.session.flush()

            new_total = 0.0
            for ni in new_items:
                product = Product.query.get(ni.get('product_id'))
                qty = float(ni.get('quantity', 0))
                price = float(ni.get('price', 0))
                if product and qty > 0:
                    si = SaleItem(sale_id=new_sale.id, product_id=product.id, quantity=qty, price=price, company_id=company_id)
                    db.session.add(si)
                    product.stock -= qty
                    new_total += qty * price

            new_sale.total = new_total

        db.session.commit()

        return jsonify({'success': True, 'return_id': return_record.id, 'new_sale_id': new_sale.id if new_sale else None})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@sales_bp.route('/api/settings/tax-rate')
@csrf.exempt
@login_required
def get_tax_rate():
    """Get the configured tax rate from settings."""
    company_id = get_company_id()
    # Get tax rate - check both 'rate' (new) and 'gstRate' (legacy) for backward compatibility
    tax_rate_setting = Setting.query.filter_by(setting_category='tax', setting_key='rate')
    if company_id and hasattr(Setting, 'company_id'):
        tax_rate_setting = tax_rate_setting.filter(Setting.company_id == company_id)
    tax_rate_setting = tax_rate_setting.first()
    
    if not tax_rate_setting:
        tax_rate_setting = Setting.query.filter_by(setting_category='tax', setting_key='gstRate')
        if company_id and hasattr(Setting, 'company_id'):
            tax_rate_setting = tax_rate_setting.filter(Setting.company_id == company_id)
        tax_rate_setting = tax_rate_setting.first()
    
    tax_rate = float(tax_rate_setting.setting_value) if tax_rate_setting and tax_rate_setting.setting_value else 18.0
    
    # Get enable_tax setting (new - to explicitly enable/disable tax)
    enable_tax_setting = Setting.query.filter_by(setting_category='tax', setting_key='enable_tax')
    if company_id and hasattr(Setting, 'company_id'):
        enable_tax_setting = enable_tax_setting.filter(Setting.company_id == company_id)
    enable_tax_setting = enable_tax_setting.first()
    enable_tax = True  # Default to True for backward compatibility
    if enable_tax_setting and enable_tax_setting.setting_value:
        enable_tax = enable_tax_setting.setting_value.lower() == 'true'
    
    # Get show_tax_in_sales setting (for backward compatibility)
    show_tax_setting = Setting.query.filter_by(setting_category='tax', setting_key='show_tax_in_sales')
    if company_id and hasattr(Setting, 'company_id'):
        show_tax_setting = show_tax_setting.filter(Setting.company_id == company_id)
    show_tax_setting = show_tax_setting.first()
    show_tax_in_sales = True
    if show_tax_setting and show_tax_setting.setting_value:
        show_tax_in_sales = show_tax_setting.setting_value.lower() == 'true'
    
    # If enable_tax is False, show_tax_in_sales should also be False
    if not enable_tax:
        show_tax_in_sales = False
    
    return jsonify({
        'tax_rate': tax_rate,
        'show_tax_in_sales': show_tax_in_sales,
        'enable_tax': enable_tax
    })

@sales_bp.route('/api/sales/hold', methods=['POST'])
@login_required
@require_permission('can_access_sales')
def hold_sale():
    """Save current cart as a held bill."""
    data = request.get_json()
    company_id = get_company_id()

    if not data or 'cart' not in data:
        return jsonify({'error': 'Invalid hold bill data'}), 400

    try:
        # Create held bill record
        held_bill = HeldBill(
            bill_data=json.dumps(data),
            user_id=current_user.id,
            notes=data.get('notes', ''),
            company_id=company_id  # Set company_id
        )

        db.session.add(held_bill)
        db.session.commit()

        return jsonify({
            'success': True,
            'held_bill_id': held_bill.id,
            'message': f'Bill held successfully! Held Bill #{held_bill.id}'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@sales_bp.route('/api/sales/held')
@login_required
@require_company_context
@require_permission('can_access_sales')
def get_held_bills():
    """Get all held bills for the current user and company."""
    try:
        company_id = get_company_id()
        query = HeldBill.query.filter_by(user_id=current_user.id)
        
        # Filter by company if company is set
        if company_id and hasattr(HeldBill, 'company_id'):
            from sqlalchemy import or_
            query = query.filter(HeldBill.company_id == company_id)
        
        held_bills = query.order_by(desc(HeldBill.held_date)).all()

        result = []
        for bill in held_bills:
            try:
                bill_data = json.loads(bill.bill_data)
                result.append({
                    'id': bill.id,
                    'held_date': bill.held_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'notes': bill.notes,
                    'items_count': len(bill_data.get('cart', [])),
                    'total': float(bill_data.get('total', 0))
                })
            except (json.JSONDecodeError, KeyError):
                # Skip malformed held bills
                continue

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@sales_bp.route('/api/sales/held/<int:bill_id>', methods=['GET'])
@login_required
@require_company_context
@require_permission('can_access_sales')
def get_held_bill(bill_id):
    """Get a specific held bill."""
    held_bill = HeldBill.query.get(bill_id)
    if not held_bill:
        return jsonify({'error': 'Held bill not found'}), 404

    # Only allow users to see their own held bills (or admin/super admin)
    if held_bill.user_id != current_user.id and current_user.role not in ['admin', 'Admin', 'super admin', 'Super Admin']:
        return jsonify({'error': 'Access denied'}), 403

    bill_data = json.loads(held_bill.bill_data)

    return jsonify({
        'id': held_bill.id,
        'held_date': held_bill.held_date.strftime('%Y-%m-%d %H:%M:%S'),
        'notes': held_bill.notes or '',
        'cart': bill_data.get('cart', []),
        'customer': bill_data.get('customer'),
        'subtotal': float(bill_data.get('subtotal', 0)),
        'discount': float(bill_data.get('discount', 0)),
        'tax': float(bill_data.get('tax', 0)),
        'total': float(bill_data.get('total', 0))
    })

@sales_bp.route('/api/sales/held/<int:bill_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_sales')
def delete_held_bill(bill_id):
    """Delete a held bill."""
    held_bill = HeldBill.query.get(bill_id)
    if not held_bill:
        return jsonify({'error': 'Held bill not found'}), 404

    # Only allow users to delete their own held bills (or admin/super admin)
    if held_bill.user_id != current_user.id and current_user.role not in ['admin', 'Admin', 'super admin', 'Super Admin']:
        return jsonify({'error': 'Access denied'}), 403

    try:
        db.session.delete(held_bill)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Held bill #{bill_id} deleted successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@sales_bp.route('/api/sales/all')
@login_required
@require_company_context
@require_permission('can_view_sales_history')
def get_all_sales():
    """Get all sales with pagination and filtering."""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        search = request.args.get('search', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        query = Sale.query

        # Apply company filter if company is selected
        # Also include sales with NULL company_id for backward compatibility
        company_id = get_company_id()
        if company_id and hasattr(Sale, 'company_id'):
            # Show sales that either match the current company OR have NULL company_id (legacy sales)
            from sqlalchemy import or_
            query = query.filter(
                Sale.company_id == company_id
            )

        if search:
            query = query.filter(Sale.customer.ilike(f'%{search}%'))

        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Sale.date >= start)
            except ValueError:
                pass

        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                end = end.replace(hour=23, minute=59, second=59)
                query = query.filter(Sale.date <= end)
            except ValueError:
                pass

        # Order by date descending
        query = query.order_by(desc(Sale.date))

        sales = query.paginate(page=page, per_page=per_page)

        result = {
            'sales': [],
            'total': sales.total,
            'pages': sales.pages,
            'current_page': sales.page
        }

        for sale in sales.items:
            result['sales'].append({
                'id': sale.id,
                'date': sale.date.strftime('%Y-%m-%d %H:%M:%S'),
                'customer': sale.customer,
                'total': sale.total,
                'payment': sale.payment,
                'items_count': len(sale.items),
                'user': sale.user.username if sale.user else 'Unknown'
            })

        return jsonify(result)
    except Exception as e:
        print(f"Error in get_all_sales: {e}")
        return jsonify({'error': 'Failed to load sales', 'sales': [], 'total': 0, 'pages': 0, 'current_page': 1}), 200

@sales_bp.route('/api/sales/<int:sale_id>')
@login_required
@require_company_context
@require_permission('can_view_sales_history')
def get_sale(sale_id):
    """Get a specific sale with all details."""
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404

    sale_data = {
        'id': sale.id,
        'date': sale.date.strftime('%Y-%m-%d %H:%M:%S'),
        'customer': sale.customer,
        'total': sale.total,
        'payment': sale.payment,
        'cash_given': sale.cash_given,
        'balance': sale.balance,
        'user': sale.user.username if sale.user else 'Unknown',
        'items': []
    }

    for item in sale.items:
        sale_data['items'].append({
            'id': item.id,
            'product_id': item.product_id,
            'product_name': item.product.name,
            'quantity': item.quantity,
            'price': item.price,
            'discount': item.discount,
            'tax': item.tax,
            'total': item.quantity * item.price
        })

    return jsonify(sale_data)

@sales_bp.route('/sales/history')
@login_required
@require_company_context
@require_permission('can_view_sales_history')
def sales_history():
    """Sales history page."""
    return render_template('sales/sales_history.html')

# Return Routes

@sales_bp.route('/returns')
@login_required
@require_company_context
@require_permission('can_manage_returns')
def returns():
    """Main returns page."""
    return render_template('sales/returns.html')

@sales_bp.route('/api/sales/<int:sale_id>/items')
@login_required
@require_permission('can_manage_returns')
def get_sale_items_for_return(sale_id):
    """Get sale items that can be returned (for partial returns)."""
    sale = get_sale_secure(sale_id)
    if not sale:
        return jsonify({'error': 'Sale not found'}), 404
    
    # Get already returned items
    returned_items = {}
    for return_record in sale.returns:
        for item in return_record.items:
            if item.original_sale_item_id:
                if item.original_sale_item_id not in returned_items:
                    returned_items[item.original_sale_item_id] = 0
                returned_items[item.original_sale_item_id] += item.quantity
    
    items = []
    for item in sale.items:
        # Calculate how many can still be returned
        already_returned = returned_items.get(item.id, 0)
        remaining_qty = item.quantity - already_returned
        
        if remaining_qty > 0:
            items.append({
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': item.price,
                'discount': item.discount,
                'tax': item.tax,
                'total': item.quantity * item.price,
                'already_returned': already_returned,
                'remaining_qty': remaining_qty
            })
    
    return jsonify({
        'sale_id': sale.id,
        'sale_date': sale.date.strftime('%Y-%m-%d %H:%M:%S'),
        'customer': sale.customer,
        'total': sale.total,
        'payment': sale.payment,
        'items': items
    })

@sales_bp.route('/api/returns', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_manage_returns')
def create_return():
    """Process a return (full or partial)."""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Invalid return data'}), 400
    
    required_fields = ['sale_id', 'return_reason', 'refund_method', 'refund_amount', 'items']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    try:
        sale = get_sale_secure(data['sale_id'])
        if not sale:
            return jsonify({'error': 'Sale not found'}), 404
        
        # Check if this is a full return (all items)
        is_full_return = data.get('is_full_return', False)
        
        # Create return record - use calculated total_refund, not frontend value
        return_record = Return(
            original_sale_id=data['sale_id'],
            customer=sale.customer,
            return_reason=data['return_reason'],
            refund_method=data['refund_method'],
            refund_amount=0,  # Will be updated after calculation
            status='completed',
            notes=data.get('notes', ''),
            user_id=current_user.id,
            company_id=get_company_id()  # Set company_id
        )
        
        db.session.add(return_record)
        db.session.flush()
        
        total_refund = 0
        
        # Process each item being returned
        for item_data in data['items']:
            sale_item = SaleItem.query.get(item_data['sale_item_id'])
            if not sale_item:
                continue
            
            return_qty = float(item_data['quantity'])
            
            # Validate return quantity
            if return_qty > sale_item.quantity:
                return jsonify({'error': f'Return quantity exceeds purchased quantity for item {sale_item.product.name}'}), 400
            
            # Calculate refund for this item - include tax when tax is enabled
            # Get tax settings to determine if tax should be included in refund
            enable_tax_setting = Setting.query.filter_by(setting_category='tax', setting_key='enable_tax').first()
            enable_tax = True  # Default to True for backward compatibility
            if enable_tax_setting and enable_tax_setting.setting_value:
                enable_tax = enable_tax_setting.setting_value.lower() == 'true'
            
            # Calculate refund: (price - discount) * quantity
            # If tax is enabled, add tax back to refund (customer paid tax, so they should get it back)
            item_refund = return_qty * (sale_item.price - sale_item.discount)
            if enable_tax and sale_item.tax:
                item_refund += return_qty * sale_item.tax
            
            total_refund += item_refund
            
            # Create return item
            return_item = ReturnItem(
                return_id=return_record.id,
                product_id=sale_item.product_id,
                quantity=return_qty,
                price=sale_item.price,
                reason=item_data.get('reason', ''),
                original_sale_item_id=sale_item.id,
                company_id=get_company_id()  # Set company_id
            )
            db.session.add(return_item)
            
            # Restore stock
            product = Product.query.get(sale_item.product_id)
            if product:
                product.stock += return_qty
                
                # Create inventory transaction for stock restoration
                inventory_tx = InventoryTransaction(
                    product_id=product.id,
                    transaction_type='return',
                    quantity=return_qty,
                    previous_stock=product.stock - return_qty,
                    new_stock=product.stock,
                    reference_id=return_record.id,
                    notes=f'Returned from Sale #{sale.id}',
                    company_id=get_company_id()  # Set company_id
                )
                db.session.add(inventory_tx)
        
        # Update customer's loyalty points if applicable (deduct points for returns)
        if sale.customer and sale.customer != 'Walk-in Customer':
            customer = Customer.query.filter_by(name=sale.customer).first()
            if customer:
                # Deduct points (1 point per Rs 10 refunded)
                points_deducted = int(total_refund // 10)
                customer.loyalty_points = max(0, customer.loyalty_points - points_deducted)
                customer.total_purchases = max(0, customer.total_purchases - total_refund)
        
        # Update the return record with the calculated refund amount
        return_record.refund_amount = total_refund
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'return_id': return_record.id,
            'message': f'Return processed successfully! Return #{return_record.id}'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@sales_bp.route('/api/returns')
@login_required
@require_permission('can_manage_returns')
def get_all_returns():
    """Get all returns with pagination and filtering."""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        search = request.args.get('search', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        
        query = Return.query
        
        # Apply company filter if company is selected
        company_id = get_company_id()
        if company_id and hasattr(Return, 'company_id'):
            from sqlalchemy import or_
            query = query.filter(Return.company_id == company_id)
        
        if search:
            query = query.filter(Return.customer.ilike(f'%{search}%'))
        
        if start_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Return.date >= start)
            except ValueError:
                pass
        
        if end_date:
            try:
                end = datetime.strptime(end_date, '%Y-%m-%d')
                end = end.replace(hour=23, minute=59, second=59)
                query = query.filter(Return.date <= end)
            except ValueError:
                pass
        
        # Order by date descending
        query = query.order_by(desc(Return.date))
        
        returns = query.paginate(page=page, per_page=per_page)
        
        result = {
            'returns': [],
            'total': returns.total,
            'pages': returns.pages,
            'current_page': returns.page
        }
        
        for return_record in returns.items:
            result['returns'].append({
                'id': return_record.id,
                'date': return_record.date.strftime('%Y-%m-%d %H:%M:%S'),
                'customer': return_record.customer,
                'original_sale_id': return_record.original_sale_id,
                'return_reason': return_record.return_reason,
                'refund_method': return_record.refund_method,
                'refund_amount': return_record.refund_amount,
                'status': return_record.status,
                'user': return_record.user.username if return_record.user else 'Unknown',
                'items_count': len(return_record.items)
            })
        
        return jsonify(result)
    except Exception as e:
        print(f"Error in get_all_returns: {e}")
        return jsonify({'error': 'Failed to load returns', 'returns': [], 'total': 0, 'pages': 0, 'current_page': 1}), 200

@sales_bp.route('/api/returns/<int:return_id>')
@login_required
@require_permission('can_manage_returns')
def get_return(return_id):
    """Get a specific return with all details."""
    try:
        return_record = Return.query.get(return_id)
        
        if not return_record:
            return jsonify({'error': 'Return not found'}), 404
        
        return_data = {
            'id': return_record.id,
            'date': return_record.date.strftime('%Y-%m-%d %H:%M:%S'),
            'customer': return_record.customer,
            'original_sale_id': return_record.original_sale_id,
            'return_reason': return_record.return_reason,
            'refund_method': return_record.refund_method,
            'refund_amount': return_record.refund_amount,
            'status': return_record.status,
            'notes': return_record.notes,
            'user': return_record.user.username if return_record.user else 'Unknown',
            'items': []
        }
        
        for item in return_record.items:
            return_data['items'].append({
                'id': item.id,
                'product_id': item.product_id,
                'product_name': item.product.name if item.product else 'Unknown',
                'quantity': item.quantity,
                'price': item.price,
                'total': item.quantity * item.price,
                'reason': item.reason
            })
        
        return jsonify(return_data)
    except Exception as e:
        current_app.logger.error(f"Error getting return: {e}")
        return jsonify({'error': 'Failed to load return details'}), 500
