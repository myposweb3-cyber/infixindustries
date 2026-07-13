"""
Audit log routes for viewing and managing audit logs.
"""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.models import db, AuditLog, User
from app.utils.permissions import require_permission
from app.utils.audit import get_current_company_id
from datetime import datetime, timedelta
import json

audit_bp = Blueprint('audit', __name__, template_folder='../../templates')


@audit_bp.route('/audit-logs')
@login_required
@require_permission('can_access_audit_logs')
def audit_logs():
    """Main audit logs page."""
    return render_template('audit/audit_logs.html')


@audit_bp.route('/api/audit-logs', methods=['GET'])
@login_required
@require_permission('can_access_audit_logs')
def get_audit_logs():
    """Get audit logs with filtering and pagination."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    
    # Filters
    entity_type = request.args.get('entity_type', '').strip()
    action = request.args.get('action', '').strip()
    user_id = request.args.get('user_id', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    search = request.args.get('search', '').strip()
    
    query = AuditLog.query
    
    # Filter by entity type
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    
    # Filter by action
    if action:
        query = query.filter(AuditLog.action == action)
    
    # Filter by user
    if user_id:
        try:
            query = query.filter(AuditLog.user_id == int(user_id))
        except ValueError:
            pass
    
    # Filter by date range
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(AuditLog.timestamp >= start)
        except ValueError:
            pass
    
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end + timedelta(days=1)  # Include the entire end date
            query = query.filter(AuditLog.timestamp < end)
        except ValueError:
            pass
    
    # Filter by search term (searches in description)
    if search:
        query = query.filter(AuditLog.description.ilike(f'%{search}%'))
    
    # Filter by company (if user has a company)
    company_id = get_current_company_id()
    if company_id:
        query = query.filter(
            AuditLog.company_id == company_id
        )
    
    # Order by timestamp descending (newest first)
    query = query.order_by(AuditLog.timestamp.desc())
    
    # Paginate
    logs = query.paginate(page=page, per_page=per_page)
    
    # Get unique entity types and actions for filters (filtered by company)
    filter_query = AuditLog.query
    if company_id:
        filter_query = filter_query.filter(AuditLog.company_id == company_id)
    
    entity_types = filter_query.with_entities(AuditLog.entity_type).distinct().all()
    entity_types = [e[0] for e in entity_types]
    
    actions = filter_query.with_entities(AuditLog.action).distinct().all()
    actions = [a[0] for a in actions]
    
    result = {
        'logs': [],
        'total': logs.total,
        'pages': logs.pages,
        'current_page': logs.page,
        'filters': {
            'entity_types': entity_types,
            'actions': actions
        }
    }
    
    for log in logs.items:
        log_dict = log.to_dict()
        # Include entity name in description if available
        if log.entity_type == 'User' and log.user:
            log_dict['entity_name'] = log.user.username
        result['logs'].append(log_dict)
    
    return jsonify(result)


@audit_bp.route('/api/audit-logs/<int:log_id>', methods=['GET'])
@login_required
@require_permission('can_access_settings')
def get_audit_log(log_id):
    """Get single audit log details."""
    log = AuditLog.query.get_or_404(log_id)
    return jsonify(log.to_dict())


@audit_bp.route('/api/audit-logs/all-users', methods=['GET'])
@login_required
@require_permission('can_access_audit_logs')
def get_all_audit_users():
    """Get all users who have ever logged anything (for filter dropdown)."""
    company_id = get_current_company_id()
    
    # Get all unique users from audit logs (no date filter)
    query = db.session.query(AuditLog.user_id).distinct()
    
    if company_id:
        query = query.filter(
            AuditLog.company_id == company_id
        )
    
    user_ids = query.all()
    users = []
    
    for (uid,) in user_ids:
        if uid:
            user = User.query.get(uid)
            if user:
                users.append({
                    'id': user.id,
                    'username': user.username
                })
    
    # Sort alphabetically
    users.sort(key=lambda x: x['username'])
    
    return jsonify(users)


@audit_bp.route('/api/audit-logs/stats', methods=['GET'])
@login_required
@require_permission('can_access_settings')
def get_audit_stats():
    """Get audit log statistics."""
    # Get date range
    days = int(request.args.get('days', 30))
    start_date = datetime.utcnow() - timedelta(days=days)
    
    company_id = get_current_company_id()
    
    # Base query
    base_query = AuditLog.query.filter(AuditLog.timestamp >= start_date)
    if company_id:
        base_query = base_query.filter(
            AuditLog.company_id == company_id
        )
    
    # Total count
    total_count = base_query.count()
    
    # Count by entity type
    entity_type_counts = {}
    for entity_type in base_query.with_entities(AuditLog.entity_type).distinct().all():
        et = entity_type[0]
        count = base_query.filter(AuditLog.entity_type == et).count()
        entity_type_counts[et] = count
    
    # Count by action
    action_counts = {}
    for action in base_query.with_entities(AuditLog.action).distinct().all():
        a = action[0]
        count = base_query.filter(AuditLog.action == a).count()
        action_counts[a] = count
    
    # Count by user
    user_counts = {}
    for user_id in base_query.with_entities(AuditLog.user_id).distinct().all():
        uid = user_id[0]
        if uid:
            count = base_query.filter(AuditLog.user_id == uid).count()
            user = User.query.get(uid)
            if user:
                user_counts[user.username] = count
    
    # Recent activity (last 24 hours)
    recent_start = datetime.utcnow() - timedelta(hours=24)
    recent_count = base_query.filter(AuditLog.timestamp >= recent_start).count()
    
    return jsonify({
        'total_count': total_count,
        'recent_count': recent_count,
        'entity_type_counts': entity_type_counts,
        'action_counts': action_counts,
        'user_counts': user_counts,
        'days': days
    })


@audit_bp.route('/api/audit-logs/export', methods=['GET'])
@login_required
@require_permission('can_access_settings')
def export_audit_logs():
    """Export audit logs to PDF."""
    from flask import make_response
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except ImportError:
        return jsonify({'error': 'PDF export requires reportlab. Install with: pip install reportlab'}), 500
    
    # Get filters
    entity_type = request.args.get('entity_type', '').strip()
    action = request.args.get('action', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    
    query = AuditLog.query
    
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(AuditLog.timestamp >= start)
        except ValueError:
            pass
    if end_date:
        try:
            end = datetime.strptime(end_date, '%Y-%m-%d')
            end = end + timedelta(days=1)
            query = query.filter(AuditLog.timestamp < end)
        except ValueError:
            pass
    
    query = query.order_by(AuditLog.timestamp.desc())
    logs = query.limit(500).all()  # Limit to 500 records for PDF
    
    # Create PDF using BytesIO
    from io import BytesIO
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, spaceAfter=20)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=8)
    
    # Title
    elements.append(Paragraph('Audit Logs Report', title_style))
    elements.append(Paragraph(f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', normal_style))
    
    # Filter info
    filter_text = 'Filters: '
    filtersApplied = []
    if entity_type:
        filtersApplied.append(f'Entity Type: {entity_type}')
    if action:
        filtersApplied.append(f'Action: {action}')
    if start_date:
        filtersApplied.append(f'Start Date: {start_date}')
    if end_date:
        filtersApplied.append(f'End Date: {end_date}')
    filter_text += ', '.join(filtersApplied) if filtersApplied else 'None'
    elements.append(Paragraph(filter_text, normal_style))
    elements.append(Paragraph(f'Total Records: {len(logs)}', normal_style))
    elements.append(Spacer(1, 20))
    
    # Table data
    table_data = [['#', 'Timestamp', 'User', 'Entity Type', 'Action', 'Description']]
    
    for idx, log in enumerate(logs, 1):
        timestamp = log.timestamp.strftime('%Y-%m-%d %H:%M') if log.timestamp else '-'
        username = log.user.username if log.user else 'System'
        entity_type_val = log.entity_type or '-'
        action_val = log.action or '-'
        description = (log.description[:40] + '..') if log.description and len(log.description) > 40 else (log.description or '-')
        
        table_data.append([
            str(idx),
            timestamp,
            username[:15],
            entity_type_val[:15],
            action_val,
            description
        ])
    
    # Create table
    col_widths = [25, 100, 70, 70, 50, 180]
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))
    
    elements.append(table)
    
    # Build PDF
    doc.build(elements)
    
    # Set response
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    filename = f'audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    
    return response


@audit_bp.route('/api/audit-logs/cleanup', methods=['POST'])
@login_required
@require_permission('can_access_settings')
def cleanup_audit_logs():
    """Clean up old audit logs."""
    data = request.get_json()
    days = int(data.get('days', 90))
    
    # Only allow admins and super admins to delete logs
    if current_user.role not in ['Admin', 'Super Admin']:
        return jsonify({'error': 'Only administrators can delete audit logs'}), 403
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    try:
        deleted_count = AuditLog.query.filter(AuditLog.timestamp < cutoff_date).delete()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} audit logs older than {days} days'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

