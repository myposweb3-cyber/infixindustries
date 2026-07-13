from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.urls import url_parse
from datetime import datetime
from app.models import User, db, Company
from app.forms import LoginForm, ForgotPasswordForm, ResetPasswordForm
from app.utils.email_sender import send_email
from app.utils.company import set_current_company, get_user_companies

auth_bp = Blueprint('auth', __name__, template_folder='../../templates')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)

        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()

        # ✅ SET COMPANY CONTEXT - CRITICAL FOR MULTI-COMPANY
        # Get user's companies
        user_companies = get_user_companies(user.id)
        
        # If no companies assigned (e.g., Super Admin), get all active companies
        if not user_companies and user.role and user.role.lower() in ['admin', 'super admin']:
            user_companies = Company.query.filter_by(is_active=True).all()
        
        if user_companies:
            # Automatically set first active company
            set_current_company(user_companies[0].id)
            session['user_role'] = user.role.lower() if user.role else 'cashier'
        else:
            flash('No active companies available. Please contact system administrator.', 'warning')
        
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('main.dashboard')
        return redirect(next_page)

    return render_template('auth/login.html', title='Sign In', form=form)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Render form to request a password reset link and send email.
    
    GET: Display forgot password form
    POST: Validate email and send reset link if account exists
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            # Generate reset token (1 hour expiration)
            token = user.get_reset_token(expires_sec=3600)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Compose email
            app_name = current_app.config.get('APP_NAME', 'POS System')
            subject = f"{app_name} - Password Reset Request"
            body = f"""Hello {user.username},

We received a request to reset your password. Click the link below to set a new password:

{reset_url}

This link will expire in 1 hour.

If you did not request a password reset, please ignore this email. Your account is safe.

Best regards,
{app_name} Team"""
            
            # Send reset email
            ok, msg = send_email(user.email, subject, body)
            if not ok:
                current_app.logger.error(f'Failed to send password reset email to {user.email}: {msg}')
            else:
                current_app.logger.info(f'Password reset email sent successfully to {user.email}')
        
        # Always show the same message to avoid leaking account existence
        flash('If an account with that email exists, a password reset link has been sent.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Verify token and allow user to set a new password.
    
    GET: Display reset password form
    POST: Validate and update password if token is valid
    """
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    user = User.verify_reset_token(token)
    if not user:
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        current_app.logger.info(f'Password reset successful for user: {user.username}')
        flash('Your password has been updated. You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout user and clear company context."""
    # ✅ CLEAR COMPANY CONTEXT
    session.pop('company_id', None)
    session.pop('user_role', None)
    session.pop('current_company', None)
    
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/verify-admin-password', methods=['POST'])
@login_required
def verify_admin_password():
    """Verify admin password for sensitive operations like credit override."""
    data = request.get_json()
    
    if not data or 'password' not in data:
        return jsonify({'success': False, 'error': 'Password is required'}), 400
    
    password = data.get('password', '').strip()
    
    if not password:
        return jsonify({'success': False, 'error': 'Password cannot be empty'}), 400
    
    # Verify the current user's password
    if not current_user.check_password(password):
        # Log the failed attempt
        current_app.logger.warning(f"Failed admin password verification attempt for user: {current_user.username}")
        return jsonify({'success': False, 'error': 'Invalid password'}), 401
    
    # Password verified successfully
    current_app.logger.info(f"Admin password verified for user: {current_user.username}")
    return jsonify({'success': True, 'message': 'Password verified'})

