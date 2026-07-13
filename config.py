import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    APP_NAME = 'POS System Web'
    VERSION = '1.0.0'

    # Database
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Session settings
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///pos_dev.db'

    # MailHog defaults for local development
    SMTP_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    SMTP_PORT = int(os.environ.get('MAIL_PORT', 1025))
    SMTP_USERNAME = os.environ.get('MAIL_USERNAME')
    SMTP_PASSWORD = os.environ.get('MAIL_PASSWORD')
    SMTP_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False') in ('True', 'true', '1')
    DEFAULT_FROM_EMAIL = os.environ.get('MAIL_DEFAULT_SENDER', 'no-reply@localhost')

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    # Use SQLite for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

def get_config(config_name=None):
    """Get configuration class based on name."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV') or 'development'

    config_map = {
        'development': DevelopmentConfig,
        'testing': TestingConfig,
        'production': ProductionConfig
    }

    return config_map.get(config_name.lower(), DevelopmentConfig)
