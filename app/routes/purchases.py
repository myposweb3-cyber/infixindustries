from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.utils.permissions import require_permission
from app.utils.security import get_company_id, require_company_context
from app.models import db, Purchase, Supplier, PurchaseReturn, Product, PurchaseItem, InventoryTransaction, PurchaseReturnItem
from sqlalchemy import desc, or_
from datetime import datetime
import json

purchases_bp = Blueprint('purchases', __name__, template_folder='../../templates')

@purchases_bp.route('/purchases')
@login_required
@require_company_context
@require_permission('can_access_purchases')
def purchases():
    """Main purchases page with filtering."""
    # Get filter parameters
    supplier_filter = request.args.get('supplier')
    status_filter = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Build query
    query = Purchase.query.join(Supplier)
    
    # Apply company filter
    company_id = get_company_id()
    if company_id and hasattr(Purchase, 'company_id'):
        query = query.filter(Purchase.company_id == company_id)

    if supplier_filter:
        query = query.filter(Purchase.supplier_id == supplier_filter)
    
    if status_filter:
        query = query.filter(Purchase.status == status_filter)

    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Purchase.date >= start)
        except ValueError:
            pass

    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end.replace(hour=23, minute=59, second=59)
            query = query.filter(Purchase.date <= end)
        except ValueError:
            pass

    # Get all purchases ordered by date descending
    purchases_list = query.order_by(desc(Purchase.date)).all()

    # Get all suppliers for the filter dropdown
    suppliers_query = Supplier.query
    if company_id and hasattr(Supplier, 'company_id'):
        suppliers_query = suppliers_query.filter(Supplier.company_id == company_id)
    suppliers = suppliers_query.order_by(Supplier.name).all()

    # Get products for the "New Purchase" modal form
    products_query = Product.query
    if company_id and hasattr(Product, 'company_id'):
        products_query = products_query.filter(Product.company_id == company_id)
    products = products_query.order_by(Product.name).all()

    # Calculate totals
    total_amount = sum(p.total_amount for p in purchases_list if p.total_amount)
    total_paid = sum(p.amount_paid for p in purchases_list if p.amount_paid)
    total_balance = total_amount - total_paid

    return render_template(
        'purchases/purchases.html',
        purchases=purchases_list,
        suppliers=suppliers,
        products=products,
        now=datetime.now(),
        total_amount=total_amount,
        total_paid=total_paid,
        total_balance=total_balance,
        supplier_filter=supplier_filter,
        status_filter=status_filter,
        start_date=start_date,
        end_date=end_date
    )

@purchases_bp.route('/purchases/returns')
@login_required
@require_permission('can_manage_purchase_returns')
def purchase_returns():
    """Purchase returns page with filtering."""
    # For a full implementation, you would add filtering similar to the purchases() function
    query = PurchaseReturn.query
    
    # Apply company filter
    company_id = get_company_id()
    if company_id and hasattr(PurchaseReturn, 'company_id'):
        query = query.filter(PurchaseReturn.company_id == company_id)
    
    purchase_returns_list = query.order_by(desc(PurchaseReturn.date)).all()

    # Get data for the "New Purchase Return" modal
    suppliers_query = Supplier.query
    if company_id and hasattr(Supplier, 'company_id'):
        suppliers_query = suppliers_query.filter(Supplier.company_id == company_id)
    suppliers = suppliers_query.order_by(Supplier.name).all()
    
    purchases_query = Purchase.query
    if company_id and hasattr(Purchase, 'company_id'):
        purchases_query = purchases_query.filter(Purchase.company_id == company_id)
    purchases = purchases_query.order_by(desc(Purchase.date)).limit(100).all()

    total_refunds = sum(pr.refund_amount for pr in purchase_returns_list if pr.refund_amount)

    return render_template(
        'purchases/returns.html',
        purchase_returns=purchase_returns_list,
        suppliers=suppliers,
        purchases=purchases,
        now=datetime.now(),
        total_refunds=total_refunds
    )

