"""
Audit utility module for logging changes in the system.
Provides helper functions to track CRUD operations and changes.
"""
import json
from datetime import datetime
from flask_login import current_user
from flask import request, has_request_context
from app.models import db, AuditLog


def get_client_info():
    """Get client IP address and user agent from request."""
    ip_address = None
    user_agent = None
    
    if has_request_context():
        # Get IP address (handle proxies)
        if request.environ.get('HTTP_X_FORWARDED_FOR'):
            ip_address = request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
        elif request.environ.get('REMOTE_ADDR'):
            ip_address = request.environ['REMOTE_ADDR']
        
        user_agent = request.headers.get('User-Agent', '')[:255]
    
    return ip_address, user_agent


def get_current_company_id():
    """Get the current company ID from session or context."""
    from app.utils.company import get_current_company
    if has_request_context() and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        company = get_current_company()
        if company:
            return company.id
    return None


def log_audit(entity_type, entity_id, action, old_values=None, new_values=None, description=None, user_id=None, company_id=None):
    """
    Create an audit log entry.
    
    Args:
        entity_type: Type of entity (e.g., 'User', 'Product', 'Customer')
        entity_id: ID of the entity
        action: Action performed (e.g., 'create', 'update', 'delete', 'login')
        old_values: Dictionary of old values (before change)
        new_values: Dictionary of new values (after change)
        description: Human-readable description of the change
        user_id: ID of user performing the action (defaults to current_user)
        company_id: ID of company (defaults to current company)
    """
    try:
        # Get current user if not specified
        if user_id is None:
            if has_request_context() and hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                user_id = current_user.id
        
        # Get current company if not specified
        if company_id is None:
            company_id = get_current_company_id()
        
        # Get client info
        ip_address, user_agent = get_client_info()
        
        # Convert dict values to JSON strings
        old_values_json = json.dumps(old_values) if old_values else None
        new_values_json = json.dumps(new_values) if new_values else None
        
        # Generate description if not provided
        if not description:
            description = generate_description(entity_type, action, old_values, new_values)
        
        # Create audit log entry
        audit_log = AuditLog(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=old_values_json,
            new_values=new_values_json,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            company_id=company_id
        )
        
        db.session.add(audit_log)
        db.session.commit()
        
        return audit_log
    except Exception as e:
        # Don't let audit logging failures break the main operation
        db.session.rollback()
        print(f"Audit logging failed: {str(e)}")
        return None


def generate_description(entity_type, action, old_values=None, new_values=None):
    """Generate a human-readable description of the change."""
    entity_name = entity_type
    
    # Try to get a meaningful name from the values
    if new_values:
        if 'name' in new_values:
            entity_name = new_values['name']
        elif 'username' in new_values:
            entity_name = new_values['username']
        elif 'product_name' in new_values:
            entity_name = new_values['product_name']
    elif old_values:
        if 'name' in old_values:
            entity_name = old_values['name']
        elif 'username' in old_values:
            entity_name = old_values['username']
    
    action_verbs = {
        'create': 'created',
        'update': 'updated',
        'delete': 'deleted',
        'login': 'logged in',
        'logout': 'logged out',
        'password_change': 'changed password'
    }
    
    verb = action_verbs.get(action, action)
    
    return f"{entity_type} '{entity_name}' {verb}"


def log_create(entity_type, entity_id, values, description=None):
    """Log a create action."""
    return log_audit(
        entity_type=entity_type,
        entity_id=entity_id,
        action='create',
        new_values=values,
        description=description
    )


def log_update(entity_type, entity_id, old_values, new_values, description=None):
    """Log an update action."""
    return log_audit(
        entity_type=entity_type,
        entity_id=entity_id,
        action='update',
        old_values=old_values,
        new_values=new_values,
        description=description
    )


def log_delete(entity_type, entity_id, old_values=None, description=None):
    """Log a delete action."""
    return log_audit(
        entity_type=entity_type,
        entity_id=entity_id,
        action='delete',
        old_values=old_values,
        description=description
    )


def log_login(user_id, description=None):
    """Log a user login."""
    return log_audit(
        entity_type='User',
        entity_id=user_id,
        action='login',
        description=description or 'User logged in'
    )


def log_logout(user_id, description=None):
    """Log a user logout."""
    return log_audit(
        entity_type='User',
        entity_id=user_id,
        action='logout',
        description=description or 'User logged out'
    )


def get_entity_changes(old_values, new_values, exclude_fields=None):
    """
    Compare old and new values to get only changed fields.
    
    Args:
        old_values: Dictionary of old values
        new_values: Dictionary of new values
        exclude_fields: List of fields to exclude from changes
    
    Returns:
        Dictionary of changed fields with old and new values
    """
    if exclude_fields is None:
        exclude_fields = ['password_hash', 'last_updated', 'updated_at', 'created_at']
    
    changes = {}
    
    if not old_values:
        # All values are new
        for key, value in new_values.items():
            if key not in exclude_fields:
                changes[key] = {'old': None, 'new': value}
        return changes
    
    if not new_values:
        return changes
    
    for key, new_value in new_values.items():
        if key in exclude_fields:
            continue
        
        old_value = old_values.get(key)
        
        # Convert both to comparable format
        if old_value != new_value:
            # Handle special types
            if isinstance(old_value, (int, float, str)) and isinstance(new_value, (int, float, str)):
                changes[key] = {'old': old_value, 'new': new_value}
            elif str(old_value) != str(new_value):
                changes[key] = {'old': old_value, 'new': new_value}
    
    return changes

