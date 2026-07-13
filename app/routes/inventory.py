import os
import uuid
import io
import pandas as pd
from flask import Blueprint, render_template, request, jsonify, flash, send_file
from flask_login import login_required
from flask_wtf.csrf import CSRFProtect
from app.models import db, Product, InventoryTransaction, Warehouse
from app.utils.security import get_company_id, require_company_context
from app.utils.permissions import require_permission
from app.utils.audit import log_create, log_update, log_delete, log_audit
from app import csrf
from sqlalchemy import or_
from datetime import datetime

inventory_bp = Blueprint('inventory', __name__, template_folder='../../templates')

@inventory_bp.route('/inventory')
@login_required
@require_company_context
@require_permission('can_view_inventory')
def inventory():
    """Main inventory page."""
    return render_template('inventory/inventory.html')

@inventory_bp.route('/warehouse')
@login_required
@require_company_context
@require_permission('can_access_warehouse')
def warehouse():
    """Warehouse inventory management page (stock in warehouses)."""
    return render_template('inventory/warehouse.html')

@inventory_bp.route('/warehouses')
@login_required
@require_company_context
@require_permission('can_access_warehouse')
def warehouses():
    """Warehouse management page (manage warehouses themselves)."""
    return render_template('inventory/warehouses.html')

@inventory_bp.route('/api/products')
@csrf.exempt
@login_required
@require_company_context
@require_permission('can_view_inventory')
def get_products():
    """API endpoint to get products with pagination and filtering."""
    company_id = get_company_id()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    low_stock = request.args.get('low_stock', 'false').lower() == 'true'
    warehouse_id = request.args.get('warehouse_id', '').strip()

    query = Product.query.filter(
        Product.company_id == company_id
    )

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.barcode.ilike(f'%{search}%')
            )
        )

    if category:
        query = query.filter(Product.category == category)

    if low_stock:
        query = query.filter(Product.stock <= Product.low_stock_threshold)

    # Filter by warehouse_id if provided
    if warehouse_id:
        try:
            query = query.filter(Product.warehouse_id == int(warehouse_id))
        except ValueError:
            pass  # Invalid warehouse_id, ignore the filter

    products = query.paginate(page=page, per_page=per_page)

    result = {
        'products': [],
        'total': products.total,
        'pages': products.pages,
        'current_page': products.page
    }

    for product in products.items:
        result['products'].append({
            'id': product.id,
            'name': product.name,
            'price': float(product.price) if product.price else 0,
            'cost_price': float(product.cost_price) if product.cost_price else 0,
            'stock': float(product.stock) if product.stock else 0,
            'unit_type': product.unit_type or '',
            'category': product.category or '',
            'low_stock_threshold': float(product.low_stock_threshold) if product.low_stock_threshold else 0,
            'barcode': product.barcode or '',
            'description': product.description or '',
            'image_path': product.image_path or '',
            'warehouse_id': product.warehouse_id,
            'supplier_id': product.supplier_id,
            'last_updated': product.last_updated.strftime('%Y-%m-%d %H:%M:%S') if product.last_updated else None
        })

    return jsonify(result)

