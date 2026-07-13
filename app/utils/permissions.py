from functools import wraps
from flask import flash, redirect, url_for, abort, request, jsonify
from flask_login import current_user

def require_permission(permission):
    """Decorator to require specific permission for a route."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if this is an API request (by path or Accept header)
            is_api_request = (request.headers.get('Accept') == 'application/json' or 
                             '/api/' in request.path or
                             (request.blueprint and 'api' in request.blueprint))
            
            if not current_user.is_authenticated:
                if is_api_request:
                    return jsonify({'error': 'Session expired. Please log in again.', 'code': 'SESSION_EXPIRED'}), 401
                return redirect(url_for('auth.login'))

            # Admins and super admins automatically have access to everything
            if current_user.role and current_user.role.lower() in ['admin', 'super admin']:
                return f(*args, **kwargs)

            # For non-admins, check specific permission
            if not hasattr(current_user, permission) or not getattr(current_user, permission, False):
                if is_api_request:
                    return jsonify({'error': 'Permission denied'}), 403
                flash(f'You do not have permission to access this feature.', 'danger')
                return redirect(url_for('main.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_any_settings_permission():
    """Decorator to require at least one settings permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.headers.get('Accept') == 'application/json' or request.blueprint and 'api' in request.blueprint.lower():
                    return jsonify({'error': 'Session expired. Please log in again.', 'code': 'SESSION_EXPIRED'}), 401
                return redirect(url_for('auth.login'))

            # Admins and super admins automatically have access to everything
            if current_user.role and current_user.role.lower() in ['admin', 'super admin']:
                return f(*args, **kwargs)

            # For non-admins, check if they have any granular settings permission
            if not has_any_settings_permission():
                if request.headers.get('Accept') == 'application/json' or request.blueprint and 'api' in request.blueprint.lower():
                    return jsonify({'error': 'Permission denied'}), 403
                flash(f'You do not have permission to access this feature.', 'danger')
                return redirect(url_for('main.dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def has_permission(permission):
    """Check if current user has a specific permission."""
    if not current_user.is_authenticated:
        return False
    
    # Admins and super admins always have all permissions
    if current_user.role and current_user.role.lower() in ['admin', 'super admin']:
        return True
    
    return getattr(current_user, permission, False)

def has_any_settings_permission():
    """Check if user has any of the granular settings permissions."""
    if not current_user.is_authenticated:
        return False
    
    # Admins and super admins always have all permissions
    if current_user.role and current_user.role.lower() in ['admin', 'super admin']:
        return True
    
    settings_permissions = [
        'can_view_general_settings',
        'can_view_receipt_settings',
        'can_view_terminal_settings',
        'can_view_backup_settings',
        'can_view_hardware_settings'
    ]
    
    for perm in settings_permissions:
        if getattr(current_user, perm, False):
            return True
    
    return False

def get_user_permissions():
    """Get all permissions for the current user."""
    if not current_user.is_authenticated:
        return {}

    permissions = {}
    permission_fields = [
        'can_access_sales', 'can_access_purchases', 'can_access_suppliers',
        'can_view_inventory', 'can_edit_inventory', 'can_view_sales_history',
        'can_view_reports', 'can_access_expenses', 'can_access_customers',
        'can_view_profit', 'can_access_settings', 'can_access_cheques',
        'can_access_quotations', 'can_access_messages', 'can_access_audit_logs',
        'can_access_scale', 'can_manage_returns', 'can_manage_purchase_returns',
        'can_manage_customer_payments', 'can_access_warehouse',
        'can_view_general_settings', 'can_view_receipt_settings', 
        'can_view_terminal_settings', 'can_view_backup_settings', 
        'can_view_hardware_settings', 'can_view_own_profile'
    ]

    for perm in permission_fields:
        # Admins and super admins always have all permissions
        if current_user.role and current_user.role.lower() in ['admin', 'super admin']:
            permissions[perm] = True
        else:
            permissions[perm] = getattr(current_user, perm, False)

    return permissions
