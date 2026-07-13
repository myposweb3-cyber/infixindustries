import smtplib
from email.message import EmailMessage
from flask import current_app


def send_email(to_email, subject, body, attachments=None):
    """Send a simple email using SMTP settings from app config.
    
    Expects the following config variables:
    - SMTP_SERVER: SMTP server address
    - SMTP_PORT: SMTP port (default: 587)
    - SMTP_USERNAME: SMTP username (optional)
    - SMTP_PASSWORD: SMTP password (optional)
    - SMTP_USE_TLS: Use TLS (default: True)
    - DEFAULT_FROM_EMAIL: Sender email address
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body text
        attachments: List of tuples (filename, bytes, mimetype)
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    # Check if SMTP is configured
    smtp_server = current_app.config.get('SMTP_SERVER')
    if not smtp_server:
        current_app.logger.warning('SMTP_SERVER not configured. Email sending disabled.')
        return False, 'Email service not configured on this server'
    
    smtp_port = current_app.config.get('SMTP_PORT', 587)
    smtp_user = current_app.config.get('SMTP_USERNAME')
    smtp_pass = current_app.config.get('SMTP_PASSWORD')
    use_tls = current_app.config.get('SMTP_USE_TLS', True)
    from_addr = current_app.config.get('DEFAULT_FROM_EMAIL', smtp_user or 'no-reply@localhost')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_email
    msg.set_content(body)

    # Attach files if provided (list of tuples (filename, bytes, mimetype))
    if attachments:
        for filename, data, mimetype in attachments:
            maintype, subtype = mimetype.split('/', 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    # Send email with proper error handling
    try:
        if use_tls:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.send_message(msg)
        server.quit()
        
        current_app.logger.info(f'Email sent successfully to {to_email}')
        return True, 'Email sent successfully'
        
    except smtplib.SMTPAuthenticationError as e:
        error_msg = 'SMTP authentication failed. Check SMTP credentials.'
        current_app.logger.error(f'{error_msg}: {str(e)}')
        return False, error_msg
        
    except smtplib.SMTPException as e:
        error_msg = f'SMTP error occurred: {str(e)}'
        current_app.logger.error(error_msg)
        return False, error_msg
        
    except Exception as e:
        error_msg = f'Failed to send email: {str(e)}'
        current_app.logger.error(error_msg)
        return False, error_msg
