
from datetime import datetime
from enum import Enum
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app

db = SQLAlchemy()

# --- User Role Enum ---
class UserRole(Enum):
    """User roles for access control and permissions."""
    SUPER_ADMIN = "Super Admin"     # Can manage all companies and users
    ADMIN = "Admin"                  # Can manage one assigned company
    MANAGER = "Manager"              # Can manage operations in assigned company
    CASHIER = "Cashier"              # Can perform transactions in assigned company
    
    def __str__(self):
        """Return the enum value when str() is called."""
        return self.value

# --- Association Table for User-Company relationship ---
user_companies = db.Table('user_companies',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('company_id', db.Integer, db.ForeignKey('companies.id'), primary_key=True),
    db.Column('is_admin', db.Boolean, default=False),  # User is admin for this company
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

# --- Company Model ---
class Company(db.Model):
    """Company model for multi-company support."""
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    business_name = db.Column(db.String(255))
    tax_id = db.Column(db.String(50))  # Tax registration number
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Settings - stored as JSON for flexibility
    default_currency = db.Column(db.String(10), default='LKR')
    timezone = db.Column(db.String(50), default='Asia/Colombo')

    # Relationships
    users = db.relationship('User', secondary=user_companies, back_populates='companies')
    warehouses = db.relationship('Warehouse', backref='company', lazy=True, cascade='all, delete-orphan')
    products = db.relationship('Product', backref='company', lazy=True, cascade='all, delete-orphan')
    customers = db.relationship('Customer', backref='company', lazy=True, cascade='all, delete-orphan')
    suppliers = db.relationship('Supplier', backref='company', lazy=True, cascade='all, delete-orphan')
    sales = db.relationship('Sale', backref='company', lazy=True, cascade='all, delete-orphan')
    expenses = db.relationship('Expense', backref='company', lazy=True, cascade='all, delete-orphan')
    purchases = db.relationship('Purchase', backref='company', lazy=True, cascade='all, delete-orphan')

# --- Warehouse Model ---
class Warehouse(db.Model):
    """Warehouse model for multi-warehouse support."""
    __tablename__ = 'warehouses'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

    # Relationship: products in this warehouse
    products = db.relationship('Product', backref='warehouse', lazy=True, cascade='all, delete-orphan')
    
    # Unique constraint: name must be unique per company
    __table_args__ = (
        db.UniqueConstraint('name', 'company_id', name='uq_warehouse_name_company'),
    )

class User(db.Model, UserMixin):
    """User model for authentication and permissions."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Role stored as string for backward compatibility, but should use UserRole enum values
    # Valid values: "Super Admin", "Admin", "Manager", "Cashier"
    role = db.Column(db.String(20), default=str(UserRole.CASHIER))
    
    last_login = db.Column(db.DateTime)
    profile_picture = db.Column(db.String(255), nullable=True)  # Path to profile picture
    
    # Company relationship - users can belong to multiple companies
    # ⚠️ FUTURE: Should be single company except for Super Admin
    companies = db.relationship('Company', secondary=user_companies, back_populates='users')

    # Permission fields
    can_access_sales = db.Column(db.Boolean, default=False)
    can_access_purchases = db.Column(db.Boolean, default=False)
    can_access_suppliers = db.Column(db.Boolean, default=False)
    can_view_inventory = db.Column(db.Boolean, default=False)
    can_edit_inventory = db.Column(db.Boolean, default=False)
    can_view_sales_history = db.Column(db.Boolean, default=False)
    can_view_reports = db.Column(db.Boolean, default=False)
    can_access_expenses = db.Column(db.Boolean, default=False)
    can_access_customers = db.Column(db.Boolean, default=False)
    can_view_profit = db.Column(db.Boolean, default=False)
    can_access_warehouse = db.Column(db.Boolean, default=False)
    can_access_settings = db.Column(db.Boolean, default=False)
    can_access_cheques = db.Column(db.Boolean, default=False)
    can_access_quotations = db.Column(db.Boolean, default=False)
    can_access_messages = db.Column(db.Boolean, default=False)
    can_access_audit_logs = db.Column(db.Boolean, default=False)
    can_access_scale = db.Column(db.Boolean, default=False)
    can_manage_returns = db.Column(db.Boolean, default=False)
    can_manage_purchase_returns = db.Column(db.Boolean, default=False)
    can_manage_customer_payments = db.Column(db.Boolean, default=False)
    
    # Settings Tab Permissions
    can_view_general_settings = db.Column(db.Boolean, default=False)
    can_view_receipt_settings = db.Column(db.Boolean, default=False)
    can_view_terminal_settings = db.Column(db.Boolean, default=False)
    can_view_backup_settings = db.Column(db.Boolean, default=False)
    can_view_hardware_settings = db.Column(db.Boolean, default=False)
    
    # Profile Permission
    can_view_own_profile = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_role_enum(self):
        """
        Convert string role to UserRole enum.
        Returns the UserRole enum value corresponding to this user's role.
        """
        if not self.role:
            return UserRole.CASHIER
        
        role_str = str(self.role).lower()
        for role in UserRole:
            if role.value.lower() == role_str:
                return role
        
        # Default to CASHIER if role not recognized
        return UserRole.CASHIER
    
    def is_super_admin(self):
        """Check if user is Super Admin."""
        return self.get_role_enum() == UserRole.SUPER_ADMIN
    
    def is_admin(self):
        """Check if user is Admin or Super Admin."""
        role = self.get_role_enum()
        return role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]
    
    def get_reset_token(self, expires_sec=3600):
        """Generate a URL-safe timed token for password reset.
        
        Args:
            expires_sec: Token expiration time in seconds (default: 1 hour)
            
        Returns:
            URL-safe timed token string
        """
        s = Serializer(current_app.config['SECRET_KEY'], expires_in=expires_sec)
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token, max_age=3600):
        """Verify reset token and return the user or None."""
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=max_age)
        except Exception:
            return None
        return User.query.get(data.get('user_id'))

class Product(db.Model):
    """Product model for inventory items."""
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, default=0.0)
    stock = db.Column(db.Float, nullable=False)
    unit_type = db.Column(db.String(10), default='unit')  # 'unit' or 'kg'
    category = db.Column(db.String(50), default='General')
    low_stock_threshold = db.Column(db.Float, default=5.0)
    barcode = db.Column(db.String(50))
    description = db.Column(db.Text)
    image_path = db.Column(db.String(255))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    # Price per KG for weighted products (vegetables, fruits, meats, etc.)
    price_per_kg = db.Column(db.Float, nullable=True)
    # Product code for barcode matching (used with weighted products)
    product_code = db.Column(db.String(50))
    
    # Relationships
    supplier = db.relationship('Supplier', backref='products')

class Sale(db.Model):
    """Sale model for transactions."""
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.Column(db.String(255), default='Walk-in Customer')
    total = db.Column(db.Float, nullable=False)
    payment = db.Column(db.String(20), default='Cash')
    cash_given = db.Column(db.Float, default=0.0)
    balance = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

    # Relationships
    user = db.relationship('User', backref='sales')
    items = db.relationship('SaleItem', backref='sale', lazy=True, cascade='all, delete-orphan')

class SaleItem(db.Model):
    """Sale item model for individual products in a sale."""
    __tablename__ = 'sale_items'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float, default=0.0)
    tax = db.Column(db.Float, default=0.0)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

    # Relationships
    product = db.relationship('Product', backref='sale_items')

class Customer(db.Model):
    """Customer model for customer management."""
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    address = db.Column(db.Text)
    loyalty_points = db.Column(db.Integer, default=0)
    total_purchases = db.Column(db.Float, default=0.0)
    last_purchase_date = db.Column(db.DateTime)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    preferred_payment_method = db.Column(db.String(20))
    credit_limit = db.Column(db.Float, default=0.0)
    credit_days = db.Column(db.Integer, default=0)  # Credit days for this customer (0 = use global setting)
    current_balance = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    
    # Outstanding aging tracking
    outstanding_0_30 = db.Column(db.Float, default=0.0)
    outstanding_30_60 = db.Column(db.Float, default=0.0)
    outstanding_60_90 = db.Column(db.Float, default=0.0)
    outstanding_90_plus = db.Column(db.Float, default=0.0)
    supply_stopped = db.Column(db.Boolean, default=False)
    last_balance_update = db.Column(db.DateTime)

class Supplier(db.Model):
    """Supplier model for supplier management."""
    __tablename__ = 'suppliers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    contact_person = db.Column(db.String(255))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(255))
    address = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

class Expense(db.Model):
    """Expense model for expense tracking."""
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

class Purchase(db.Model):
    """Purchase model for purchase orders."""
    __tablename__ = 'purchases'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    invoice_number = db.Column(db.String(50))
    total_amount = db.Column(db.Float)
    amount_paid = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='pending')
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

    # Relationships
    supplier = db.relationship('Supplier', backref='purchases')
    items = db.relationship('PurchaseItem', backref='purchase', lazy=True, cascade='all, delete-orphan')

class PurchaseItem(db.Model):
    """Purchase item model for individual products in a purchase."""
    __tablename__ = 'purchase_items'

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    product = db.relationship('Product', backref='purchase_items')
    company = db.relationship('Company', backref='purchase_items', foreign_keys=[company_id])

class PurchaseReturn(db.Model):
    """Model for returning items from a purchase to a supplier."""
    __tablename__ = 'purchase_returns'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    original_purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    return_reason = db.Column(db.String(255))
    refund_amount = db.Column(db.Float, nullable=False)
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    original_purchase = db.relationship('Purchase', backref='purchase_returns')
    supplier = db.relationship('Supplier', backref='purchase_returns')
    user = db.relationship('User', backref='purchase_returns')
    items = db.relationship('PurchaseReturnItem', backref='purchase_return', lazy=True, cascade='all, delete-orphan')
    company = db.relationship('Company', backref='purchase_returns', foreign_keys=[company_id])

class PurchaseReturnItem(db.Model):
    """Model for items in a purchase return."""
    __tablename__ = 'purchase_return_items'

    id = db.Column(db.Integer, primary_key=True)
    purchase_return_id = db.Column(db.Integer, db.ForeignKey('purchase_returns.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    product = db.relationship('Product', backref='purchase_return_items')
    company = db.relationship('Company', backref='purchase_return_items', foreign_keys=[company_id])

class PurchaseOrder(db.Model):
    """Purchase order model for ordering from suppliers."""
    __tablename__ = 'purchase_orders'

    id = db.Column(db.Integer, primary_key=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    status = db.Column(db.String(20), default='pending')
    expected_delivery_date = db.Column(db.DateTime)
    total_amount = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    supplier = db.relationship('Supplier', backref='purchase_orders')
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')
    company = db.relationship('Company', backref='purchase_orders', foreign_keys=[company_id])

class PurchaseOrderItem(db.Model):
    """Purchase order item model."""
    __tablename__ = 'purchase_order_items'

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_ordered = db.Column(db.Float, nullable=False)
    quantity_received = db.Column(db.Float, default=0.0)
    unit_cost = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    product = db.relationship('Product', backref='purchase_order_items')
    company = db.relationship('Company', backref='purchase_order_items', foreign_keys=[company_id])

# --- Cheque Model ---
class Cheque(db.Model):
    """Cheque entry and tracking model."""
    __tablename__ = 'cheques'

    id = db.Column(db.Integer, primary_key=True)
    cheque_number = db.Column(db.String(50), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    branch = db.Column(db.String(100))
    cheque_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payer_name = db.Column(db.String(255), nullable=True)  # Nullable for backward compat; use customer_name if not set
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    notes = db.Column(db.Text)
    image_front = db.Column(db.String(255))  # Path to uploaded image
    image_back = db.Column(db.String(255))
    status = db.Column(db.String(20), default='pending')  # pending, deposited, cleared, bounced, cancelled
    status_updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    deposit_id = db.Column(db.Integer, db.ForeignKey('cheque_deposits.id'), nullable=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True)  # Link to sale/invoice
    purchase_id = db.Column(db.Integer, db.ForeignKey('purchases.id'), nullable=True)  # Link to purchase
    is_partial = db.Column(db.Boolean, default=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    customer = db.relationship('Customer', backref='cheques', foreign_keys=[customer_id])
    supplier = db.relationship('Supplier', backref='cheques', foreign_keys=[supplier_id])
    deposit = db.relationship('ChequeDeposit', backref='cheques', foreign_keys=[deposit_id])
    sale = db.relationship('Sale', backref='cheques', foreign_keys=[sale_id])
    purchase = db.relationship('Purchase', backref='cheques', foreign_keys=[purchase_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    updater = db.relationship('User', foreign_keys=[updated_by])
    company = db.relationship('Company', backref='cheques', foreign_keys=[company_id])

    __table_args__ = (
        db.UniqueConstraint('cheque_number', 'bank_name', name='uq_cheque_number_bank'),
    )

# --- Cheque Deposit Model ---
class ChequeDeposit(db.Model):
    """Model for grouping cheques into a bank deposit."""
    __tablename__ = 'cheque_deposits'

    id = db.Column(db.Integer, primary_key=True)
    deposit_date = db.Column(db.Date, nullable=False)
    bank_account = db.Column(db.String(100), nullable=False)
    reference_number = db.Column(db.String(100))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    creator = db.relationship('User', foreign_keys=[created_by])
    company = db.relationship('Company', backref='cheque_deposits', foreign_keys=[company_id])

class InventoryTransaction(db.Model):
    """Inventory transaction model for tracking stock changes."""
    __tablename__ = 'inventory_transactions'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # 'sale', 'purchase', 'adjustment', 'return'
    quantity = db.Column(db.Float, nullable=False)
    previous_stock = db.Column(db.Float, nullable=False)
    new_stock = db.Column(db.Float, nullable=False)
    reference_id = db.Column(db.Integer)  # sale_id, purchase_id, etc.
    date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    product = db.relationship('Product', backref='inventory_transactions')
    company = db.relationship('Company', backref='inventory_transactions', foreign_keys=[company_id])

class SerialNumber(db.Model):
    """Serial number model for serial/lot tracking."""
    __tablename__ = 'serial_numbers'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    serial_number = db.Column(db.String(100), unique=True, nullable=False)
    lot_number = db.Column(db.String(50))
    expiry_date = db.Column(db.DateTime)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, sold, expired, damaged
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    product = db.relationship('Product', backref='serial_numbers')
    company = db.relationship('Company', backref='serial_numbers', foreign_keys=[company_id])

class Promotion(db.Model):
    """Promotion model for discounts and offers."""
    __tablename__ = 'promotions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    discount_type = db.Column(db.String(20), nullable=False)  # 'percentage', 'fixed_amount', 'buy_x_get_y'
    discount_value = db.Column(db.Float, nullable=False)
    minimum_purchase = db.Column(db.Float, default=0.0)
    applicable_products = db.Column(db.Text, default='all')  # JSON array of product IDs, or 'all'
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    usage_limit = db.Column(db.Integer, default=-1)  # -1 for unlimited
    usage_count = db.Column(db.Integer, default=0)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    company = db.relationship('Company', backref='promotions', foreign_keys=[company_id])

class CustomerFeedback(db.Model):
    """Customer feedback model for ratings and reviews."""
    __tablename__ = 'customer_feedback'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    feedback_text = db.Column(db.Text)
    feedback_date = db.Column(db.DateTime, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    customer = db.relationship('Customer', backref='feedback')
    sale = db.relationship('Sale', backref='feedback')
    company = db.relationship('Company', backref='customer_feedback', foreign_keys=[company_id])

class HeldBill(db.Model):
    """Held bill model for temporarily saving sales."""
    __tablename__ = 'held_bills'

    id = db.Column(db.Integer, primary_key=True)
    bill_data = db.Column(db.Text, nullable=False)  # JSON data
    held_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    user = db.relationship('User', backref='held_bills')
    company = db.relationship('Company', backref='held_bills', foreign_keys=[company_id])

class Setting(db.Model):
    """Settings model for application configuration."""
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    setting_category = db.Column(db.String(50), nullable=False)
    setting_key = db.Column(db.String(100), nullable=False)
    setting_value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    company = db.relationship('Company', backref='settings', foreign_keys=[company_id])

    __table_args__ = (db.UniqueConstraint('setting_category', 'setting_key', 'company_id', name='unique_setting_per_company'),)


class Return(db.Model):
    """Return model for tracking returns/refunds."""
    __tablename__ = 'returns'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    original_sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    customer = db.Column(db.String(255), default='Walk-in Customer')
    return_reason = db.Column(db.String(255), nullable=False)
    refund_method = db.Column(db.String(20), nullable=False)  # 'Cash', 'Card', 'Store Credit'
    refund_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='completed')  # 'pending', 'completed', 'cancelled'
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    original_sale = db.relationship('Sale', backref='returns')
    user = db.relationship('User', backref='returns')
    items = db.relationship('ReturnItem', backref='return', lazy=True, cascade='all, delete-orphan')
    company = db.relationship('Company', backref='returns', foreign_keys=[company_id])


class ReturnItem(db.Model):
    """Return item model for individual products in a return."""
    __tablename__ = 'return_items'

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)  # Price at time of return
    reason = db.Column(db.String(255))
    original_sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    # Relationships
    product = db.relationship('Product', backref='return_items')
    original_sale_item = db.relationship('SaleItem', backref='return_items')
    company = db.relationship('Company', backref='return_items', foreign_keys=[company_id])


class Exchange(db.Model):
    """Exchange model to track item exchanges linked to sales and returns."""
    __tablename__ = 'exchanges'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    original_sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))
    new_sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'))
    customer = db.Column(db.String(255), default='Walk-in Customer')
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    user = db.relationship('User', backref='exchanges')
    items = db.relationship('ExchangeItem', backref='exchange', lazy=True, cascade='all, delete-orphan')
    company = db.relationship('Company', backref='exchanges', foreign_keys=[company_id])


class ExchangeItem(db.Model):
    __tablename__ = 'exchange_items'

    id = db.Column(db.Integer, primary_key=True)
    exchange_id = db.Column(db.Integer, db.ForeignKey('exchanges.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)  # Multi-company support

    product = db.relationship('Product', backref='exchange_items')
    company = db.relationship('Company', backref='exchange_items', foreign_keys=[company_id])


class CustomerPayment(db.Model):
    """Customer payment model for recording payments received from customers."""
    __tablename__ = 'customer_payments'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=True)  # Optional: link to specific sale
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), default='Cash')  # Cash, Card, Bank Transfer, etc.
    reference_number = db.Column(db.String(50))  # Cheque number, transaction ID, etc.
    notes = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)

    # Relationships
    customer = db.relationship('Customer', backref='payments')
    sale = db.relationship('Sale', backref='customer_payments')
    user = db.relationship('User', backref='customer_payments')


class AuditLog(db.Model):
    """Audit log model for tracking all changes in the system."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    entity_type = db.Column(db.String(50), nullable=False)  # 'User', 'Product', 'Customer', 'Sale', 'Setting', 'Expense', etc.
    entity_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(50), nullable=False)  # 'create', 'update', 'delete', 'login', 'logout'
    old_values = db.Column(db.Text)  # JSON string of old values
    new_values = db.Column(db.Text)  # JSON string of new values
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    description = db.Column(db.Text)  # Human-readable description

    # Relationships
    user = db.relationship('User', backref='audit_logs')
    company = db.relationship('Company', backref='audit_logs')

    def to_dict(self):
        """Convert audit log to dictionary."""
        import json
        # Convert timestamp to ISO format with UTC timezone indicator
        timestamp_iso = None
        if self.timestamp:
            # Use isoformat and append 'Z' to explicitly mark as UTC
            timestamp_iso = self.timestamp.isoformat() + 'Z'
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else 'System',
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'action': self.action,
            'old_values': json.loads(self.old_values) if self.old_values else None,
            'new_values': json.loads(self.new_values) if self.new_values else None,
            'timestamp': timestamp_iso,
            'timestamp_str': self.timestamp.strftime('%Y-%m-%d %H:%M:%S') if self.timestamp else None,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'company_id': self.company_id,
            'company_name': self.company.name if self.company else None,
            'description': self.description
        }
