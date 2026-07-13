from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, send_file
from flask_login import login_required, current_user
from app.models import db, Setting, User
from app.utils.permissions import require_permission, require_any_settings_permission
from app.utils.audit import log_create, log_update, log_delete, get_entity_changes
from datetime import datetime
import os
import shutil
import subprocess
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

@settings_bp.route('/settings')
@login_required
@require_any_settings_permission()
def settings():
    return render_template('settings/settings.html')

@settings_bp.route('/profile')
@login_required
def profile():
    """Profile page accessible to all logged-in users."""
    return render_template('settings/profile.html')

@settings_bp.route('/api/settings', methods=['GET'])
@csrf.exempt
@login_required
@require_any_settings_permission()
def getSettings():
    from app.utils.security import get_company_id
    
    company_id = get_company_id()
    
    # Filter settings by company
    query = Setting.query
    if company_id:
        query = query.filter(Setting.company_id == company_id)
    
    settings = query.all()
    settings_by_category = {}
    for setting in settings:
        category = setting.setting_category
        if category not in settings_by_category:
            settings_by_category[category] = {}
        settings_by_category[category][setting.setting_key] = setting.setting_value
    return jsonify(settings_by_category)

@settings_bp.route('/api/currency-symbol', methods=['GET'])
@csrf.exempt
def get_currency_symbol():
    """Public endpoint to get currency symbol (no auth required)"""
    # First check the 'currency' category with 'symbol' key (where form saves it)
    setting = Setting.query.filter_by(
        setting_category='currency',
        setting_key='symbol'
    ).first()
    
    # Fallback to 'general' category with 'currency_symbol' key for legacy compatibility
    if not setting:
        setting = Setting.query.filter_by(
            setting_category='general',
            setting_key='currency_symbol'
        ).first()
    
    if setting:
        return jsonify({'currency_symbol': setting.setting_value})
    return jsonify({'currency_symbol': 'Rs. '})

