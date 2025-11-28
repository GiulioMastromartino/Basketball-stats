#!/usr/bin/env python3
"""
Enhanced Flask Application Factory
Includes authentication, CSRF, rate limiting, and caching
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from config import get_config
from core.models import User, bcrypt, db

# Initialize extensions
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)
cache = Cache()


def create_app(config_name: str = None) -> Flask:
    """
    Application factory with full security stack.
    """
    app = Flask(__name__)

    # Load configuration
    config = get_config(config_name)
    app.config.from_object(config)

    # Setup logging
    setup_logging(app, config)

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)

    # Configure login manager
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    register_blueprints(app)

    return app


def setup_logging(app: Flask, config):
    """Configure application logging with rotation"""
    log_level = getattr(logging, config.LOG_LEVEL)

    # File handler
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s]: %(message)s")
    )

    app.logger.addHandler(file_handler)
    app.logger.setLevel(log_level)


def register_blueprints(app: Flask):
    """Register all blueprints"""
    # Import blueprints here to avoid circular imports
    from web.routes.analytics import analytics_bp  # <--- NEW IMPORT
    from web.routes.api import api_bp
    from web.routes.auth import auth_bp
    from web.routes.main import main_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(analytics_bp)  # <--- NEW REGISTRATION
