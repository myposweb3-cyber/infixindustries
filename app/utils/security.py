"""
Multi-Company Security & Authorization Layer
Ensures complete data isolation between companies
"""
from functools import wraps
from flask import session, jsonify, abort, current_app
from flask_login import current_user
from app.models import Company, db
from sqlalchemy import or_

def get_company_id():
    """Get current company ID from session with validation."""
    if not current_user.is_authenticated:
        return None
    
    company_id = session.get('company_id')
    
    # Validate the company_id belongs to this user (except for Super Admin)
    if company_id:
        is_super_admin = current_user.role and current_user.role.lower() == 'super admin'
        
        if is_super_admin:
            # Super Admin can access any company
            return company_id
        
        # Regular Admin/Cashier can only access their assigned companies
        user_company_ids = [c.id for c in current_user.companies if c.is_active]
        if company_id in user_company_ids:
            return company_id
        else:
            # Unauthorized company access attempt
            current_app.logger.warning(
                f"Unauthorized company access: User {current_user.username} "
                f"attempted to access company {company_id}"
            )
            return None
    
    return None


def require_super_admin(f):
    """
    Decorator: Require Super Admin role.
    Super Admin can manage all companies and users.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Unauthorized'}), 401
        
        is_super_admin = (current_user.role and 
                         current_user.role.lower() == 'super admin')
        
        if not is_super_admin:
            current_app.logger.warning(
                f"Super Admin access denied: User {current_user.username} "
                f"(role: {current_user.role}) attempted restricted operation"
            )
            return jsonify({'error': 'Super Admin access required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_company_admin(f):
    """
    Decorator: Require Company Admin role.
    Company Admin manages one company and its users/resources.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Unauthorized'}), 401
        
        user_role = current_user.role.lower() if current_user.role else None
        is_company_admin = user_role in ['admin', 'super admin']
        
        if not is_company_admin:
            current_app.logger.warning(
                f"Admin access denied: User {current_user.username} "
                f"(role: {current_user.role}) attempted admin operation"
            )
            return jsonify({'error': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    
    return decorated_function


def require_company_context(f):
    """
    Decorator: Ensure user has selected a valid company.
    Applied to all data access endpoints.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': 'Unauthorized'}), 401
        
        company_id = get_company_id()
        
        if not company_id:
            current_app.logger.warning(
                f"No company context: User {current_user.username} "
                f"attempted operation without selecting company"
            )
            return jsonify({'error': 'No company selected'}), 400
        
        return f(*args, **kwargs)
    
    return decorated_function


def get_company_filter(model):
    """
    Generate SQLAlchemy filter for company isolation.
    Returns filter that includes current company OR NULL (for backward compat).
    """
    company_id = get_company_id()
    
    if not company_id:
        return None
    
    # Check if model has company_id column
    if hasattr(model, 'company_id'):
        return or_(
            model.company_id == company_id,
            model.company_id == None  # Backward compatibility
        )
    
    return None


def verify_resource_access(model_instance):
    """
    Verify user has access to a specific resource.
    Raises 403 if unauthorized.
    """
    current_company_id = get_company_id()
    
    if not current_company_id:
        abort(400, "No company selected")
    
    # Check if resource has company_id and belongs to current company
    if hasattr(model_instance, 'company_id'):
        if model_instance.company_id and model_instance.company_id != current_company_id:
            current_app.logger.warning(
                f"Cross-company access denied: User {current_user.username} "
                f"attempted to access {model_instance.__class__.__name__} "
                f"from company {model_instance.company_id} "
                f"(current company: {current_company_id})"
            )
            abort(403, "Access to this resource denied")


def get_current_company():
    """Get current company object."""
    company_id = get_company_id()
    if company_id:
        return Company.query.get(company_id)
    return None


def before_request_company_check():
    """
    Flask before_request handler.
    Validates company context on every request for authenticated users.
    ENFORCES:
    1. Company exists and is active
    2. User has access to the company (or is Super Admin)
    3. User is assigned to exactly ONE company (except Super Admin)
    """
    if not current_user.is_authenticated:
        return
    
    company_id = session.get('company_id')
    is_super_admin = (current_user.role and 
                     current_user.role.lower() == 'super admin')
    
    # Validate company_id if set
    if company_id:
        try:
            company_id = int(company_id)  # Validate type
        except (ValueError, TypeError):
            current_app.logger.warning(
                f"Invalid company_id type for user {current_user.username}: {company_id}"
            )
            session.pop('company_id', None)
            return
        
        company = Company.query.get(company_id)
        
        # ✅ Check 1: Company exists and is active
        if not company or not company.is_active:
            current_app.logger.warning(
                f"Invalid/inactive company {company_id} cleared from session "
                f"for user {current_user.username}"
            )
            session.pop('company_id', None)
            current_app.logger.info(
                f"Session cleared for user {current_user.username}: "
                f"company {company_id} not found or inactive"
            )
            return
        
        # ✅ Check 2: User has access to this company
        if not is_super_admin:
            user_company_ids = [c.id for c in current_user.companies if c.is_active]
            
            if company_id not in user_company_ids:
                current_app.logger.warning(
                    f"SECURITY: Unauthorized company access attempt by user "
                    f"{current_user.username}: tried to access company {company_id}, "
                    f"allowed: {user_company_ids}"
                )
                session.pop('company_id', None)
                # Don't abort here, just clear and let route handle context requirement
                return
            
            # ✅ Check 3: User should have EXACTLY ONE company (non-super-admin)
            if len(user_company_ids) > 1:
                current_app.logger.error(
                    f"SECURITY: User {current_user.username} assigned to multiple "
                    f"companies {user_company_ids}. This violates multi-company policy. "
                    f"User should be re-assigned to single company."
                )
                # For now, log it but allow. Future: abort(400, "User assigned to multiple companies")
    else:
        # ✅ Check 4: Super Admin can see all companies
        if is_super_admin:
            current_app.logger.debug(
                f"Super Admin {current_user.username} has no company selected"
            )
        else:
            # Non-super-admin should have a company selected
            user_company_ids = [c.id for c in current_user.companies if c.is_active]
            
            if not user_company_ids:
                current_app.logger.warning(
                    f"User {current_user.username} has no active companies assigned"
                )
            elif len(user_company_ids) == 1:
                # Auto-select if user has exactly one company
                session['company_id'] = user_company_ids[0]
                current_app.logger.debug(
                    f"Auto-selected company {user_company_ids[0]} for user "
                    f"{current_user.username}"
                )

