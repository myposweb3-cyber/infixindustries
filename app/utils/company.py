"""
Company utility functions for multi-company support.
IMPORTANT: Use get_company_id() from app.utils.security (NOT this module).
This module provides helper functions that internally use the secure version.
"""
from flask import session, g, abort, current_app
from flask_login import current_user
from app.models import Company, User
from app import db

def set_current_company(company_id):
    """Set the current company in session."""
    session['company_id'] = company_id

def get_current_company():
    """Get the currently selected company from session."""
    # Import here to avoid circular imports
    from app.utils.security import get_company_id as get_company_id_secure
    
    company_id = get_company_id_secure()
    if company_id:
        return Company.query.get(company_id)
    return None

def get_user_companies(user_id):
    """Get all ACTIVE companies a user has access to (excludes deleted companies).

    Super Admin users should be able to see all active companies even if they are not
    associated with a specific company record. This returns all active companies for
    Super Admins, otherwise returns only the user's associated active companies.
    """
    user = User.query.get(user_id)
    if user:
        # Super Admin can view all active companies regardless of association
        if user.role and user.role.lower() == 'super admin':
            return Company.query.filter_by(is_active=True).all()
        # Filter to only return active companies for regular users
        return [c for c in user.companies if c.is_active]
    return []

def get_company_id():
    """
    DEPRECATED: Use app.utils.security.get_company_id() instead.
    This function is kept for backward compatibility only.
    The secure version validates user has access to the company.
    """
    from app.utils.security import get_company_id as get_company_id_secure
    current_app.logger.warning(
        "DEPRECATED: Use get_company_id from app.utils.security instead"
    )
    return get_company_id_secure()

def column_exists_in_db(table_name, column_name):
    """Check if a column exists in the actual database table."""
    try:
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False

def get_company_filter(model_class):
    """
    Get company filter for a model if company_id column exists in database.
    Returns None if the column doesn't exist in the database or no company is selected.
    Uses secure get_company_id() from security module.
    """
    from app.utils.security import get_company_id as get_company_id_secure
    from sqlalchemy import or_
    
    # Map model class to table name
    table_mapping = {
        'Sale': 'sales',
        'Product': 'products',
        'Customer': 'customers',
        'Supplier': 'suppliers',
        'Expense': 'expenses',
        'Purchase': 'purchases',
        'Warehouse': 'warehouses',
        'User': 'users',
        'SaleItem': 'sale_items',
        'HeldBill': 'held_bills',
        'Return': 'returns',
        'Setting': 'settings'
    }
    
    table_name = table_mapping.get(model_class.__name__)
    if not table_name:
        return None
    
    # Check if company_id column exists in the actual database
    if not column_exists_in_db(table_name, 'company_id'):
        return None
    
    # Use secure get_company_id() which validates user has access
    company_id = get_company_id_secure()
    if company_id is None:
        return None
    
    # Backward compatibility: include NULL company_id records
    return or_(
        model_class.company_id == company_id,
        model_class.company_id.is_(None)  # Use .is_(None) for proper NULL handling
    )

def filter_by_company(query, model_class):
    """
    Filter a query by current company.
    Returns the query with company filter applied if company is set and column exists.
    """
    company_filter = get_company_filter(model_class)
    if company_filter is not None:
        return query.filter(company_filter)
    return query

def require_company():
    """
    Check if user has a company selected.
    Returns the company if selected, None otherwise.
    """
    return get_current_company()

def is_company_admin(user_id, company_id):
    """Check if user is admin for a specific company."""
    user = User.query.get(user_id)
    if not user:
        return False
    
    # Check if user is associated with this company
    for company in user.companies:
        if company.id == company_id:
            return user.role in ['Admin', 'Super Admin']
    
    return False