@inventory_bp.route('/api/products/<int:product_id>', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_view_inventory')
def get_product(product_id):
    """Get single product details."""
    company_id = get_company_id()
    product = Product.query.filter(
        Product.id == product_id,
        Product.company_id == company_id
    ).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    return jsonify({
        'id': product.id,
        'name': product.name,
        'price': float(product.price) if product.price else 0,
        'cost_price': float(product.cost_price) if product.cost_price else 0,
        'stock': float(product.stock) if product.stock else 0,
        'unit_type': product.unit_type or '',
        'category': product.category or '',
        'low_stock_threshold': float(product.low_stock_threshold) if product.low_stock_threshold else 0,
        'barcode': product.barcode or '',
        'description': product.description or '',
        'image_path': product.image_path or '',
        'warehouse_id': product.warehouse_id,
        'last_updated': product.last_updated.strftime('%Y-%m-%d %H:%M:%S') if product.last_updated else None,
        'supplier_id': product.supplier_id,
        'supplier_name': product.supplier.name if product.supplier else '-',
        'supplier_phone': product.supplier.phone if product.supplier else '-',
        'supplier_email': product.supplier.email if product.supplier else '-'
    })

@inventory_bp.route('/api/products', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_edit_inventory')
def create_product():
    """Create a new product."""
    data = request.get_json()
    company_id = get_company_id()

    if not data or 'name' not in data or 'price' not in data:
        return jsonify({'error': 'Product name and price are required'}), 400

    try:
        product = Product(
            name=data['name'],
            price=float(data['price']),
            cost_price=float(data.get('cost_price', 0.0)),
            stock=float(data.get('stock', 0.0)),
            unit_type=data.get('unit_type', 'unit'),
            category=data.get('category', 'General'),
            low_stock_threshold=float(data.get('low_stock_threshold', 5.0)),
            barcode=data.get('barcode'),
            description=data.get('description'),
            image_path=data.get('image_path'),
            warehouse_id=data.get('warehouse_id'),
            supplier_id=data.get('supplier_id'),
            company_id=company_id
        )

        db.session.add(product)
        db.session.commit()
        
        # Log audit
        log_create('Product', product.id, {
            'name': product.name,
            'price': product.price,
            'cost_price': product.cost_price,
            'stock': product.stock,
            'category': product.category
        }, description=f"Product '{product.name}' created with price ₨{product.price}")

        return jsonify({
            'success': True,
            'product_id': product.id,
            'message': 'Product created successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/api/products/<int:product_id>', methods=['PUT'])
@csrf.exempt
@login_required
@require_permission('can_edit_inventory')
def update_product(product_id):
    """Update an existing product."""
    company_id = get_company_id()
    product = Product.query.filter(
        Product.id == product_id,
        Product.company_id == company_id
    ).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        # Store old values for audit
        old_values = {
            'name': product.name,
            'price': product.price,
            'cost_price': product.cost_price,
            'stock': product.stock,
            'category': product.category
        }
        
        # Track stock change for inventory transaction
        old_stock = product.stock

        # Update product fields
        for field in ['name', 'price', 'cost_price', 'stock', 'unit_type', 'category',
                     'low_stock_threshold', 'barcode', 'description', 'image_path', 'warehouse_id', 'supplier_id']:
            if field in data:
                if field in ['price', 'cost_price', 'stock', 'low_stock_threshold']:
                    setattr(product, field, float(data[field]))
                else:
                    setattr(product, field, data[field])

        product.last_updated = datetime.utcnow()

        # Log inventory transaction if stock changed
        if 'stock' in data and float(data['stock']) != old_stock:
            transaction = InventoryTransaction(
                product_id=product.id,
                transaction_type='adjustment',
                quantity=float(data['stock']),
                previous_stock=old_stock,
                new_stock=float(data['stock']),
                notes='Manual stock adjustment via web interface',
                company_id=company_id
            )
            db.session.add(transaction)

        db.session.commit()
        
        # Store new values for audit
        new_values = {
            'name': product.name,
            'price': product.price,
            'cost_price': product.cost_price,
            'stock': product.stock,
            'category': product.category
        }
        
        # Log audit
        log_update('Product', product.id, old_values, new_values,
                   description=f"Product '{product.name}' updated")

        return jsonify({
            'success': True,
            'message': 'Product updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/api/products/<int:product_id>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_permission('can_edit_inventory')
def delete_product(product_id):
    """Delete a product."""
    company_id = get_company_id()
    product = Product.query.filter(
        Product.id == product_id,
        Product.company_id == company_id
    ).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    try:
        # Check if product has related records in other tables
        from app.models import SaleItem, InventoryTransaction, PurchaseItem, ReturnItem, ExchangeItem, SerialNumber
        
        related_counts = {
            'sales': SaleItem.query.filter_by(product_id=product_id).filter(SaleItem.company_id == company_id).count(),
            'transactions': InventoryTransaction.query.filter_by(product_id=product_id).filter(InventoryTransaction.company_id == company_id).count(),
            'purchases': PurchaseItem.query.filter_by(product_id=product_id).filter(PurchaseItem.company_id == company_id).count(),
            'returns': ReturnItem.query.filter_by(product_id=product_id).filter(ReturnItem.company_id == company_id).count(),
            'exchanges': ExchangeItem.query.filter_by(product_id=product_id).filter(ExchangeItem.company_id == company_id).count(),
            'serial_numbers': SerialNumber.query.filter_by(product_id=product_id).filter(SerialNumber.company_id == company_id).count()
        }
        
        total_related = sum(related_counts.values())
        
        if total_related > 0:
            # Product has related records - set stock to 0 instead of deleting
            product.stock = 0
            product.last_updated = datetime.utcnow()
            db.session.commit()
            
            # Log audit
            log_audit('Product', product_id, 'deactivate',
                      description=f"Product '{product.name}' deactivated (stock set to 0)")
            
            return jsonify({
                'success': True,
                'message': f'Product has {total_related} related records (sales, purchases, etc.) so it cannot be fully deleted. Stock has been set to 0.',
                'stock_set_to_zero': True
            })
        else:
            # No related records, safe to delete
            product_name = product.name
            db.session.delete(product)
            db.session.commit()
            
            # Log audit
            log_delete('Product', product_id, {'name': product_name},
                       description=f"Product '{product_name}' deleted")
            
            return jsonify({
                'success': True,
                'message': 'Product deleted successfully'
            })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/api/inventory/transactions')
@csrf.exempt
@login_required
@require_permission('can_view_inventory')
def get_inventory_transactions():
    """Get inventory transaction history."""
    company_id = get_company_id()
    product_id = request.args.get('product_id')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))

    query = InventoryTransaction.query.filter(
        InventoryTransaction.company_id == company_id
    )

    if product_id:
        query = query.filter_by(product_id=int(product_id))

    query = query.order_by(InventoryTransaction.date.desc())

    transactions = query.paginate(page=page, per_page=per_page)

    result = {
        'transactions': [],
        'total': transactions.total,
        'pages': transactions.pages,
        'current_page': transactions.page
    }

    for transaction in transactions.items:
        result['transactions'].append({
            'id': transaction.id,
            'product_id': transaction.product_id,
            'product_name': transaction.product.name,
            'transaction_type': transaction.transaction_type,
            'quantity': float(transaction.quantity) if transaction.quantity else 0,
            'previous_stock': float(transaction.previous_stock) if transaction.previous_stock else 0,
            'new_stock': float(transaction.new_stock) if transaction.new_stock else 0,
            'reference_id': transaction.reference_id or '',
            'date': transaction.date.strftime('%Y-%m-%d %H:%M:%S'),
            'notes': transaction.notes or ''
        })

    return jsonify(result)

@inventory_bp.route('/api/inventory/low-stock')
@csrf.exempt
@login_required
@require_permission('can_view_inventory')
def get_low_stock_products():
    """Get products that are below their low stock threshold."""
    company_id = get_company_id()
    products = Product.query.filter(
        Product.stock <= Product.low_stock_threshold,
        Product.company_id == company_id
    ).all()

    result = []
    for product in products:
        result.append({
            'id': product.id,
            'name': product.name,
            'stock': float(product.stock) if product.stock else 0,
            'low_stock_threshold': float(product.low_stock_threshold) if product.low_stock_threshold else 0,
            'unit_type': product.unit_type or ''
        })

    return jsonify(result)

@inventory_bp.route('/api/products/upload', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_edit_inventory')
def upload_product_image():
    """Upload product image."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Allowed extensions
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    
    if ext not in allowed_extensions:
        return jsonify({'error': 'File type not allowed. Allowed: png, jpg, jpeg, gif, webp'}), 400
    
    # Generate unique filename
    filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Create uploads directory if it doesn't exist
    upload_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'uploads', 'products')
    os.makedirs(upload_folder, exist_ok=True)
    
    # Save file
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    # Return the URL path
    image_url = f"/uploads/products/{filename}"
    
    return jsonify({
        'success': True,
        'image_path': image_url,
        'message': 'Image uploaded successfully'
    })

@inventory_bp.route('/api/products/export')
@csrf.exempt
@login_required
@require_permission('can_view_inventory')
def export_products():
    """Export all products to Excel file."""
    try:
        # Get all products without pagination (company-filtered)
        company_id = get_company_id()
        products_query = Product.query
        if company_id and hasattr(Product, 'company_id'):
            from sqlalchemy import or_
            products_query = products_query.filter(Product.company_id == company_id)
        products = products_query.all()
        
        if not products:
            return jsonify({'error': 'No products to export'}), 400
        
        # Prepare data for export
        data = []
        for product in products:
            data.append({
                'Name': product.name,
                'Price': product.price,
                'Cost Price': product.cost_price or 0.0,
                'Stock': product.stock,
                'Unit Type': product.unit_type or 'unit',
                'Category': product.category or 'General',
                'Low Stock Threshold': product.low_stock_threshold or 5.0,
                'Barcode': product.barcode or '',
                'Description': product.description or ''
            })
        
        # Create DataFrame and export to Excel
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        
        # Generate filename with timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'inventory_products_{timestamp}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        import traceback
        from flask import current_app
        current_app.logger.error(f"Import error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@inventory_bp.route('/api/products/import', methods=['POST', 'OPTIONS'])
@csrf.exempt
@login_required
@require_permission('can_edit_inventory')
def import_products():
    """Import products from Excel file."""
    # Handle OPTIONS requests (browser preflight)
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get import mode: 'replace' (default) or 'add'
        import_mode = request.form.get('import_mode', 'replace')
        
        # Check file extension
        allowed_extensions = {'xlsx', 'xls'}
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        
        if ext not in allowed_extensions:
            return jsonify({'error': 'File type not allowed. Allowed: xlsx, xls'}), 400
        
        # Read the Excel file
        df = pd.read_excel(file, engine='openpyxl')
        
        # Required columns
        required_columns = ['Name', 'Price']
        
        # Check for required columns
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return jsonify({'error': f'Missing required columns: {", ".join(missing_columns)}'}), 400
        
        # Validate data
        if df.empty:
            return jsonify({'error': 'The file is empty'}), 400
        
        # Import products
        imported_count = 0
        updated_count = 0
        stock_added_count = 0
        error_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Validate required fields
                if pd.isna(row.get('Name')) or pd.isna(row.get('Price')):
                    error_count += 1
                    errors.append(f'Row {index + 2}: Name and Price are required')
                    continue
                
                product_name = str(row['Name']).strip()
                product_barcode = str(row['Barcode']).strip() if not pd.isna(row.get('Barcode')) else None
                
                # Check if product already exists by name or barcode (scoped to company)
                company_id = get_company_id()
                existing_product = None
                if product_barcode:
                    # Try to find by barcode first
                    existing_product = Product.query.filter(
                        Product.barcode == product_barcode,
                        Product.company_id == company_id
                    ).first()
                
                if not existing_product:
                    # Try to find by name
                    existing_product = Product.query.filter(
                        Product.name == product_name,
                        Product.company_id == company_id
                    ).first()
                
                if existing_product:
                    # Update existing product
                    old_stock = existing_product.stock
                    existing_product.price = float(row['Price']) if not pd.isna(row['Price']) else 0.0
                    existing_product.cost_price = float(row['Cost Price']) if not pd.isna(row.get('Cost Price')) else 0.0
                    
                    # Handle stock based on import mode
                    import_stock = float(row['Stock']) if not pd.isna(row.get('Stock')) else 0.0
                    if import_mode == 'add':
                        # ADD stock to existing stock
                        existing_product.stock = old_stock + import_stock
                        if import_stock > 0:
                            # Log inventory transaction for stock addition
                            transaction = InventoryTransaction(
                                product_id=existing_product.id,
                                transaction_type='purchase',
                                quantity=import_stock,
                                previous_stock=old_stock,
                                new_stock=existing_product.stock,
                                company_id=get_company_id(),
                                notes=f'Bulk import: Added {import_stock} units via Excel import'
                            )
                            db.session.add(transaction)
                            stock_added_count += 1
                    else:
                        # REPLACE stock (default behavior)
                        existing_product.stock = import_stock
                    
                    existing_product.unit_type = str(row['Unit Type']).strip() if not pd.isna(row.get('Unit Type')) else 'unit'
                    existing_product.category = str(row['Category']).strip() if not pd.isna(row.get('Category')) else 'General'
                    existing_product.low_stock_threshold = float(row['Low Stock Threshold']) if not pd.isna(row.get('Low Stock Threshold')) else 5.0
                    if product_barcode:
                        existing_product.barcode = product_barcode
                    existing_product.description = str(row['Description']).strip() if not pd.isna(row.get('Description')) else None
                    existing_product.last_updated = datetime.utcnow()
                    updated_count += 1
                else:
                    # Create new product
                    company_id = get_company_id()
                    product = Product(
                        name=product_name,
                        company_id=company_id,
                        price=float(row['Price']) if not pd.isna(row['Price']) else 0.0,
                        cost_price=float(row['Cost Price']) if not pd.isna(row.get('Cost Price')) else 0.0,
                        stock=float(row['Stock']) if not pd.isna(row.get('Stock')) else 0.0,
                        unit_type=str(row['Unit Type']).strip() if not pd.isna(row.get('Unit Type')) else 'unit',
                        category=str(row['Category']).strip() if not pd.isna(row.get('Category')) else 'General',
                        low_stock_threshold=float(row['Low Stock Threshold']) if not pd.isna(row.get('Low Stock Threshold')) else 5.0,
                        barcode=product_barcode,
                        description=str(row['Description']).strip() if not pd.isna(row.get('Description')) else None
                    )
                    db.session.add(product)
                    imported_count += 1
                
            except Exception as e:
                error_count += 1
                errors.append(f'Row {index + 2}: {str(e)}')
        
        # Commit all changes
        db.session.commit()
        
        # Build response message based on import mode
        if import_mode == 'add':
            message = f'Import completed: {imported_count} new products added, {updated_count} products updated, {stock_added_count} stock additions, {error_count} errors'
        else:
            message = f'Import completed: {imported_count} new products added, {updated_count} products updated, {error_count} errors'
        
        return jsonify({
            'success': True,
            'message': message,
            'imported_count': imported_count,
            'updated_count': updated_count,
            'stock_added_count': stock_added_count,
            'error_count': error_count,
            'import_mode': import_mode,
            'errors': errors[:10] if errors else []
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        from flask import current_app
        error_msg = f"Products import error: {str(e)}\n{traceback.format_exc()}"
        current_app.logger.error(error_msg)
        return jsonify({'error': str(e)}), 500
