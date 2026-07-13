import os
from flask import current_app

# Optional Twilio import - package may not be installed
try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    Client = None


def send_whatsapp_via_twilio(to_phone, text, media_urls=None):
    """Send WhatsApp message using Twilio WhatsApp API. Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM in config.
    `to_phone` should include country code e.g. +9477...
    `media_urls` is an optional list of media URLs to attach.
    Returns (True, message_sid) on success or (False, error)
    """
    if not TWILIO_AVAILABLE:
        return False, 'Twilio package not installed'
    
    sid = current_app.config.get('TWILIO_ACCOUNT_SID')
    token = current_app.config.get('TWILIO_AUTH_TOKEN')
    from_whatsapp = current_app.config.get('TWILIO_WHATSAPP_FROM')

    if not sid or not token or not from_whatsapp:
        return False, 'Twilio not configured'

    try:
        client = Client(sid, token)
        to_whatsapp = f'whatsapp:{to_phone}'
        from_whatsapp_full = f'whatsapp:{from_whatsapp}'

        if media_urls:
            message = client.messages.create(body=text, from_=from_whatsapp_full, to=to_whatsapp, media_url=media_urls)
        else:
            message = client.messages.create(body=text, from_=from_whatsapp_full, to=to_whatsapp)

        return True, message.sid
    except Exception as e:
        return False, str(e)
