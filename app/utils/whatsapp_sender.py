from flask import current_app
import urllib.parse


def generate_whatsapp_link(phone, text):
    """Generate a wa.me link to send a text message via WhatsApp (user will open link).
    For full API integration (Twilio or WhatsApp Business API), replace with provider code.
    """
    if not phone:
        return None
    encoded = urllib.parse.quote(text)
    # Use wa.me format
    phone_digits = ''.join(c for c in phone if c.isdigit())
    return f'https://wa.me/{phone_digits}?text={encoded}'