@settings_bp.route('/api/settings', methods=['POST'])
@csrf.exempt
@login_required
@require_any_settings_permission()
def save_settings():
    from app.utils.security import get_company_id
    
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
                
                # Use no_autoflush to avoid premature flushes
                with db.session.no_autoflush:
                    setting = Setting.query.filter(
                        Setting.setting_category == category,
                        Setting.setting_key == key,
                        Setting.company_id == company_id
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
                            Setting.setting_category == category,
                            Setting.setting_key == key,
                            Setting.company_id == company_id
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
@require_any_settings_permission()
def get_category_settings(category):
    settings = Setting.query.filter_by(setting_category=category).all()
    result = {}
    for setting in settings:
        result[setting.setting_key] = setting.setting_value
    return jsonify(result)

@settings_bp.route('/api/settings/upload-logo', methods=['POST'])
@csrf.exempt
@login_required
@require_any_settings_permission()
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

        setting = Setting.query.filter_by(
            setting_category='general',
            setting_key='logo_path'
        ).first()

        if setting:
            setting.setting_value = f'/static/uploads/{filename}'
            setting.updated_at = datetime.utcnow()
        else:
            setting = Setting(
                setting_category='general',
                setting_key='logo_path',
                setting_value=f'/static/uploads/{filename}'
            )
            db.session.add(setting)

        db.session.commit()

        return jsonify({
            'success': True,
            'logo_path': f'/static/uploads/{filename}',
            'message': 'Logo uploaded successfully'
        })

    return jsonify({'error': 'Invalid file type'}), 400

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

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@settings_bp.route('/api/settings/backup-status', methods=['GET'])
@csrf.exempt
@login_required
@require_any_settings_permission()
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
@require_any_settings_permission()
def create_backup():
    """Create database backup for SQLite or PostgreSQL."""
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        if db_uri.startswith('sqlite:'):
            # SQLite backup
            db_filename = db_uri.split(':///')[-1]
            db_path = os.path.join(current_app.root_path, '..', db_filename)
            
            if not os.path.exists(db_path):
                current_app.logger.error(f"Database file not found at: {db_path}")
                return jsonify({'error': 'Database file not found.'}), 500
            
            backup_filename = f'pos_backup_{timestamp}.db'
            backup_path = os.path.join(backup_dir, backup_filename)
            shutil.copy2(db_path, backup_path)
            
            return jsonify({
                'success': True,
                'message': f'SQLite backup created: {backup_filename}',
                'filename': backup_filename
            })
        
        elif db_uri.startswith('postgresql:') or db_uri.startswith('postgres:'):
            # PostgreSQL backup using pg_dump
            parsed_uri = urlparse(db_uri)
            
            # Extract connection details
            host = parsed_uri.hostname or 'localhost'
            port = parsed_uri.port or 5432
            username = parsed_uri.username or 'postgres'
            password = parsed_uri.password
            database = parsed_uri.path.lstrip('/')
            
            # Create the pg_dump command
            backup_filename = f'pos_backup_{timestamp}.sql'
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Build environment with password if provided
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password
            
            # Find pg_dump executable
            pg_dump_path = find_pg_dump()
            
            # Build pg_dump command
            cmd = [
                pg_dump_path,
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                '--format=plain',  # Plain SQL format
                f'--file={backup_path}',
                database
            ]
            
            try:
                # Execute pg_dump with shell=True on Windows to help find executables
                result = subprocess.run(
                    cmd, 
                    env=env, 
                    capture_output=True, 
                    text=True, 
                    timeout=300,
                    shell=True if os.name == 'nt' else False
                )
                
                if result.returncode != 0:
                    error_msg = result.stderr or 'Unknown error during backup'
                    current_app.logger.error(f"PostgreSQL backup failed: {error_msg}")
                    
                    # Check if pg_dump is not found
                    if 'not found' in error_msg.lower() or 'not recognized' in error_msg.lower():
                        return jsonify({
                            'error': 'pg_dump not found',
                            'hint': 'PostgreSQL tools not installed. Please install PostgreSQL client tools, or use a SQLite database for backups.'
                        }), 500
                    
                    return jsonify({
                        'error': f'Backup failed: {error_msg}',
                        'hint': 'Check database credentials and ensure PostgreSQL is accessible'
                    }), 500
                
                if not os.path.exists(backup_path) or os.path.getsize(backup_path) == 0:
                    return jsonify({'error': 'Backup file was not created or is empty'}), 500
                
                return jsonify({
                    'success': True,
                    'message': f'PostgreSQL backup created: {backup_filename}',
                    'filename': backup_filename
                })
            
            except FileNotFoundError as e:
                current_app.logger.error(f"pg_dump not found: {e}")
                return jsonify({
                    'error': 'pg_dump utility not found',
                    'hint': 'PostgreSQL client tools are not installed. Please install PostgreSQL client tools or use SQLite.'
                }), 500
            except subprocess.TimeoutExpired:
                return jsonify({'error': 'Backup operation timed out (5 minutes)'}), 500
        
        else:
            return jsonify({
                'error': 'Unsupported database type',
                'hint': 'Backup is available for SQLite and PostgreSQL databases'
            }), 400
    
    except Exception as e:
        current_app.logger.error(f"Backup failed: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/backups', methods=['GET'])
@csrf.exempt
@login_required
@require_any_settings_permission()
def get_backups():
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    if not os.path.exists(backup_dir):
        return jsonify([])
    
    backups = []
    try:
        for filename in os.listdir(backup_dir):
            if filename.endswith(('.db', '.sql')):  # Support both SQLite and PostgreSQL backups
                filepath = os.path.join(backup_dir, filename)
                stats = os.stat(filepath)
                backup_type = 'SQLite' if filename.endswith('.db') else 'PostgreSQL'
                backups.append({
                    'filename': filename,
                    'type': backup_type,
                    'created_at': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'size': f"{stats.st_size / 1024 / 1024:.2f} MB" if stats.st_size < 1024*1024*1024 else f"{stats.st_size / 1024 / 1024 / 1024:.2f} GB"
                })
    except Exception as e:
        current_app.logger.error(f"Error listing backups: {e}")
        return jsonify([])
    
    backups.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify(backups)

@settings_bp.route('/api/settings/import-backup', methods=['POST'])
@csrf.exempt
@login_required
@require_any_settings_permission()
def import_backup():
    """Import and restore a backup file uploaded by user."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate file extension
    if not (file.filename.endswith('.db') or file.filename.endswith('.sql')):
        return jsonify({'error': 'Invalid file type. Only .db and .sql files are supported'}), 400
    
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    
    try:
        # Save uploaded file to backups directory with timestamp to avoid conflicts
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_name = os.path.splitext(file.filename)[0]
        file_ext = '.db' if file.filename.endswith('.db') else '.sql'
        backup_filename = f'{original_name}_imported_{timestamp}{file_ext}'
        backup_path = os.path.join(backup_dir, backup_filename)
        
        file.save(backup_path)
        
        # After saving, proceed with restore
        db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
        
        if db_uri.startswith('sqlite:'):
            # SQLite restore
            db_path = db_uri.replace('sqlite:///', '').replace('sqlite:', '')
            if not os.path.exists(backup_path):
                return jsonify({'error': 'Backup file upload failed'}), 500
            
            # Create auto-backup
            auto_backup_dir = os.path.join(current_app.root_path, '..', 'backups')
            auto_backup = os.path.join(auto_backup_dir, f'pre_restore_{timestamp}.db')
            if os.path.exists(db_path):
                shutil.copy2(db_path, auto_backup)
            
            # Restore from backup
            shutil.copy2(backup_path, db_path)
            # Force connection pool to dispose stale connections
            db.engine.dispose()
            return jsonify({
                'success': True,
                'message': f'Backup imported and restored successfully from {file.filename}'
            })
        
        elif db_uri.startswith('postgresql:') or db_uri.startswith('postgres:'):
            # PostgreSQL restore
            parsed_uri = urlparse(db_uri)
            
            host = parsed_uri.hostname or 'localhost'
            port = parsed_uri.port or 5432
            username = parsed_uri.username or 'postgres'
            password = parsed_uri.password
            database = parsed_uri.path.lstrip('/')
            
            # Create auto-backup first
            auto_backup_filename = f'pre_restore_{timestamp}.sql'
            auto_backup_path = os.path.join(backup_dir, auto_backup_filename)
            pg_dump = find_pg_dump()
            if pg_dump:
                try:
                    env = os.environ.copy()
                    if password:
                        env['PGPASSWORD'] = password
                    cmd = f'{pg_dump} -h {host} -p {port} -U {username} {database} > {auto_backup_path}'
                    subprocess.run(cmd, env=env, capture_output=True, timeout=600, shell=True if os.name == 'nt' else False)
                except Exception as e:
                    current_app.logger.warning(f"Auto-backup failed (non-critical): {e}")
            
            # Restore from uploaded backup
            psql = find_psql()
            if not psql:
                return jsonify({'error': 'psql utility not found. PostgreSQL client tools required for restore'}), 500
            
            try:
                env = os.environ.copy()
                if password:
                    env['PGPASSWORD'] = password
                
                with open(backup_path, 'r') as f:
                    restore_sql = f.read()
                
                # Drop existing connections and restore
                cmd = (
                    f"{psql} -h {host} -p {port} -U {username} {database} "
                    f"-c \"SELECT pg_terminate_backend(p.pid) FROM pg_stat_activity p WHERE p.datname = '{database}' AND p.pid != pg_backend_pid();\" && "
                    f"echo '{restore_sql.replace(chr(34), chr(92)+chr(34))}' | {psql} -h {host} -p {port} -U {username} {database}"
                )
                
                result = subprocess.run(cmd, env=env, capture_output=True, timeout=600, shell=True if os.name == 'nt' else False)
                error_msg = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ''
                
                if result.returncode != 0:
                    raise Exception(error_msg or 'Restore command failed')
                
                # Force connection pool to dispose stale connections
                db.engine.dispose()
                return jsonify({
                    'success': True,
                    'message': f'Backup imported and restored successfully from {file.filename}'
                })
                
            except subprocess.TimeoutExpired:
                return jsonify({'error': 'Restore operation timed out (10 minutes)'}), 500
            except Exception as e:
                error_msg = str(e)
                current_app.logger.error(f"Restore failed: {error_msg}")
                
                # Try rollback if auto-backup exists
                if os.path.exists(auto_backup_path):
                    try:
                        env = os.environ.copy()
                        if password:
                            env['PGPASSWORD'] = password
                        with open(auto_backup_path, 'r') as f:
                            rollback_sql = f.read()
                        rollback_cmd = (
                            f"{psql} -h {host} -p {port} -U {username} {database} "
                            f"-c \"SELECT pg_terminate_backend(p.pid) FROM pg_stat_activity p WHERE p.datname = '{database}' AND p.pid != pg_backend_pid();\" && "
                            f"echo '{rollback_sql.replace(chr(34), chr(92)+chr(34))}' | {psql} -h {host} -p {port} -U {username} {database}"
                        )
                        subprocess.run(rollback_cmd, env=env, capture_output=True, timeout=300, shell=True if os.name == 'nt' else False)
                    except:
                        pass
                
                return jsonify({
                    'error': f'Restore failed: {error_msg}',
                    'hint': 'An auto-backup was created before the restore attempt'
                }), 500
        
        else:
            return jsonify({'error': 'Unsupported database type'}), 400
    
    except Exception as e:
        current_app.logger.error(f"Import backup failed: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/restore/<filename>', methods=['POST'])
@csrf.exempt
@login_required
@require_any_settings_permission()
def restore_backup(filename):
    """Restore database from backup file."""
    filename = os.path.basename(filename)
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    if not os.path.exists(backup_path):
        return jsonify({'error': 'Backup file not found'}), 404
    
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        if db_uri.startswith('sqlite:'):
            # SQLite restore - simple file copy
            db_filename = db_uri.split(':///')[-1]
            db_path = os.path.join(current_app.root_path, '..', db_filename)
            
            # Create auto-backup
            auto_backup = os.path.join(backup_dir, f'pre_restore_{timestamp}.db')
            if os.path.exists(db_path):
                shutil.copy2(db_path, auto_backup)
            
            # Restore from backup
            shutil.copy2(backup_path, db_path)
            # Force connection pool to dispose stale connections
            db.engine.dispose()
            return jsonify({
                'success': True,
                'message': 'SQLite database restored successfully. Please restart the application if you encounter issues.'
            })
        
        elif db_uri.startswith('postgresql:') or db_uri.startswith('postgres:'):
            # PostgreSQL restore using psql or pg_restore
            parsed_uri = urlparse(db_uri)
            
            # Extract connection details
            host = parsed_uri.hostname or 'localhost'
            port = parsed_uri.port or 5432
            username = parsed_uri.username or 'postgres'
            password = parsed_uri.password
            database = parsed_uri.path.lstrip('/')
            
            # Find pg_dump for auto-backup
            pg_dump_path = find_pg_dump()
            
            # Create auto-backup first
            auto_backup_path = os.path.join(backup_dir, f'pre_restore_{timestamp}.sql')
            
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password
            
            # Auto-backup current database
            auto_backup_cmd = [
                pg_dump_path,
                f'--host={host}',
                f'--port={port}',
                f'--username={username}',
                '--format=plain',
                f'--file={auto_backup_path}',
                database
            ]
            
            result = subprocess.run(
                auto_backup_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
                shell=True if os.name == 'nt' else False
            )
            
            if result.returncode != 0:
                current_app.logger.error(f"Auto-backup failed: {result.stderr}")
                return jsonify({
                    'error': f'Could not create auto-backup before restore: {result.stderr}'
                }), 500
            
            # Determine if backup is SQL or binary format
            if filename.endswith('.sql'):
                # SQL format - use psql
                psql_path = find_psql()
                
                # Read the backup file and execute via psql
                restore_cmd = [
                    psql_path,
                    f'--host={host}',
                    f'--port={port}',
                    f'--username={username}',
                    f'--dbname={database}',
                    f'--file={backup_path}'
                ]
            else:
                # Binary format - use pg_restore
                pg_restore_path = find_pg_restore()
                
                restore_cmd = [
                    pg_restore_path,
                    f'--host={host}',
                    f'--port={port}',
                    f'--username={username}',
                    f'--dbname={database}',
                    f'--clean',  # Clean database before restore
                    f'--if-exists',  # Don't fail if objects don't exist
                    backup_path
                ]
            
            # Execute restore
            result = subprocess.run(
                restore_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes for restore
                shell=True if os.name == 'nt' else False
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or 'Unknown error during restore'
                current_app.logger.error(f"PostgreSQL restore failed: {error_msg}")
                
                # Attempt rollback
                try:
                    current_app.logger.info(f"Attempting to restore from auto-backup: {auto_backup_path}")
                    rollback_cmd = [
                        psql_path if filename.endswith('.sql') else pg_restore_path,
                        f'--host={host}',
                        f'--port={port}',
                        f'--username={username}',
                        f'--dbname={database}',
                        f'--file={auto_backup_path}' if filename.endswith('.sql') else '',
                        auto_backup_path if not filename.endswith('.sql') else ''
                    ]
                    if not filename.endswith('.sql'):
                        rollback_cmd = [
                            pg_restore_path,
                            f'--host={host}',
                            f'--port={port}',
                            f'--username={username}',
                            f'--dbname={database}',
                            f'--clean',
                            f'--if-exists',
                            auto_backup_path
                        ]
                    subprocess.run(rollback_cmd, env=env, capture_output=True, timeout=300, shell=True if os.name == 'nt' else False)
                except:
                    pass
                
                return jsonify({
                    'error': f'Restore failed: {error_msg}',
                    'hint': 'An auto-backup was created before the restore attempt'
                }), 500
            
            # Force connection pool to dispose stale connections
            db.engine.dispose()
            return jsonify({
                'success': True,
                'message': 'PostgreSQL database restored successfully. Please restart the application if you encounter issues.'
            })
        
        else:
            return jsonify({'error': 'Unsupported database type'}), 400
    
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Restore operation timed out (10 minutes)'}), 500
    except Exception as e:
        current_app.logger.error(f"Restore failed: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/backups/<filename>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_any_settings_permission()
def delete_backup(filename):
    filename = os.path.basename(filename)
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    if os.path.exists(backup_path):
        try:
            os.remove(backup_path)
            return jsonify({'success': True, 'message': 'Backup deleted successfully'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Backup not found'}), 404

@settings_bp.route('/api/settings/download-backup/<filename>', methods=['GET'])
@login_required
@require_any_settings_permission()
def download_backup(filename):
    """Download a backup file."""
    filename = os.path.basename(filename)
    backup_dir = os.path.join(current_app.root_path, '..', 'backups')
    backup_path = os.path.join(backup_dir, filename)
    
    # Validate file exists and is a backup file
    if not os.path.exists(backup_path) or not filename.endswith(('.db', '.sql')):
        return jsonify({'error': 'Backup not found'}), 404
    
    try:
        return send_file(backup_path, as_attachment=True, download_name=filename)
    except Exception as e:
        current_app.logger.error(f"Error downloading backup: {e}")
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/users', methods=['GET'])
@csrf.exempt
@login_required
def get_users():
    users = User.query.all()
    result = []
    for user in users:
        result.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None,
            'permissions': {
                'can_access_sales': user.can_access_sales,
                'can_access_purchases': user.can_access_purchases,
                'can_access_suppliers': user.can_access_suppliers,
                'can_view_inventory': user.can_view_inventory,
                'can_edit_inventory': user.can_edit_inventory,
                'can_view_sales_history': user.can_view_sales_history,
                'can_view_reports': user.can_view_reports,
                'can_access_expenses': user.can_access_expenses,
                'can_access_customers': user.can_access_customers,
                'can_view_profit': user.can_view_profit,
                'can_access_settings': user.can_access_settings,
                'can_access_warehouse': user.can_access_warehouse,
                'can_access_cheques': user.can_access_cheques,
                'can_manage_returns': user.can_manage_returns,
                'can_manage_purchase_returns': user.can_manage_purchase_returns,
                'can_manage_customer_payments': user.can_manage_customer_payments,
                'can_access_quotations': user.can_access_quotations,
                'can_access_messages': user.can_access_messages,
                'can_access_audit_logs': user.can_access_audit_logs,
                'can_access_scale': user.can_access_scale,
                'can_view_general_settings': user.can_view_general_settings,
                'can_view_receipt_settings': user.can_view_receipt_settings,
                'can_view_terminal_settings': user.can_view_terminal_settings,
                'can_view_backup_settings': user.can_view_backup_settings,
                'can_view_hardware_settings': user.can_view_hardware_settings
            }
        })
    return jsonify(result)

@settings_bp.route('/api/settings/users', methods=['POST'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def create_user():
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
            elif role_str == 'super admin':
                role = 'Super Admin'

        user = User(
            username=data['username'],
            email=email,
            role=role
        )
        user.set_password(data['password'])

        if user.role == 'Super Admin':
            # Super Admin gets ALL permissions
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
            user.can_access_cheques = True
            user.can_access_quotations = True
            user.can_access_messages = True
            user.can_access_audit_logs = True
            user.can_access_scale = True
            user.can_manage_returns = True
            user.can_manage_purchase_returns = True
            user.can_manage_customer_payments = True
            user.can_view_general_settings = True
            user.can_view_receipt_settings = True
            user.can_view_terminal_settings = True
            user.can_view_backup_settings = True
            user.can_view_hardware_settings = True
        elif user.role == 'Admin':
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
            user.can_access_cheques = True
            user.can_access_quotations = True
            user.can_access_messages = True
            user.can_access_audit_logs = True
            user.can_access_scale = True
            user.can_manage_returns = True
            user.can_manage_purchase_returns = True
            user.can_manage_customer_payments = True
            user.can_view_general_settings = True
            user.can_view_receipt_settings = True
            user.can_view_terminal_settings = True
            user.can_view_backup_settings = True
            user.can_view_hardware_settings = True
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
            user.can_access_cheques = True
            user.can_manage_returns = True
            user.can_manage_purchase_returns = True
            user.can_manage_customer_payments = True
            user.can_access_scale = True
            user.can_view_general_settings = True
            user.can_view_receipt_settings = True
            user.can_view_terminal_settings = True
            user.can_view_backup_settings = False
            user.can_view_hardware_settings = False
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
        
        # Log the user creation
        log_create(
            entity_type='User',
            entity_id=user.id,
            values={'username': user.username, 'email': user.email, 'role': user.role},
            description=f"User '{user.username}' created with role '{user.role}'"
        )
        
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
    user_role = current_user.role.lower() if current_user.role else None
    if user_role not in ['admin', 'super admin']:
        return jsonify({'error': 'Only admins can modify users'}), 403
    
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        # Capture old values before making changes
        old_username = user.username
        old_email = user.email
        old_role = user.role
        
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
                role_str = str(role_input).strip()
                if role_str:
                    new_role = 'Cashier'
                    if role_str.lower() == 'admin': new_role = 'Admin'
                    elif role_str.lower() == 'manager': new_role = 'Manager'
                    elif role_str.lower() == 'super admin': new_role = 'Super Admin'
                    user.role = new_role

        if 'permissions' in data and isinstance(data['permissions'], dict):
            permissions = data['permissions']
            for perm, value in permissions.items():
                if hasattr(user, perm):
                    if user.role in ['Admin', 'admin', 'ADMIN', 'Super Admin', 'super admin'] and perm == 'can_access_settings' and value == False:
                        continue
                    setattr(user, perm, bool(value))

        db.session.commit()
        
        # Log the user update
        log_update(
            entity_type='User',
            entity_id=user.id,
            old_values={'username': old_username, 'email': old_email, 'role': old_role},
            new_values={'username': user.username, 'email': user.email, 'role': user.role},
            description=f"User '{user.username}' was updated"
        )
        
        return jsonify({'success': True, 'message': 'User updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@settings_bp.route('/api/settings/users/<int:user_id>', methods=['DELETE'])
@csrf.exempt
@login_required
@require_permission('can_access_settings')
def delete_user(user_id):
    """Delete a user (admin only)."""
    # SECURITY: Only admins and super admins can delete users
    user_role = current_user.role.lower() if current_user.role else None
    if user_role not in ['admin', 'super admin']:
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
    user_role = current_user.role.lower() if current_user.role else None
    if user_role not in ['admin', 'super admin']:
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
    """Reset the entire POS system - Admin only"""
    from app.models import (
        Sale, SaleItem, Return, ReturnItem, Exchange, ExchangeItem,
        Product, Customer, Supplier, Expense, Purchase, PurchaseItem,
        PurchaseReturn, PurchaseReturnItem, InventoryTransaction, 
        Promotion, CustomerFeedback, HeldBill, Setting, Warehouse,
        SerialNumber, PurchaseOrder, PurchaseOrderItem
    )
    
    # Extra security check - only Admin or Super Admin role can reset
    if current_user.role not in ['Admin', 'Super Admin']:
        return jsonify({'error': 'Only administrators can reset the system. Your role is: ' + str(current_user.role)}), 403
    
    try:
        # Delete all transactional data (in order to respect foreign keys)
        # First delete child tables that reference parent tables
        
        # Sales related - delete return/exchange items BEFORE sale items
        db.session.query(ReturnItem).delete()
        db.session.query(Return).delete()
        
        db.session.query(ExchangeItem).delete()
        db.session.query(Exchange).delete()
        
        # Now delete sale items and sales
        db.session.query(SaleItem).delete()
        db.session.query(Sale).delete()
        
        # Purchases related - delete return items BEFORE purchase items
        db.session.query(PurchaseReturnItem).delete()
        db.session.query(PurchaseReturn).delete()
        
        db.session.query(PurchaseItem).delete()
        db.session.query(Purchase).delete()
        
        db.session.query(PurchaseOrderItem).delete()
        db.session.query(PurchaseOrder).delete()
        
        db.session.query(InventoryTransaction).delete()
        
        db.session.query(CustomerFeedback).delete()
        
        db.session.query(HeldBill).delete()
        
        db.session.query(Expense).delete()
        
        db.session.query(SerialNumber).delete()
        
        # Delete all products (this will cascade to sale_items, etc.)
        db.session.query(Product).delete()
        
        # Delete all customers
        db.session.query(Customer).delete()
        
        # Delete all suppliers
        db.session.query(Supplier).delete()
        
        # Delete all promotions
        db.session.query(Promotion).delete()
        
        # Delete all warehouses (except we might want to keep this, but for full reset we delete)
        db.session.query(Warehouse).delete()
        
        # Delete all settings
        db.session.query(Setting).delete()
        
        # Delete all users except the current admin user
        User.query.filter(User.id != current_user.id).delete()
        
        # Reset the current admin user's permissions to full access
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
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'System reset completed successfully. All data has been cleared except your admin account.'
        })
    except Exception as e:
        db.session.rollback()
        import traceback
        current_app.logger.error(f"System reset failed: {traceback.format_exc()}")
        return jsonify({'error': 'System reset failed: ' + str(e)}), 500
