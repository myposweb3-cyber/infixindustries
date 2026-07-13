import os
from flask import Flask, session
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_socketio import SocketIO
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config, get_config
from app.models import db, User, Setting, Company

# Initialize extensions
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
socketio = SocketIO(cors_allowed_origins="*")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_app(config_class=None):
    app = Flask(__name__)
    # Allow passing either a config class or a config name string (e.g., 'testing')
    if config_class is None:
        config_obj = get_config()
    elif isinstance(config_class, str):
        config_obj = get_config(config_class)
    else:
        config_obj = config_class

    app.config.from_object(config_obj)

    # Configure ProxyFix for reverse proxy (nginx) headers
    # This ensures that X-Forwarded-Proto, X-Forwarded-For, etc. are properly handled
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(app)

    # Set login view
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.sales import sales_bp
    from app.routes.inventory import inventory_bp
    from app.routes.customers import customers_bp
    from app.routes.reports import reports_bp
    from app.routes.settings_new import settings_bp
    from app.routes.expenses import expenses_bp
    from app.routes.purchases import purchases_bp
    from app.routes.warehouse_api import warehouse_api_bp
    from app.routes.suppliers import suppliers_bp
    from app.routes.scale import scale_bp
    from app.routes.companies import companies_bp
    from app.routes.cheques import cheques_bp
    from app.routes.audit import audit_bp
    from app.routes.invoices import invoices_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(customers_bp, url_prefix='/customers')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(settings_bp)
    app.register_blueprint(expenses_bp, url_prefix='/expenses')
    app.register_blueprint(purchases_bp)
    app.register_blueprint(warehouse_api_bp)
    app.register_blueprint(suppliers_bp, url_prefix='/suppliers')
    app.register_blueprint(scale_bp)
    app.register_blueprint(companies_bp, url_prefix='/companies')
    app.register_blueprint(cheques_bp, url_prefix='/cheques')
    app.register_blueprint(audit_bp, url_prefix='/audit')
    app.register_blueprint(invoices_bp)

    # ✅ REGISTER MULTI-COMPANY SECURITY MIDDLEWARE
    from app.utils.security import before_request_company_check
    app.before_request(before_request_company_check)

    # Add Jinja filter for timezone conversion (UTC to Pakistan Standard Time UTC+5)
    @app.template_filter('to_local_time')
    def to_local_time(dt):
        """Convert UTC datetime to Pakistan Standard Time (UTC+5)"""
        from datetime import timedelta
        if dt is None:
            return ''
        local_dt = dt + timedelta(hours=5)
        return local_dt.strftime('%d/%m/%Y %H:%M')

    # Company context processor - adds company info to all templates
    @app.context_processor
    def inject_company():
        from app.utils.company import get_current_company, get_user_companies
        company = None
        companies = []
        
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            # Get user's companies
            companies = get_user_companies(current_user.id)
            company = get_current_company()
            
            # If no company selected but user has companies, select first one
            if not company and companies:
                company = companies[0]
                from app.utils.company import set_current_company
                set_current_company(company.id)
        
        return dict(current_company=company, user_companies=companies)

    # Serve uploaded files
    @app.route('/uploads/<path:filename>')
    def serve_upload(filename):
        from flask import send_from_directory
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        return send_from_directory(upload_dir, filename)

    # Create database tables
    with app.app_context():
        db.create_all()

        # Create default settings if they don't exist (skip in testing)
        if not app.config.get('TESTING'):
            try:
                default_settings = [
                    ('general', 'business_name', 'POS System Web'),
                    ('general', 'currency_symbol', '₨'),
                    ('tax', 'gstRate', '18.0'),
                    ('printing', 'receipt_footer', 'Thank you for your business!'),
                    ('printing', 'show_logo', 'true'),
                ]

                for category, key, value in default_settings:
                    existing = Setting.query.filter_by(setting_category=category, setting_key=key).first()
                    if not existing:
                        setting = Setting(setting_category=category, setting_key=key, setting_value=value)
                        db.session.add(setting)

                db.session.commit()

                # Create default Super Admin user if not exists (skip in testing)
                super_admin = User.query.filter_by(username='admin').first()
                if not super_admin:
                    super_admin = User(
                        username='admin',
                        email='admin@example.com',
                        role='Super Admin',
                        # Super Admin gets ALL permissions
                        can_access_sales=True,
                        can_access_purchases=True,
                        can_access_suppliers=True,
                        can_view_inventory=True,
                        can_edit_inventory=True,
                        can_view_sales_history=True,
                        can_view_reports=True,
                        can_access_expenses=True,
                        can_access_customers=True,
                        can_view_profit=True,
                        can_access_warehouse=True,
                        can_access_settings=True,
                        can_access_cheques=True,
                        can_access_quotations=True,
                        can_access_messages=True,
                        can_access_audit_logs=True,
                        can_access_scale=True,
                        can_manage_returns=True,
                        can_manage_purchase_returns=True,
                        can_manage_customer_payments=True,
                        can_view_general_settings=True,
                        can_view_receipt_settings=True,
                        can_view_terminal_settings=True,
                        can_view_backup_settings=True,
                        can_view_hardware_settings=True
                    )
                    super_admin.set_password('admin123')
                    db.session.add(super_admin)
                    db.session.commit()
                else:
                    # Upgrade existing admin user to Super Admin role if not already
                    if super_admin.role != 'Super Admin':
                        super_admin.role = 'Super Admin'
                        # Grant all permissions
                        super_admin.can_access_sales = True
                        super_admin.can_access_purchases = True
                        super_admin.can_access_suppliers = True
                        super_admin.can_view_inventory = True
                        super_admin.can_edit_inventory = True
                        super_admin.can_view_sales_history = True
                        super_admin.can_view_reports = True
                        super_admin.can_access_expenses = True
                        super_admin.can_access_customers = True
                        super_admin.can_view_profit = True
                        super_admin.can_access_warehouse = True
                        super_admin.can_access_settings = True
                        super_admin.can_access_cheques = True
                        super_admin.can_access_quotations = True
                        super_admin.can_access_messages = True
                        super_admin.can_access_audit_logs = True
                        super_admin.can_access_scale = True
                        super_admin.can_manage_returns = True
                        super_admin.can_manage_purchase_returns = True
                        super_admin.can_manage_customer_payments = True
                        super_admin.can_view_general_settings = True
                        super_admin.can_view_receipt_settings = True
                        super_admin.can_view_terminal_settings = True
                        super_admin.can_view_backup_settings = True
                        super_admin.can_view_hardware_settings = True
                        db.session.commit()
                
                # Create default company if none exists
                if not Company.query.first():
                    default_company = Company(
                        name='Default Company',
                        business_name='My POS Business',
                        address='Main Street',
                        phone='+1234567890',
                        email='info@company.com',
                        is_active=True
                    )
                    db.session.add(default_company)
                    db.session.commit()
                    
                    # Add Super Admin to the default company
                    if super_admin not in default_company.users:
                        default_company.users.append(super_admin)
                        db.session.commit()
            except Exception as e:
                # Database schema might be out of sync due to migrations
                # This is expected during migration process
                db.session.rollback()
                app.logger.warning(f"Database initialization skipped (likely due to pending migrations): {str(e)}")

    return app
