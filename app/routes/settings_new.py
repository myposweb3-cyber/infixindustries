from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, send_file
from flask_login import login_required, current_user
from app.models import db, Setting, User
from app.utils.permissions import require_permission
from app.utils.security import get_company_id
from app.utils.company import get_user_companies
from datetime import datetime
import os
import shutil
import subprocess
import json
from urllib.parse import urlparse
from app import csrf

settings_bp = Blueprint('settings', __name__, template_folder='../../templates')

def find_pg_dump():
    """Find pg_dump executable, checking common Windows installation paths."""
    if os.name == 'nt':  # Windows
        # Common PostgreSQL installation paths on Windows
        possible_paths = [
            r'C:\Program Files\PostgreSQL\17\bin\pg_dump.exe',
            r'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe',
            r'C:\Program Files\PostgreSQL\16\bin\pg_dump.exe',
            r'C:\Program Files\PostgreSQL\15\bin\pg_dump.exe',
            r'C:\Program Files (x86)\PostgreSQL\17\bin\pg_dump.exe',
            r'C:\Program Files (x86)\PostgreSQL\18\bin\pg_dump.exe',
            r'C:\Program Files (x86)\PostgreSQL\16\bin\pg_dump.exe',
            r'C:\Program Files (x86)\PostgreSQL\15\bin\pg_dump.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    
    # Fallback to 'pg_dump' (assumes it's in PATH)
    return 'pg_dump'

def export_company_data_to_sql(company_id):
    """Export all company data as SQL INSERT statements."""
    from sqlalchemy import inspect
    
    try:
        from app.models import (
            Sale, SaleItem, Return, ReturnItem, Exchange, ExchangeItem,
            Product, Customer, Supplier, Expense, Purchase, PurchaseItem,
            PurchaseReturn, PurchaseReturnItem, InventoryTransaction, 
            Promotion, CustomerFeedback, HeldBill, Setting, Warehouse,
            SerialNumber, PurchaseOrder, PurchaseOrderItem, Cheque, ChequeDeposit,
            AuditLog, CustomerPayment
        )
    except ImportError as e:
        raise Exception(f"Cannot import models: {e}")
    
    # List of models that have company_id field
    company_models = [
        Sale, SaleItem, Return, ReturnItem, Exchange, ExchangeItem,
        Product, Customer, Supplier, Expense, Purchase, PurchaseItem,
        PurchaseReturn, PurchaseReturnItem, InventoryTransaction,
        Promotion, CustomerFeedback, HeldBill, Setting, Warehouse,
        SerialNumber, PurchaseOrder, PurchaseOrderItem, Cheque, ChequeDeposit,
        AuditLog, CustomerPayment
    ]
    
    export_data = {
        'company_id': company_id,
        'exported_at': datetime.now().isoformat(),
        'tables': {}
    }
    
    for model in company_models:
        try:
            # Query records for this company
            records = db.session.query(model).filter(
                model.company_id == company_id
            ).all()
            
            if not records:
                continue
            
            table_name = model.__tablename__
            export_data['tables'][table_name] = []
            
            # Convert each record to dictionary
            mapper = inspect(model)
            for record in records:
                row_dict = {}
                for column in mapper.columns:
                    value = getattr(record, column.name)
                    # Handle datetime and other non-JSON serializable types
                    if isinstance(value, datetime):
                        row_dict[column.name] = value.isoformat()
                    else:
                        row_dict[column.name] = value
                export_data['tables'][table_name].append(row_dict)
        
        except Exception as e:
            current_app.logger.warning(f"Could not export {model.__tablename__}: {e}")
            continue
    
    return json.dumps(export_data, indent=2, default=str)

def import_company_data_from_sql(company_id, sql_data):
    """Import company data from JSON export. Replaces existing company data."""
    from sqlalchemy import insert, text
    
    try:
        data = json.loads(sql_data)
    except json.JSONDecodeError as e:
        raise Exception(f"Invalid backup format: {e}")
    
    if data.get('company_id') != company_id:
        raise Exception(f"Backup company ID ({data.get('company_id')}) does not match current company ({company_id})")
    
    try:
        from app.models import (
            Sale, SaleItem, Return, ReturnItem, Exchange, ExchangeItem,
            Product, Customer, Supplier, Expense, Purchase, PurchaseItem,
            PurchaseReturn, PurchaseReturnItem, InventoryTransaction, 
            Promotion, CustomerFeedback, HeldBill, Setting, Warehouse,
            SerialNumber, PurchaseOrder, PurchaseOrderItem, Cheque, ChequeDeposit,
            AuditLog, CustomerPayment
        )
    except ImportError as e:
        raise Exception(f"Cannot import models: {e}")
    
    model_map = {
        'sale': Sale,
        'sale_item': SaleItem,
        'return': Return,
        'return_item': ReturnItem,
        'exchange': Exchange,
        'exchange_item': ExchangeItem,
        'product': Product,
        'customer': Customer,
        'supplier': Supplier,
        'expense': Expense,
        'purchase': Purchase,
        'purchase_item': PurchaseItem,
        'purchase_return': PurchaseReturn,
        'purchase_return_item': PurchaseReturnItem,
        'inventory_transaction': InventoryTransaction,
        'promotion': Promotion,
        'customer_feedback': CustomerFeedback,
        'held_bill': HeldBill,
        'setting': Setting,
        'warehouse': Warehouse,
        'serial_number': SerialNumber,
        'purchase_order': PurchaseOrder,
        'purchase_order_item': PurchaseOrderItem,
        'cheque': Cheque,
        'cheque_deposit': ChequeDeposit,
        'audit_log': AuditLog,
        'customer_payment': CustomerPayment
    }
    
    # CRITICAL: Delete existing company data FIRST to avoid PRIMARY KEY conflicts
    # Delete in reverse dependency order (child tables before parent tables)
    current_app.logger.info(f"[RESTORE] Clearing existing data for company {company_id}...")
    deletion_order = [
        (AuditLog, "AuditLog"),
        (SaleItem, "SaleItem"),
        (Sale, "Sale"),
        (ExchangeItem, "ExchangeItem"),
        (Exchange, "Exchange"),
        (ReturnItem, "ReturnItem"),
        (Return, "Return"),
        (PurchaseReturnItem, "PurchaseReturnItem"),
        (PurchaseReturn, "PurchaseReturn"),
        (PurchaseOrderItem, "PurchaseOrderItem"),
        (PurchaseOrder, "PurchaseOrder"),
        (PurchaseItem, "PurchaseItem"),
        (Purchase, "Purchase"),
        (InventoryTransaction, "InventoryTransaction"),
        (CustomerPayment, "CustomerPayment"),
        (Cheque, "Cheque"),
        (ChequeDeposit, "ChequeDeposit"),
        (CustomerFeedback, "CustomerFeedback"),
        (HeldBill, "HeldBill"),
        (Expense, "Expense"),
        (Promotion, "Promotion"),
        (SerialNumber, "SerialNumber"),
        (Product, "Product"),
        (Customer, "Customer"),
        (Supplier, "Supplier"),
        (Warehouse, "Warehouse"),
        (Setting, "Setting"),
    ]
    
    deleted_records = {}
    for model_class, table_name in deletion_order:
        try:
            if hasattr(model_class, 'company_id'):
                count = db.session.query(model_class).filter(
                    model_class.company_id == company_id
                ).delete(synchronize_session=False)
                if count > 0:
                    deleted_records[table_name] = count
                    current_app.logger.info(f"[RESTORE] Deleted {count} existing {table_name} records")
        except Exception as e:
            current_app.logger.warning(f"Warning: Could not delete {table_name}: {e}")
            # Continue anyway - might not have this table
    
    db.session.commit()
    current_app.logger.info(f"[RESTORE] Existing data cleared. Now importing backup...")
    
    # Reset sequences/autoincrement AFTER deletion and BEFORE import
    try:
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('postgresql:') or db_uri.startswith('postgres:'):
            current_app.logger.info(f"[RESTORE] Resetting PostgreSQL sequences...")
            sequence_info = []
            for table_name, table_data in data.get('tables', {}).items():
                if not table_data or 'id' not in table_data[0]:
                    continue
                max_id = max(int(row.get('id', 0)) for row in table_data if 'id' in row)
                if max_id > 0:
                    sequence_name = f"{table_name}_id_seq"
                    sequence_info.append((sequence_name, max_id))
            
            for sequence_name, max_id in sequence_info:
                try:
                    db.session.execute(text(f"ALTER SEQUENCE IF EXISTS {sequence_name} RESTART WITH {max_id + 1}"))
                except:
                    pass  # Ignore missing sequences
            
            db.session.commit()
            current_app.logger.info(f"[RESTORE] PostgreSQL sequences reset")
        
        elif db_uri.startswith('sqlite:'):
            current_app.logger.info(f"[RESTORE] Resetting SQLite autoincrement...")
            for table_name, table_data in data.get('tables', {}).items():
                if not table_data or 'id' not in table_data[0]:
                    continue
                max_id = max(int(row.get('id', 0)) for row in table_data if 'id' in row)
                if max_id > 0:
                    try:
                        db.session.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{table_name}'"))
                        db.session.execute(text(f"INSERT INTO sqlite_sequence (name, seq) VALUES ('{table_name}', {max_id})"))
                    except:
                        pass  # Ignore errors
            
            db.session.commit()
            current_app.logger.info(f"[RESTORE] SQLite autoincrement reset")
    except Exception as seq_error:
        current_app.logger.warning(f"Warning: Sequence reset not critical: {seq_error}")
    
    # Now import backup data
    tables_imported = 0
    records_imported = 0
    
    for table_name, table_data in data.get('tables', {}).items():
        if not table_data:
            continue
        
        try:
            # Find model for this table
            model = None
            for key, m in model_map.items():
                if m.__tablename__ == table_name:
                    model = m
                    break
            
            if not model:
                current_app.logger.warning(f"Unknown table: {table_name}")
                continue
            
            # Insert records
            for record in table_data:
                # Ensure company_id matches
                if 'company_id' in record:
                    record['company_id'] = company_id
                
                # Create instance and add
                obj = model(**record)
                db.session.add(obj)
            
            tables_imported += 1
            records_imported += len(table_data)
            current_app.logger.info(f"[RESTORE] Imported {len(table_data)} records into {table_name}")
        
        except Exception as e:
            current_app.logger.error(f"[RESTORE] Error importing {table_name}: {e}")
            raise
    
    db.session.commit()
    current_app.logger.info(f"[RESTORE] Restore complete. Imported {records_imported} records into {tables_imported} tables")
    return {'tables_imported': tables_imported, 'records_imported': records_imported, 'deleted_records': deleted_records}

def get_company_filtered_settings(category=None, key=None):
    """Helper to get settings with company filtering."""
    company_id = get_company_id()
    query = Setting.query
    
    if company_id and hasattr(Setting, 'company_id'):
        query = query.filter(Setting.company_id == company_id)
    
    if category:
        query = query.filter(Setting.setting_category == category)
    if key:
        query = query.filter(Setting.setting_key == key)
    
    return query

@settings_bp.route('/settings')
@login_required
@require_permission('can_access_settings')
def settings():
    return render_template('settings/settings.html')

@settings_bp.route('/profile')
@login_required
def profile():
    """Profile page accessible to all logged-in users."""
    return render_template('settings/profile.html')

@settings_bp.route('/api/currency-symbol', methods=['GET'])
@csrf.exempt
def get_currency_symbol():
    """Public endpoint to get currency symbol (no auth required, but company-scoped when logged in)"""
    company_id = None
    if current_user.is_authenticated:
        company_id = get_company_id()
    
    # First check the 'currency' category with 'symbol' key
    query = Setting.query.filter_by(
        setting_category='currency',
        setting_key='symbol'
    )
    if company_id and hasattr(Setting, 'company_id'):
        query = query.filter(Setting.company_id == company_id)
    setting = query.first()
    
    # Fallback to 'general' category with 'currency_symbol' key for legacy compatibility
    if not setting:
        query = Setting.query.filter_by(
            setting_category='general',
            setting_key='currency_symbol'
        )
        if company_id and hasattr(Setting, 'company_id'):
            query = query.filter(Setting.company_id == company_id)
        setting = query.first()
    
    if setting:
        return jsonify({'currency_symbol': setting.setting_value})
    return jsonify({'currency_symbol': 'Rs. '})

@settings_bp.route('/api/settings', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def getSettings():
    settings = get_company_filtered_settings().all()
    settings_by_category = {}
    for setting in settings:
        category = setting.setting_category
        if category not in settings_by_category:
            settings_by_category[category] = {}
        settings_by_category[category][setting.setting_key] = setting.setting_value
    return jsonify(settings_by_category)

@settings_bp.route('/api/settings', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def save_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No settings data provided'}), 400

    ALLOWED_CATEGORIES = [
        'general', 'tax', 'currency', 'datetime', 'printing', 'localization', 'receipt', 'terminal',
        'scale', 'printer'
    ]

    data_to_process = {cat: data[cat] for cat in data if cat in ALLOWED_CATEGORIES}

    try:
        company_id = get_company_id()
        
        for category, settings_dict in data_to_process.items():
            for key, value in settings_dict.items():
                if value is not None:
                    value = str(value)
                
                # Use no_autoflush to avoid premature flushes during query
                with db.session.no_autoflush:
                    setting = get_company_filtered_settings(category, key).first()
                
                if setting:
                    # Update existing setting
                    setting.setting_value = value
                    setting.updated_at = datetime.utcnow()
                else:
                    # Create new setting
                    setting = Setting(
                        setting_category=category,
                        setting_key=key,
                        setting_value=value,
                        company_id=company_id
                    )
                    db.session.add(setting)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Settings saved successfully'})
    except Exception as e:
        db.session.rollback()
        
        # Handle duplicate key errors more gracefully
        error_str = str(e).lower()
        if 'unique' in error_str or 'duplicate' in error_str:
            # Try to update instead of insert
            try:
                db.session.rollback()
                company_id = get_company_id()
                
                for category, settings_dict in data_to_process.items():
                    for key, value in settings_dict.items():
                        if value is not None:
                            value = str(value)
                        
                        setting = Setting.query.filter(
                            Setting.company_id == company_id,
                            Setting.setting_category == category,
                            Setting.setting_key == key
                        ).first()
                        
                        if setting:
                            setting.setting_value = value
                            setting.updated_at = datetime.utcnow()
                        else:
                            setting = Setting(
                                setting_category=category,
                                setting_key=key,
                                setting_value=value,
                                company_id=company_id
                            )
                            db.session.add(setting)
                
                db.session.commit()
                return jsonify({'success': True, 'message': 'Settings saved successfully'})
            except Exception as retry_error:
                db.session.rollback()
                return jsonify({'error': f'Failed to save settings: {str(retry_error)}'}), 500
        
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/categories/<category>')
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def get_category_settings(category):
    settings = get_company_filtered_settings(category=category).all()
    result = {}
    for setting in settings:
        result[setting.setting_key] = setting.setting_value
    return jsonify(result)

@settings_bp.route('/api/settings/upload-logo', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def upload_logo():
    if 'logo' not in request.files:
        return jsonify({'error': 'No logo file provided'}), 400

    file = request.files['logo']
    if file.filename == '':
        return jsonify({'error': 'No logo file selected'}), 400

    if file and allowed_file(file.filename):
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static/uploads')
        os.makedirs(upload_dir, exist_ok=True)

        filename = f"business_logo_{int(datetime.utcnow().timestamp())}_{file.filename}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        setting = get_company_filtered_settings(
            category='general',
            key='logo_path'
        ).first()

        if setting:
            setting.setting_value = f'/static/uploads/{filename}'
            setting.updated_at = datetime.utcnow()
        else:
            company_id = get_company_id()
            setting = Setting(
                setting_category='general',
                setting_key='logo_path',
                setting_value=f'/static/uploads/{filename}',
                company_id=company_id
            )
            db.session.add(setting)

        db.session.commit()

        return jsonify({
            'success': True,
            'logo_path': f'/static/uploads/{filename}',
            'message': 'Logo uploaded successfully'
        })

    return jsonify({'error': 'Invalid file type'}), 400

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@settings_bp.route('/api/profile/upload-picture', methods=['POST'])
@csrf.exempt
@login_required
def upload_profile_picture():
    """Upload profile picture for the current user."""
    from app.utils.file_manager import FileManager
    
    if 'profile_picture' not in request.files:
        return jsonify({'error': 'No profile picture file provided'}), 400

    file = request.files['profile_picture']
    if file.filename == '':
        return jsonify({'error': 'No profile picture file selected'}), 400

    try:
        # Get rotation angle (if provided)
        rotation = request.form.get('rotation', 0)
        
        # Validate and save the profile picture (auto-crop to 500x500)
        file_path = FileManager.save_profile_picture(file, rotation)
        
        # Delete old profile picture if exists
        if current_user.profile_picture:
            old_file_path = os.path.join(os.path.dirname(current_app.root_path), 'uploads', current_user.profile_picture.replace('uploads/', ''))
            FileManager.delete_file(old_file_path)
        
        # Update user with new profile picture path
        current_user.profile_picture = file_path
        db.session.commit()
        
        return jsonify({
            'success': True,
            'profile_picture': f'/{file_path}',
            'message': 'Profile picture uploaded successfully (500×500px)'
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f"Profile picture upload failed: {e}")
        return jsonify({'error': 'An error occurred while uploading the profile picture'}), 500

@settings_bp.route('/api/profile/delete-picture', methods=['POST'])
@csrf.exempt
@login_required
def delete_profile_picture():
    """Delete profile picture for the current user."""
    from app.utils.file_manager import FileManager
    
    try:
        if current_user.profile_picture:
            # Delete the file from top-level uploads folder
            file_path = os.path.join(os.path.dirname(current_app.root_path), 'uploads', current_user.profile_picture.replace('uploads/', ''))
            FileManager.delete_file(file_path)
            
            # Update user
            current_user.profile_picture = None
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Profile picture deleted successfully'
            })
        else:
            return jsonify({'error': 'No profile picture to delete'}), 400
    except Exception as e:
        current_app.logger.error(f"Profile picture deletion failed: {e}")
        return jsonify({'error': 'An error occurred while deleting the profile picture'}), 500

@settings_bp.route('/api/settings/backup-status', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def backup_status():
    """Check if backup is available and what type."""
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    
    try:
        if db_uri.startswith('sqlite:'):
            # SQLite backup - always available
            return jsonify({
                'available': True,
                'type': 'SQLite',
                'message': 'SQLite backups available',
                'requires_tool': False
            })
        
        elif db_uri.startswith('postgresql:') or db_uri.startswith('postgres:'):
            # PostgreSQL - check if pg_dump is available
            pg_dump_path = find_pg_dump()
            result = subprocess.run(
                [pg_dump_path, '--version'],
                capture_output=True,
                text=True,
                shell=True if os.name == 'nt' else False,
                timeout=5
            )
            
            if result.returncode == 0:
                return jsonify({
                    'available': True,
                    'type': 'PostgreSQL',
                    'message': 'PostgreSQL backups available',
                    'requires_tool': True,
                    'tool_installed': True
                })
            else:
                return jsonify({
                    'available': False,
                    'type': 'PostgreSQL',
                    'message': 'pg_dump utility not installed',
                    'requires_tool': True,
                    'tool_installed': False,
                    'hint': 'Install PostgreSQL client tools or switch to SQLite for easier backups'
                })
        
        else:
            return jsonify({
                'available': False,
                'type': 'Unknown',
                'message': 'Unsupported database type'
            })
    
    except Exception as e:
        current_app.logger.error(f"Backup status check failed: {e}")
        return jsonify({
            'available': False,
            'message': f'Error checking backup status: {str(e)}'
        })

@settings_bp.route('/api/settings/backup', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def create_backup():
    """Create company-scoped database backup (JSON export)."""
    # Get current company
    company_id = get_company_id()
    if not company_id:
        return jsonify({'error': 'Must select a company to backup'}), 400
    
    # Verify user has access to this company
    user_companies = [c.id for c in current_user.companies]
    if company_id not in user_companies and not current_user.is_super_admin():
        return jsonify({'error': 'No permission to backup this company'}), 403
    
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Export company data as JSON
        export_data = export_company_data_to_sql(company_id)
        
        # Save to file with company_id in filename
        backup_filename = f'pos_backup_company_{company_id}_{timestamp}.json'
        backup_path = os.path.join(backup_dir, backup_filename)
        
        with open(backup_path, 'w') as f:
            f.write(export_data)
        
        return jsonify({
            'success': True,
            'message': f'Company backup created: {backup_filename}',
            'filename': backup_filename,
            'company_id': company_id
        })
    
    except Exception as e:
        current_app.logger.error(f"Backup failed: {e}")
        return jsonify({'error': str(e)}), 500


@settings_bp.route('/api/settings/backups', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def get_backups():
    """Get backups for current company only."""
    company_id = get_company_id()
    if not company_id:
        return jsonify([])
    
    # Verify user has access to this company
    user_companies = [c.id for c in current_user.companies]
    if company_id not in user_companies and not current_user.is_super_admin():
        return jsonify([])
    
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    if not os.path.exists(backup_dir):
        return jsonify([])
    
    backups = []
    try:
        for filename in os.listdir(backup_dir):
            # Only show backups for this company (look for company_id in filename)
            if filename.endswith('.json') and f'company_{company_id}' in filename:
                filepath = os.path.join(backup_dir, filename)
                stats = os.stat(filepath)
                backups.append({
                    'filename': filename,
                    'type': 'Company Backup',
                    'created_at': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'size': f"{stats.st_size / 1024:.2f} KB" if stats.st_size < 1024*1024 else f"{stats.st_size / 1024 / 1024:.2f} MB",
                    'company_id': company_id
                })
    except Exception as e:
        current_app.logger.error(f"Error listing backups: {e}")
        return jsonify([])
    
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify(backups)

def _import_json_backup(company_id, file, user_companies):
    """Helper function to import JSON backup file."""
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Save uploaded file
        backup_filename = f'pos_backup_company_{company_id}_imported_{timestamp}.json'
        backup_path = os.path.join(backup_dir, backup_filename)
        file.save(backup_path)
        
        # Read backup file
        with open(backup_path, 'r') as f:
            backup_data = f.read()
        
        # Validate backup is for this company
        backup_json = json.loads(backup_data)
        if backup_json.get('company_id') != company_id:
            os.remove(backup_path)  # Clean up invalid backup
            return jsonify({
                'error': f'Backup is for company {backup_json.get("company_id")}, not company {company_id}',
                'hint': 'Backups are company-specific and cannot be imported to different companies'
            }), 400
        
        # Create auto-backup of current data
        auto_backup_data = export_company_data_to_sql(company_id)
        auto_backup_filename = f'pre_restore_company_{company_id}_{timestamp}.json'
        auto_backup_path = os.path.join(backup_dir, auto_backup_filename)
        with open(auto_backup_path, 'w') as f:
            f.write(auto_backup_data)
        
        # Import backup data
        result = import_company_data_from_sql(company_id, backup_data)
        
        # Dispose connection pool
        db.engine.dispose()
        
        return jsonify({
            'success': True,
            'message': f'Backup imported successfully. Cleared {sum(result.get("deleted_records", {}).values())} old records and imported {result["records_imported"]} records from {result["tables_imported"]} tables.',
            'details': result
        })
    
    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f"Import backup failed: {error_msg}")
        
        # Cleanup invalid file
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
        except:
            pass
        
        return jsonify({
            'error': f'Backup import failed: {error_msg}',
            'hint': 'Ensure the backup file is from the same company and in valid format'
        }), 500

@settings_bp.route('/api/settings/import-backup', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def import_backup():
    """Import and restore a company-scoped backup file uploaded by user."""
    # Get current company
    company_id = get_company_id()
    if not company_id:
        return jsonify({'error': 'Must select a company to import backup into'}), 400
    
    # Verify user has access to this company
    user_companies = [c.id for c in current_user.companies]
    if company_id not in user_companies and not current_user.is_super_admin():
        return jsonify({'error': 'No permission to import to this company'}), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file extension - support both new JSON and old DB/SQL formats
    file_ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    
    if file_ext == 'json':
        # New company-scoped JSON backup format
        return _import_json_backup(company_id, file, user_companies)
    
    elif file_ext in ('db', 'sql'):
        # Old full-database backup format - requires special handling
        current_app.logger.warning(f"Attempting to import legacy backup format: {file.filename}")
        return jsonify({
            'error': 'Legacy backup format detected (.db or .sql)',
            'format': 'old',
            'hint': 'Legacy backups were full-database exports. For company-specific backups, export from the current system as JSON format. Contact admin for legacy backup conversion assistance.',
            'note': 'The new backup system uses JSON format for company-specific data protection. Old backups cannot be reliably imported due to company_id field changes.'
        }), 400
    
    else:
        return jsonify({'error': f'Invalid file type: .{file_ext}. Supported formats: .json (new), .db/.sql (legacy)'}), 400

@settings_bp.route('/api/settings/restore/<filename>', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def restore_backup(filename):
    """Restore company data from backup file (company-scoped)."""
    filename = os.path.basename(filename)
    
    # Get current company
    company_id = get_company_id()
    if not company_id:
        return jsonify({'error': 'Must select a company to restore to'}), 400
    
    # Verify user has access to this company
    user_companies = [c.id for c in current_user.companies]
    if company_id not in user_companies and not current_user.is_super_admin():
        return jsonify({'error': 'No permission to restore to this company'}), 403
    
    # Verify backup file exists and belongs to this company
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    if not os.path.exists(backup_path):
        return jsonify({'error': 'Backup file not found'}), 404
    
    # Verify filename contains company_id (security check)
    if f'company_{company_id}' not in filename:
        return jsonify({
            'error': 'Backup belongs to a different company',
            'hint': 'Backups can only be restored to the same company'
        }), 403
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Validate backup file format and content
        if not filename.endswith('.json'):
            return jsonify({'error': 'Invalid backup format. Only .json backups are supported'}), 400
        
        # Read backup file
        with open(backup_path, 'r') as f:
            backup_data = f.read()
        
        # Validate company_id in backup
        backup_json = json.loads(backup_data)
        if backup_json.get('company_id') != company_id:
            return jsonify({
                'error': 'Backup company ID mismatch',
                'hint': 'Backup belongs to a different company'
            }), 403
        
        # Create auto-backup of current data
        current_app.logger.info(f"Creating auto-backup before restore for company {company_id}")
        auto_backup_data = export_company_data_to_sql(company_id)
        auto_backup_filename = f'pre_restore_company_{company_id}_{timestamp}.json'
        auto_backup_path = os.path.join(backup_dir, auto_backup_filename)
        with open(auto_backup_path, 'w') as f:
            f.write(auto_backup_data)
        current_app.logger.info(f"Auto-backup created: {auto_backup_filename}")
        
        # Restore from backup
        current_app.logger.info(f"Restoring backup for company {company_id}")
        result = import_company_data_from_sql(company_id, backup_data)
        
        # Dispose connection pool
        db.engine.dispose()
        
        return jsonify({
            'success': True,
            'message': f'Backup restored successfully. Cleared {sum(result.get("deleted_records", {}).values())} old records and imported {result["records_imported"]} records from {result["tables_imported"]} tables.',
            'details': result,
            'auto_backup': auto_backup_filename
        })
    
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid backup file format. File is corrupted or not a valid backup'}), 400
    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f"Restore failed for company {company_id}: {error_msg}")
        return jsonify({'error': f'Restore failed: {error_msg}'}), 500

def find_psql():
    """Find psql executable for PostgreSQL."""
    if os.name == 'nt':  # Windows
        possible_paths = [
            r'C:\Program Files\PostgreSQL\17\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\18\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\16\bin\psql.exe',
            r'C:\Program Files\PostgreSQL\15\bin\psql.exe',
            r'C:\Program Files (x86)\PostgreSQL\17\bin\psql.exe',
            r'C:\Program Files (x86)\PostgreSQL\18\bin\psql.exe',
            r'C:\Program Files (x86)\PostgreSQL\16\bin\psql.exe',
            r'C:\Program Files (x86)\PostgreSQL\15\bin\psql.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    return 'psql'

def find_pg_restore():
    """Find pg_restore executable for PostgreSQL."""
    if os.name == 'nt':  # Windows
        possible_paths = [
            r'C:\Program Files\PostgreSQL\17\bin\pg_restore.exe',
            r'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe',
            r'C:\Program Files\PostgreSQL\16\bin\pg_restore.exe',
            r'C:\Program Files\PostgreSQL\15\bin\pg_restore.exe',
            r'C:\Program Files (x86)\PostgreSQL\17\bin\pg_restore.exe',
            r'C:\Program Files (x86)\PostgreSQL\18\bin\pg_restore.exe',
            r'C:\Program Files (x86)\PostgreSQL\16\bin\pg_restore.exe',
            r'C:\Program Files (x86)\PostgreSQL\15\bin\pg_restore.exe',
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
    return 'pg_restore'

@settings_bp.route('/api/settings/backups/<filename>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def delete_backup(filename):
    """Delete a backup file (company-scoped)."""
    filename = os.path.basename(filename)
    
    # Get current company
    company_id = get_company_id()
    if not company_id:
        return jsonify({'error': 'Must select a company'}), 400
    
    # Verify user has access to this company
    user_companies = [c.id for c in current_user.companies]
    if company_id not in user_companies and not current_user.is_super_admin():
        return jsonify({'error': 'No permission'}), 403
    
    # Verify backup belongs to this company
    if f'company_{company_id}' not in filename:
        return jsonify({'error': 'Cannot delete backup from another company'}), 403
    
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    if os.path.exists(backup_path):
        try:
            os.remove(backup_path)
            current_app.logger.info(f"Deleted backup: {filename} for company {company_id}")
            return jsonify({'success': True, 'message': 'Backup deleted successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Backup not found'}), 404

@settings_bp.route('/api/settings/download-backup/<filename>', methods=['GET'])
@login_required
@require_permission('can_access_settings')
def download_backup(filename):
    """Download a backup file (company-scoped)."""
    filename = os.path.basename(filename)
    
    # Get current company
    company_id = get_company_id()
    if not company_id:
        return jsonify({'error': 'Must select a company'}), 400
    
    # Verify user has access to this company
    user_companies = [c.id for c in current_user.companies]
    if company_id not in user_companies and not current_user.is_super_admin():
        return jsonify({'error': 'No permission'}), 403
    
    # Verify backup belongs to this company
    if f'company_{company_id}' not in filename:
        return jsonify({'error': 'Cannot download backup from another company'}), 403
    
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    # Validate file exists and is a JSON backup file
    if not os.path.exists(backup_path) or not filename.endswith('.json'):
        return jsonify({'error': 'Backup not found'}), 404
    
    try:
        current_app.logger.info(f"Downloaded backup: {filename} for company {company_id}")
        return send_file(backup_path, as_attachment=True, download_name=filename)
    except Exception as e:
        current_app.logger.error(f"Error downloading backup: {e}")
        return jsonify({'error': str(e)}), 500

def validate_single_company_assignment(user, num_companies):
    """
    Validate that non-Super Admin users are assigned to exactly ONE company.
    Super Admin users can have multiple companies or none.
    
    Returns tuple: (is_valid, error_message)
    """
    # Super Admin can have any number of companies
    if user.role and user.role.lower() == 'super admin':
        return (True, None)
    
    # Regular users must be in exactly ONE company
    if num_companies != 1:
        return (False, "Non-admin users must be assigned to exactly ONE company. Current: {}".format(num_companies))
    
    return (True, None)

    return (True, None)

@settings_bp.route('/api/settings/users', methods=['GET'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def get_users():
    """Get users (excluding ALL super admin users - they are hidden from management)."""
    # SECURITY: Super admin users are NEVER shown in user management interface
    # This ensures admins cannot see, edit, or delete super admin accounts
    
    # Get all users EXCEPT super admins
    users = User.query.filter(User.role != 'Super Admin').all()
    
    result = []
    for user in users:
        result.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None,
            'permissions': {
                # Sales permissions
                'can_access_sales': user.can_access_sales,
                'can_access_cheques': user.can_access_cheques,
                'can_manage_customer_payments': user.can_manage_customer_payments,
                # Purchases permissions
                'can_access_purchases': user.can_access_purchases,
                'can_access_suppliers': user.can_access_suppliers,
                # Returns permissions
                'can_manage_returns': user.can_manage_returns,
                'can_manage_purchase_returns': user.can_manage_purchase_returns,
                # Inventory permissions
                'can_view_inventory': user.can_view_inventory,
                'can_edit_inventory': user.can_edit_inventory,
                'can_access_warehouse': user.can_access_warehouse,
                # Customers permissions
                'can_access_customers': user.can_access_customers,
                'can_view_sales_history': user.can_view_sales_history,
                'can_view_reports': user.can_view_reports,
                'can_view_profit': user.can_view_profit,
                # Reports permissions (already covered above)
                # Settings permissions
                'can_view_general_settings': user.can_view_general_settings,
                'can_view_receipt_settings': user.can_view_receipt_settings,
                'can_view_terminal_settings': user.can_view_terminal_settings,
                'can_view_backup_settings': user.can_view_backup_settings,
                'can_view_hardware_settings': user.can_view_hardware_settings,
                # System permissions
                'can_access_scale': user.can_access_scale,
                # Other permissions
                'can_access_expenses': user.can_access_expenses,
                'can_access_quotations': user.can_access_quotations,
                'can_access_messages': user.can_access_messages,
                'can_access_audit_logs': user.can_access_audit_logs,
                'can_access_settings': user.can_access_settings,
                'can_view_own_profile': user.can_view_own_profile
            }
        })
    return jsonify(result)

@settings_bp.route('/api/settings/users', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def create_user():
    """Create a new user (admin only)."""
    # SECURITY: Only admins and super admins can create users
    if not current_user.role or current_user.role.lower() not in ['admin', 'super admin']:
        return jsonify({'error': 'Only admins can create users'}), 403
    
    data = request.get_json()

    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password are required'}), 400

    if len(data.get('password', '')) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Username already exists'}), 400

    email = data.get('email')
    if email:
        email = str(email).strip()
        if not email:
            email = None
        elif User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
    else:
        email = None

    try:
        role_input = data.get('role') 
        role = 'Cashier'
        if role_input:
            role_str = str(role_input).strip().lower()
            if role_str == 'admin':
                role = 'Admin'
            elif role_str == 'manager':
                role = 'Manager'
            # SECURITY: Never allow setting role to Super Admin through API
            elif role_str == 'super admin':
                return jsonify({'error': 'Super Admin role cannot be assigned through this interface'}), 403

        user = User(
            username=data['username'],
            email=email,
            role=role
        )
        user.set_password(data['password'])

        # Assign current company to user (unless Super Admin)
        try:
            current_company_id = get_company_id()
            if current_company_id:
                company = Company.query.get(current_company_id)
                if company:
                    user.companies.append(company)
                    # Validate single-company assignment
                    is_valid, error_msg = validate_single_company_assignment(user, len(user.companies))
                    if not is_valid:
                        db.session.rollback()
                        return jsonify({'error': error_msg}), 400
        except Exception as company_error:
            # If company assignment fails, continue anyway - user can work without company assignment
            current_app.logger.warning(f"Failed to assign company to user: {str(company_error)}")
            pass

        if user.role == 'Admin' or user.role == 'Super Admin':
            user.can_access_sales = True
            user.can_access_purchases = True
            user.can_access_suppliers = True
            user.can_view_inventory = True
            user.can_edit_inventory = True
            user.can_view_sales_history = True
            user.can_view_reports = True
            user.can_access_expenses = True
            user.can_access_customers = True
            user.can_view_profit = True
            user.can_access_settings = True
            user.can_access_warehouse = True
        elif user.role == 'Manager':
            user.can_access_sales = True
            user.can_access_purchases = True
            user.can_access_suppliers = True
            user.can_view_inventory = True
            user.can_edit_inventory = True
            user.can_view_sales_history = True
            user.can_view_reports = True
            user.can_access_expenses = True
            user.can_access_customers = True
            user.can_view_profit = True
            user.can_access_settings = False
            user.can_access_warehouse = True
        else:
            user.can_access_sales = True
            user.can_access_customers = True
            user.can_view_inventory = True

        if 'permissions' in data and isinstance(data['permissions'], dict):
            for perm, value in data['permissions'].items():
                if hasattr(user, perm):
                    setattr(user, perm, bool(value))

        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User created successfully', 'user_id': user.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/users/<int:user_id>', methods=['PUT'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def update_user(user_id):
    """Update a user (admin only)."""
    # SECURITY: Only admins and super admins can modify users
    if not current_user.role or current_user.role.lower() not in ['admin', 'super admin']:
        return jsonify({'error': 'Only admins can modify users'}), 403
    
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    # SECURITY: Prevent regular admins from modifying super admin users
    if user.role and user.role.lower() == 'super admin' and current_user.role.lower() != 'super admin':
        return jsonify({'error': 'Super admin users cannot be modified by regular admins'}), 403

    try:
        if 'username' in data and data['username'] != user.username:
            if User.query.filter_by(username=data['username']).first():
                return jsonify({'error': 'Username already exists'}), 400
            user.username = data['username']
            
        if 'email' in data:
            email = data['email']
            if email:
                email = str(email).strip()
                if not email:
                    email = None
                else:
                    existing = User.query.filter_by(email=email).first()
                    if existing and existing.id != user_id:
                        return jsonify({'error': 'Email already exists'}), 400
            else:
                email = None
            user.email = email
            
        if 'role' in data and data.get('role') != user.role:
            role_input = data.get('role')
            if role_input:
                role_str = str(role_input).strip().lower()
                # SECURITY: Prevent role change to Super Admin
                if role_str == 'super admin':
                    return jsonify({'error': 'Super Admin role cannot be assigned through this interface'}), 403
                if role_str:
                    new_role = 'Cashier'
                    if role_str == 'admin': new_role = 'Admin'
                    elif role_str == 'manager': new_role = 'Manager'
                    user.role = new_role

        if 'permissions' in data and isinstance(data['permissions'], dict):
            permissions = data['permissions']
            for perm, value in permissions.items():
                if hasattr(user, perm):
                    if user.role in ['Admin', 'admin', 'ADMIN', 'Super Admin', 'super admin'] and perm == 'can_access_settings' and value == False:
                        continue
                    setattr(user, perm, bool(value))

        db.session.commit()
        return jsonify({'success': True, 'message': 'User updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/users/<int:user_id>/assign-company', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def assign_user_to_company(user_id):
    """Assign a user to a company. Non-super-admin users can only be in ONE company."""
    # SECURITY: Only admins and super admins can assign users to companies
    if not current_user.role or current_user.role.lower() not in ['admin', 'super admin']:
        return jsonify({'error': 'Only admins can assign users to companies'}), 403
    
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    
    if not data or 'company_id' not in data:
        return jsonify({'error': 'company_id is required'}), 400
    
    try:
        from app.models import Company
        company = Company.query.get(data['company_id'])
        if not company:
            return jsonify({'error': 'Company not found'}), 404
        
        # For non-super-admin users, check if they're already in another company
        if not user.is_super_admin():
            # Check if user already in another active company
            other_companies = [c for c in user.companies if c.is_active and c.id != company.id]
            if other_companies:
                return jsonify({
                    'error': 'User is already assigned to another company. Non-admin users must be in exactly ONE company.',
                    'current_company_id': other_companies[0].id,
                    'current_company_name': other_companies[0].name
                }), 400
        
        # Add user to company if not already there
        if company not in user.companies:
            user.companies.append(company)
            db.session.commit()
            return jsonify({'success': True, 'message': 'User assigned to company successfully'})
        else:
            return jsonify({'success': True, 'message': 'User is already assigned to this company'})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("Error assigning user to company: {}".format(str(e)))
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/users/<int:user_id>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def delete_user(user_id):
    """Delete a user (admin only)."""
    # SECURITY: Only admins and super admins can delete users
    if not current_user.role or current_user.role.lower() not in ['admin', 'super admin']:
        return jsonify({'error': 'Only admins can delete users'}), 403
    
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400

    user = User.query.get_or_404(user_id)
    
    # SECURITY: Prevent deletion of admin and super admin accounts
    if user.role and user.role.lower() in ['admin', 'super admin']:
        return jsonify({'error': 'Cannot delete admin accounts'}), 403

    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/users/<int:user_id>/password', methods=['PUT'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def change_user_password(user_id):
    """Change user password (admin only)."""
    # SECURITY: Only admins and super admins can change other users' passwords
    if not current_user.role or current_user.role.lower() not in ['admin', 'super admin']:
        return jsonify({'error': 'Only admins can change passwords'}), 403
    
    user = User.query.get_or_404(user_id)
    
    # SECURITY: Prevent changing admin and super admin passwords through API
    if user.role and user.role.lower() in ['admin', 'super admin'] and user.id != current_user.id:
        return jsonify({'error': 'Cannot change other admin passwords'}), 403
    
    data = request.get_json()

    if not data or 'password' not in data:
        return jsonify({'error': 'New password required'}), 400

    if len(data['password']) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    try:
        user.set_password(data['password'])
        db.session.commit()
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/reset', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def reset_system():
    """Reset the current company data only - Admin only"""
    import traceback
    import sys
    
    try:
        current_app.logger.info("[RESET] Reset endpoint called")
        current_app.logger.debug(f"[RESET] User: {current_user.username if hasattr(current_user, 'username') else 'N/A'}")
        
        # Check admin/super admin role first
        is_admin = False
        if hasattr(current_user, 'role') and current_user.role:
            is_admin = current_user.role.lower() in ['admin', 'super admin']
        
        if not is_admin:
            current_app.logger.warning("[RESET] Non-admin attempted system reset")
            return jsonify({'error': 'Only administrators can reset the system.'}), 403
        
        # Get company ID
        company_id = get_company_id()
        
        # Fallback: if no company_id in session, try to get from user's companies
        if not company_id and hasattr(current_user, 'companies') and current_user.companies:
            company_id = current_user.companies[0].id
        
        if not company_id:
            return jsonify({'error': 'No company selected for reset'}), 400
        
        # Now import models and utilities
        try:
            from app.models import (
                Sale, SaleItem, Return, ReturnItem, Exchange, ExchangeItem,
                Product, Customer, Supplier, Expense, Purchase, PurchaseItem,
                PurchaseReturn, PurchaseReturnItem, InventoryTransaction, 
                Promotion, CustomerFeedback, HeldBill, Setting, Warehouse,
                SerialNumber, PurchaseOrder, PurchaseOrderItem, Cheque, ChequeDeposit,
                AuditLog, CustomerPayment, Company, User
            )
            from sqlalchemy import or_ as sql_or
            current_app.logger.debug("[RESET] Models imported successfully")
        except Exception as import_error:
            current_app.logger.error(f"[RESET] ERROR importing models: {import_error}")
            raise
        
        # Delete all transactional data FOR CURRENT COMPANY ONLY
        # in correct order to avoid FK violations
        
        # Get all Sales IDs for this company
        company_sales_ids = db.session.query(Sale.id).filter(
            Sale.company_id == company_id
        ).all()
        sales_ids = [s[0] for s in company_sales_ids]
        current_app.logger.debug(f"[RESET] Found {len(sales_ids)} Sales to be deleted")
        
        # Get all SaleItems IDs for this company
        company_saleitems_ids = db.session.query(SaleItem.id).filter(
            SaleItem.company_id == company_id
        ).all()
        saleitem_ids = [s[0] for s in company_saleitems_ids]
        current_app.logger.debug(f"[RESET] Found {len(saleitem_ids)} SaleItems to be deleted")
        
        # Now delete in order:
        # 1. ReturnItems referencing our SaleItems
        if saleitem_ids:
            count = db.session.query(ReturnItem).filter(
                ReturnItem.original_sale_item_id.in_(saleitem_ids)
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {count} ReturnItems")
        
        # 2. Returns referencing our Sales or belonging to company
        if sales_ids:
            returns_count = db.session.query(Return).filter(
                sql_or(
                    Return.original_sale_id.in_(sales_ids),
                    Return.company_id == company_id
                )
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {returns_count} Returns")
        
        # 3. Exchanges referencing our Sales or belonging to company
        if sales_ids:
            exchanges_count = db.session.query(Exchange).filter(
                sql_or(
                    Exchange.original_sale_id.in_(sales_ids),
                    Exchange.new_sale_id.in_(sales_ids),
                    Exchange.company_id == company_id
                )
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {exchanges_count} Exchanges")
        
        # 4. Cheques referencing our Sales or belonging to company
        if sales_ids:
            cheques_count = db.session.query(Cheque).filter(
                sql_or(
                    Cheque.sale_id.in_(sales_ids),
                    Cheque.company_id == company_id
                )
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {cheques_count} Cheques")
        
        # 5. ChequeDeposits belonging to company (they don't have sale_id FK)
        deposits_count = db.session.query(ChequeDeposit).filter(
            ChequeDeposit.company_id == company_id
        ).delete(synchronize_session=False)
        db.session.flush()
        current_app.logger.debug(f"[RESET] Deleted {deposits_count} ChequeDeposits")
        
        # Now delete the other tables in order
        tables_to_delete = [
            
            # Exchange items before sales (items belong to exchanges which are already deleted)
            (ExchangeItem, "ExchangeItem"),
            # Sale items before sales
            (SaleItem, "SaleItem"),
            (Sale, "Sale"),
            
            # Purchase items before purchases
            (PurchaseReturnItem, "PurchaseReturnItem"),
            (PurchaseOrderItem, "PurchaseOrderItem"),
            (PurchaseItem, "PurchaseItem"),
            
            # Then parent purchase records
            (PurchaseReturn, "PurchaseReturn"),
            (PurchaseOrder, "PurchaseOrder"),
            (Purchase, "Purchase"),
            
            # Other transactional records
            (InventoryTransaction, "InventoryTransaction"),
            (CustomerFeedback, "CustomerFeedback"),
            (HeldBill, "HeldBill"),
            (Expense, "Expense"),
            (SerialNumber, "SerialNumber"),
            (CustomerPayment, "CustomerPayment"),
            (AuditLog, "AuditLog"),
            
            # Master data last (but not Product - we handle it specially)
            # (Product is handled after orphan cleanup)
            (Customer, "Customer"),
            (Supplier, "Supplier"),
            (Promotion, "Promotion"),
            (Warehouse, "Warehouse"),
        ]
        
        for model_class, table_name in tables_to_delete:
            try:
                print(f"[RESET] Deleting {table_name} for company {company_id}...")
                
                # Filter by company_id if the table has it
                if hasattr(model_class, 'company_id'):
                    query = db.session.query(model_class).filter(
                        model_class.company_id == company_id
                    )
                else:
                    query = db.session.query(model_class)
                
                count = query.delete(synchronize_session=False)
                db.session.flush()
                print(f"[RESET]   Deleted {count} records")
            except Exception as e:
                print(f"[RESET] ERROR deleting {table_name}: {str(e)}")
                raise
        
        # Commit after major delete batches to release connections
        print("[RESET] Releasing connections after first batch of deletions...")
        db.session.commit()
        
        # Special handling for Product - also delete orphaned dependent records
        try:
            current_app.logger.debug(f"[RESET] Deleting Products for company {company_id}")
            
            # Try to delete any orphaned InventoryTransaction/ReturnItem/etc with NULL company_id
            # that might reference this company's products
            
            # Get all product IDs for this company
            company_product_ids = db.session.query(Product.id).filter(
                Product.company_id == company_id
            ).all()
            product_ids = [p[0] for p in company_product_ids]
            
            if product_ids:
                # Delete orphaned inventory transactions
                orphan_inv_count = db.session.query(InventoryTransaction).filter(
                    sql_or(
                        InventoryTransaction.product_id.in_(product_ids),
                        InventoryTransaction.company_id == company_id
                    )
                ).delete(synchronize_session=False)
                db.session.flush()
                current_app.logger.debug(f"[RESET] Cleaned {orphan_inv_count} orphaned inventory transactions")
                
                # Delete orphaned return items
                orphan_ret_items = db.session.query(ReturnItem).filter(
                    sql_or(
                        ReturnItem.product_id.in_(product_ids),
                        ReturnItem.company_id == company_id
                    )
                ).delete(synchronize_session=False)
                db.session.flush()
                current_app.logger.debug(f"[RESET] Cleaned {orphan_ret_items} orphaned return items")
            
            # Now delete products
            products_count = db.session.query(Product).filter(
                Product.company_id == company_id
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {products_count} products")
        except Exception as e:
            current_app.logger.error(f"[RESET] ERROR deleting Product: {str(e)}")
            raise
        
        # Commit to release connections after product deletion
        db.session.commit()
        
        # Delete company-specific settings only
        try:
            Setting.query.filter(
                Setting.company_id == company_id  # Only delete THIS company's settings
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug("[RESET] Settings deleted")
        except Exception as e:
            current_app.logger.warning(f"[RESET] Warning: Error deleting settings: {str(e)}")
            # Continue anyway
        
        # Delete Customer and Supplier data
        try:
            cust_count = Customer.query.filter(
                Customer.company_id == company_id
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {cust_count} customers")
        except Exception as e:
            current_app.logger.error(f"[RESET] ERROR deleting Customer: {str(e)}")
            raise
        
        try:
            supp_count = Supplier.query.filter(
                Supplier.company_id == company_id
            ).delete(synchronize_session=False)
            db.session.flush()
            current_app.logger.debug(f"[RESET] Deleted {supp_count} suppliers")
        except Exception as e:
            current_app.logger.error(f"[RESET] ERROR deleting Supplier: {str(e)}")
            raise
        
        # Commit to release connections after settings and customer/supplier deletion
        db.session.commit()
        
        # Remove from the main deletion list since we handled them above
        # Update tables_to_delete to remove Product, Customer, Supplier if they were there
        
        # Reset the current admin user's permissions to full access
        # BUT keep company association (don't clear companies)
        try:
            admin_user = User.query.get(current_user.id)
            if admin_user:
                admin_user.can_access_sales = True
                admin_user.can_access_purchases = True
                admin_user.can_access_suppliers = True
                admin_user.can_view_inventory = True
                admin_user.can_edit_inventory = True
                admin_user.can_view_sales_history = True
                admin_user.can_view_reports = True
                admin_user.can_access_expenses = True
                admin_user.can_access_customers = True
                admin_user.can_view_profit = True
                admin_user.can_access_settings = True
                admin_user.can_access_warehouse = True
                admin_user.can_access_cheques = True
                admin_user.can_access_quotations = True
                admin_user.can_access_messages = True
                admin_user.can_access_audit_logs = True
                admin_user.can_access_scale = True
                admin_user.can_manage_returns = True
                admin_user.can_manage_purchase_returns = True
                admin_user.can_manage_customer_payments = True
                db.session.flush()
                current_app.logger.debug("[RESET] Admin user permissions reset successfully")
        except Exception as e:
            current_app.logger.warning(f"[RESET] Warning: Error resetting admin user: {str(e)}")
            # Continue anyway - admin permissions are not critical to reset
        
        db.session.commit()
        
        # Dispose of all connections in the pool to prevent holding connections
        db.engine.dispose()
        
        current_app.logger.info("[RESET] System reset completed successfully!")
        return jsonify({
            'success': True, 
            'message': f'Company {company_id} data reset successfully. All transactional data has been cleared.'
        })
    except Exception as e:
        current_app.logger.error(f"[RESET] EXCEPTION: {type(e).__name__} - {str(e)}")
        current_app.logger.error(f"[RESET] Traceback: {traceback.format_exc()}")
        
        db.session.rollback()
        
        try:
            current_app.logger.error(f"System reset failed: {error_msg}")
        except:
            pass  # Logging might fail, that's ok
        
        # Return error with details for debugging
        return jsonify({
            'error': f'System reset failed: {str(e)}',
            'type': type(e).__name__,
            'details': error_msg if current_app.debug else 'Check server logs'
        }), 500

@settings_bp.route('/sales/api/settings/tax-rate', methods=['GET'])
@login_required
def get_tax_rate():
    """Get tax rate and tax settings for current company (for sales page)."""
    company_id = get_company_id()
    try:
        tax_rate_setting = Setting.query.filter(
            Setting.company_id == company_id,
            Setting.setting_category == 'tax',
            Setting.setting_key == 'rate'
        ).first()
        
        enable_tax_setting = Setting.query.filter(
            Setting.company_id == company_id,
            Setting.setting_category == 'tax',
            Setting.setting_key == 'enable_tax'
        ).first()
        
        show_tax_setting = Setting.query.filter(
            Setting.company_id == company_id,
            Setting.setting_category == 'tax',
            Setting.setting_key == 'show_tax_in_sales'
        ).first()
        
        tax_rate = float(tax_rate_setting.setting_value) if tax_rate_setting else 18.0
        enable_tax = enable_tax_setting.setting_value == 'true' if enable_tax_setting else True
        show_tax_in_sales = show_tax_setting.setting_value == 'true' if show_tax_setting else True
        
        return jsonify({
            'success': True,
            'tax_rate': tax_rate,
            'enable_tax': enable_tax,
            'show_tax_in_sales': show_tax_in_sales
        })
    except Exception as e:
        current_app.logger.error(f"Error getting tax rate: {str(e)}")
        return jsonify({
            'success': False,
            'tax_rate': 18.0,
            'enable_tax': True,
            'show_tax_in_sales': True
        })

@settings_bp.route('/sales/api/settings/loyalty-points', methods=['GET'])
@login_required
def get_loyalty_points_settings():
    """Get loyalty points settings for current company (for sales page)."""
    company_id = get_company_id()
    try:
        enable_loyalty_setting = Setting.query.filter(
            Setting.company_id == company_id,
            Setting.setting_category == 'general',
            Setting.setting_key == 'enable_loyalty_points'
        ).first()
        
        conversion_rate_setting = Setting.query.filter(
            Setting.company_id == company_id,
            Setting.setting_category == 'general',
            Setting.setting_key == 'loyalty_points_conversion_rate'
        ).first()
        
        enable_loyalty_points = enable_loyalty_setting.setting_value == 'true' if enable_loyalty_setting else True
        conversion_rate = float(conversion_rate_setting.setting_value) if conversion_rate_setting else 1.0
        
        return jsonify({
            'success': True,
            'enable_loyalty_points': enable_loyalty_points,
            'loyalty_points_conversion_rate': conversion_rate
        })
    except Exception as e:
        current_app.logger.error(f"Error getting loyalty points settings: {str(e)}")
        return jsonify({
            'success': False,
            'enable_loyalty_points': True,
            'loyalty_points_conversion_rate': 1.0
        })