@purchases_bp.route('/purchases/new', methods=['GET', 'POST'])
@login_required
@require_permission('can_access_purchases')
def new_purchase():
    """Form to create a new purchase."""
    if request.method == 'POST':
        data = request.form
        items_json = data.get('items_json')
        
        if not items_json:
            flash('No items added to the purchase.', 'danger')
            return redirect(url_for('purchases.purchases', open_modal='new_purchase'))

        try:
            items = json.loads(items_json)
            if not items:
                flash('No items added to the purchase.', 'danger')
                return redirect(url_for('purchases.purchases', open_modal='new_purchase'))

            # Create Purchase
            purchase = Purchase(
                supplier_id=data.get('supplier_id'),
                invoice_number=data.get('invoice_number'),
                date=datetime.strptime(data.get('date'), '%Y-%m-%d'),
                total_amount=float(data.get('total_amount')),
                amount_paid=float(data.get('amount_paid', 0.0)),
                status=data.get('status'),
                company_id=get_company_id()  # Set company_id
            )
            db.session.add(purchase)
            db.session.flush() # to get purchase.id

            # Create PurchaseItems and update stock
            company_id = get_company_id()
            for item in items:
                product_query = Product.query.filter_by(id=item['product_id'])
                if company_id and hasattr(Product, 'company_id'):
                    product_query = product_query.filter(Product.company_id == company_id)
                product = product_query.first()
                if not product:
                    raise Exception(f"Product with ID {item['product_id']} not found.")

                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=item['product_id'],
                    quantity=float(item['quantity']),
                    cost_price=float(item['cost_price']),
                    total_cost=float(item['quantity']) * float(item['cost_price']),
                    company_id=company_id  # Set company_id for multi-company support
                )
                db.session.add(purchase_item)

                # Update product stock and cost price
                previous_stock = product.stock
                product.stock += float(item['quantity'])
                product.cost_price = float(item['cost_price']) # Update with latest cost
                product.supplier_id = purchase.supplier_id  # Link product to supplier
                
                # Log inventory transaction
                inv_trans = InventoryTransaction(
                    product_id=product.id,
                    transaction_type='purchase',
                    quantity=float(item['quantity']),
                    previous_stock=previous_stock,
                    new_stock=product.stock,
                    reference_id=purchase.id,
                    company_id=get_company_id()  # Set company_id
                )
                db.session.add(inv_trans)

            db.session.commit()
            flash(f'Purchase #{purchase.id} created successfully!', 'success')
            return redirect(url_for('purchases.purchases'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating purchase: {str(e)}', 'danger')
            return redirect(url_for('purchases.purchases', open_modal='new_purchase'))

    # GET request
    company_id = get_company_id()
    suppliers_query = Supplier.query
    if company_id and hasattr(Supplier, 'company_id'):
        suppliers_query = suppliers_query.filter(Supplier.company_id == company_id)
    suppliers = suppliers_query.order_by(Supplier.name).all()
    
    products_query = Product.query
    if company_id and hasattr(Product, 'company_id'):
        products_query = products_query.filter(Product.company_id == company_id)
    products = products_query.order_by(Product.name).all()
    return render_template('purchases/new_purchase.html', suppliers=suppliers, products=products, now=datetime.now())


@purchases_bp.route('/purchases/returns/new', methods=['GET', 'POST'])
@login_required
@require_permission('can_manage_purchase_returns')
def new_purchase_return():
    """Form to create a new purchase return."""
    if request.method == 'POST':
        data = request.form
        items_json = data.get('items_json')
        
        if not items_json:
            flash('No items selected for return.', 'danger')
            return redirect(url_for('purchases.purchase_returns', open_modal='new_purchase_return'))

        try:
            items = json.loads(items_json)
            if not items:
                flash('No items selected for return.', 'danger')
                return redirect(url_for('purchases.purchase_returns', open_modal='new_purchase_return'))

            company_id = get_company_id()
            original_purchase_query = Purchase.query.filter_by(id=data.get('original_purchase_id'))
            if company_id and hasattr(Purchase, 'company_id'):
                original_purchase_query = original_purchase_query.filter(Purchase.company_id == company_id)
            original_purchase = original_purchase_query.first()
            if not original_purchase:
                 flash('Original purchase not found.', 'danger')
                 return redirect(url_for('purchases.purchase_returns', open_modal='new_purchase_return'))

            # Create PurchaseReturn
            purchase_return = PurchaseReturn(
                original_purchase_id=original_purchase.id,
                supplier_id=original_purchase.supplier_id,
                date=datetime.strptime(data.get('date'), '%Y-%m-%d'),
                return_reason=data.get('return_reason'),
                refund_amount=float(data.get('total_refund_amount')),
                notes=data.get('notes'),
                user_id=current_user.id,
                company_id=get_company_id()  # Set company_id
            )
            db.session.add(purchase_return)
            db.session.flush() # to get purchase_return.id

            # Create PurchaseReturnItems and update stock
            for item in items:
                product_query = Product.query.filter_by(id=item['product_id'])
                if company_id and hasattr(Product, 'company_id'):
                    product_query = product_query.filter(Product.company_id == company_id)
                product = product_query.first()
                if not product:
                    raise Exception(f"Product with ID {item['product_id']} not found.")

                return_item = PurchaseReturnItem(
                    purchase_return_id=purchase_return.id,
                    product_id=item['product_id'],
                    quantity=float(item['quantity']),
                    unit_cost=float(item['unit_cost']),
                    total_cost=float(item['quantity']) * float(item['unit_cost']),
                    company_id=get_company_id()  # Set company_id
                )
                db.session.add(return_item)

                # Update product stock
                previous_stock = product.stock
                product.stock -= float(item['quantity'])
                
                inv_trans = InventoryTransaction(
                    product_id=product.id, transaction_type='purchase_return',
                    quantity=float(item['quantity']), previous_stock=previous_stock,
                    new_stock=product.stock, reference_id=purchase_return.id,
                    company_id=get_company_id()  # Set company_id
                )
                db.session.add(inv_trans)

            db.session.commit()
            flash(f'Purchase Return #{purchase_return.id} created successfully!', 'success')
            return redirect(url_for('purchases.purchase_returns'))

        except Exception as e:
            db.session.rollback()
            flash(f'Error creating purchase return: {str(e)}', 'danger')
            return redirect(url_for('purchases.purchase_returns', open_modal='new_purchase_return'))

    # GET request
    company_id = get_company_id()
    suppliers_query = Supplier.query
    if company_id and hasattr(Supplier, 'company_id'):
        suppliers_query = suppliers_query.filter(Supplier.company_id == company_id)
    suppliers = suppliers_query.order_by(Supplier.name).all()
    
    purchases_query = Purchase.query
    if company_id and hasattr(Purchase, 'company_id'):
        purchases_query = purchases_query.filter(Purchase.company_id == company_id)
    purchases = purchases_query.order_by(desc(Purchase.date)).limit(100).all()
    return render_template('purchases/new_purchase_return.html', suppliers=suppliers, purchases=purchases, now=datetime.now())

@purchases_bp.route('/api/purchases/<int:purchase_id>/items')
@login_required
@require_permission('can_access_purchases')
def get_purchase_items(purchase_id):
    """API to get items for a specific purchase, for the return form."""
    company_id = get_company_id()
    purchase_query = Purchase.query.filter_by(id=purchase_id)
    if company_id and hasattr(Purchase, 'company_id'):
        purchase_query = purchase_query.filter(Purchase.company_id == company_id)
    purchase = purchase_query.first()
    if not purchase:
        return jsonify({'error': 'Purchase not found'}), 404
    items = []
    for item in purchase.items:
        items.append({
            'product_id': item.product_id,
            'product_name': item.product.name,
            'quantity_purchased': float(item.quantity) if item.quantity else 0,
            'cost_price': float(item.cost_price) if item.cost_price else 0
        })
    return jsonify({'supplier_id': purchase.supplier_id, 'items': items})

@purchases_bp.route('/api/purchases/<int:purchase_id>')
@login_required
@require_permission('can_access_purchases')
def get_purchase(purchase_id):
    """API to get details of a specific purchase."""
    company_id = get_company_id()
    purchase_query = Purchase.query.filter_by(id=purchase_id)
    if company_id and hasattr(Purchase, 'company_id'):
        purchase_query = purchase_query.filter(Purchase.company_id == company_id)
    purchase = purchase_query.first()
    if not purchase:
        return jsonify({'error': 'Purchase not found'}), 404
    
    items = []
    for item in purchase.items:
        items.append({
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else 'Unknown Product',
            'quantity': float(item.quantity) if item.quantity else 0,
            'cost_price': float(item.cost_price) if item.cost_price else 0,
            'total_cost': float(item.total_cost) if item.total_cost else 0
        })
    
    return jsonify({
        'id': purchase.id,
        'date': purchase.date.strftime('%Y-%m-%d') if purchase.date else None,
        'invoice_number': purchase.invoice_number or '',
        'supplier_id': purchase.supplier_id,
        'supplier_name': purchase.supplier.name if purchase.supplier else 'Unknown',
        'total_amount': float(purchase.total_amount) if purchase.total_amount else 0,
        'amount_paid': float(purchase.amount_paid) if purchase.amount_paid else 0,
        'status': purchase.status or '',
        'items': items
    })

@purchases_bp.route('/api/purchase-returns/<int:return_id>')
@login_required
@require_permission('can_manage_purchase_returns')
def get_purchase_return(return_id):
    """API to get details of a specific purchase return."""
    company_id = get_company_id()
    purchase_return_query = PurchaseReturn.query.filter_by(id=return_id)
    if company_id and hasattr(PurchaseReturn, 'company_id'):
        purchase_return_query = purchase_return_query.filter(PurchaseReturn.company_id == company_id)
    purchase_return = purchase_return_query.first()
    if not purchase_return:
        return jsonify({'error': 'Purchase return not found'}), 404
    
    items = []
    for item in purchase_return.items:
        items.append({
            'product_id': item.product_id,
            'product_name': item.product.name if item.product else 'Unknown Product',
            'quantity': float(item.quantity) if item.quantity else 0,
            'unit_cost': float(item.unit_cost) if item.unit_cost else 0,
            'total_cost': float(item.total_cost) if item.total_cost else 0
        })
    
    return jsonify({
        'id': purchase_return.id,
        'date': purchase_return.date.strftime('%Y-%m-%d') if purchase_return.date else None,
        'original_purchase_id': purchase_return.original_purchase_id,
        'supplier_name': purchase_return.supplier.name if purchase_return.supplier else 'Unknown',
        'return_reason': purchase_return.return_reason or '',
        'refund_amount': float(purchase_return.refund_amount) if purchase_return.refund_amount else 0,
        'notes': purchase_return.notes or '',
        'items': items
    })

@purchases_bp.route('/api/purchases/<int:purchase_id>', methods=['PUT'])
@login_required
@require_permission('can_access_purchases')
def update_purchase(purchase_id):
    """API to update purchase status and amount paid."""
    company_id = get_company_id()
    purchase_query = Purchase.query.filter_by(id=purchase_id)
    if company_id and hasattr(Purchase, 'company_id'):
        purchase_query = purchase_query.filter(Purchase.company_id == company_id)
    purchase = purchase_query.first()
    if not purchase:
        return jsonify({'error': 'Purchase not found'}), 404
    data = request.get_json()
    
    try:
        if 'status' in data:
            purchase.status = data['status']
        if 'amount_paid' in data:
            purchase.amount_paid = float(data['amount_paid'])
            
            # Auto-update status based on amount paid if not explicitly set
            if 'status' not in data:
                if purchase.amount_paid >= purchase.total_amount:
                    purchase.status = 'paid'
                elif purchase.amount_paid > 0:
                    purchase.status = 'partial'
                else:
                    purchase.status = 'pending'
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Purchase updated successfully',
            'purchase': {
                'id': purchase.id,
                'status': purchase.status or '',
                'amount_paid': float(purchase.amount_paid) if purchase.amount_paid else 0,
                'total_amount': float(purchase.total_amount) if purchase.total_amount else 0,
                'balance': float(purchase.total_amount - purchase.amount_paid) if purchase.total_amount and purchase.amount_paid else 0
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@purchases_bp.route('/api/purchases/<int:purchase_id>', methods=['DELETE'])
@login_required
@require_permission('can_access_purchases')
def delete_purchase(purchase_id):
    """Delete a purchase (requires admin password verification)."""
    try:
        company_id = get_company_id()
        purchase_query = Purchase.query.filter_by(id=purchase_id)
        if company_id and hasattr(Purchase, 'company_id'):
            purchase_query = purchase_query.filter(Purchase.company_id == company_id)
        purchase = purchase_query.first()
        if not purchase:
            return jsonify({'success': False, 'message': 'Purchase not found'}), 404
        
        # Get JSON data with better error handling
        try:
            data = request.get_json() if request.is_json else {}
        except Exception as e:
            return jsonify({'success': False, 'message': f'Invalid JSON: {str(e)}'}), 400
        
        # Verify admin password exists
        admin_password = data.get('admin_password', '').strip()
        if not admin_password:
            return jsonify({'success': False, 'message': 'Admin password is required'}), 400
        
        # Verify password against current user
        if not current_user.check_password(admin_password):
            return jsonify({'success': False, 'message': 'Invalid admin password'}), 401
        
        # Delete associated purchase returns first (they have FK to this purchase)
        purchase_returns = PurchaseReturn.query.filter_by(original_purchase_id=purchase_id).all()
        for pr in purchase_returns:
            # Delete purchase return items (cascade)
            for item in pr.items:
                db.session.delete(item)
            # Delete the purchase return
            db.session.delete(pr)
        
        # Reverse stock updates from purchase items
        for item in purchase.items:
            product = item.product
            if product:
                # Reverse the stock increase
                product.stock -= item.quantity
                
                # Log reversal transaction
                inv_trans = InventoryTransaction(
                    product_id=product.id,
                    transaction_type='purchase_reversed',
                    quantity=-item.quantity,
                    previous_stock=product.stock + item.quantity,
                    new_stock=product.stock,
                    reference_id=purchase.id,
                    company_id=get_company_id(),
                    notes=f'Purchase #{purchase.id} deleted - stock reversed'
                )
                db.session.add(inv_trans)
        
        # Delete purchase (cascade will delete purchase items)
        db.session.delete(purchase)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Purchase #{purchase.id} deleted successfully. Stock levels have been reversed.'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error deleting purchase: {str(e)}'}), 400

@purchases_bp.route('/api/purchase-returns/<int:return_id>', methods=['DELETE'])
@login_required
@require_permission('can_manage_purchase_returns')
def delete_purchase_return(return_id):
    """Delete a purchase return (requires admin password verification)."""
    try:
        # Get the purchase return
        purchase_return = PurchaseReturn.query.get(return_id)
        if not purchase_return:
            return jsonify({'success': False, 'message': 'Purchase return not found'}), 404
        
        # Parse JSON data from request body
        admin_password = ''
        try:
            if request.data:
                data = json.loads(request.data.decode('utf-8'))
                admin_password = data.get('admin_password', '').strip()
        except Exception as parse_error:
            return jsonify({'success': False, 'message': f'Could not parse request: {str(parse_error)}'}), 400
        
        # Verify admin password exists
        if not admin_password:
            return jsonify({'success': False, 'message': 'Admin password is required'}), 400
        
        # Verify password against current user
        if not current_user.check_password(admin_password):
            return jsonify({'success': False, 'message': 'Invalid admin password'}), 401
        
        # Reverse stock updates and delete items
        for item in list(purchase_return.items):
            product = item.product
            if product:
                previous_stock = product.stock
                product.stock += item.quantity
                
                inv_trans = InventoryTransaction(
                    product_id=product.id,
                    transaction_type='return_deleted',  # Max 20 chars
                    quantity=item.quantity,
                    previous_stock=previous_stock,
                    new_stock=product.stock,
                    reference_id=purchase_return.id,
                    company_id=get_company_id(),
                    notes=f'Purchase Return #{purchase_return.id} deleted - stock reversed'
                )
                db.session.add(inv_trans)
            
            db.session.delete(item)
        
        # Delete purchase return
        db.session.delete(purchase_return)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Purchase Return #{purchase_return.id} deleted successfully. Stock levels have been reversed.'
        }), 200
        
    except Exception as e:
        try:
            db.session.rollback()
        except:
            pass
        return jsonify({'success': False, 'message': str(e)}), 400
