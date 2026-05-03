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
from flask_login import LoginManager, AnonymousUserMixin
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from sqlalchemy import inspect, text
from config import get_config
from core.models import User, bcrypt, db, PlayType
from core.db_migrations import add_missing_columns as auto_add_missing_columns
from core import mail


# Initialize extensions
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)
cache = Cache()
migrate = Migrate()


class NoAuthUser(AnonymousUserMixin):
    id = 0
    username = "local"
    email = "local@localhost"
    role = "admin"
    is_admin = True

    @property
    def is_authenticated(self):
        return True

    @property
    def is_manager(self):
        return True


def create_app(config_name: str = None) -> Flask:
    """
    Application factory with full security stack.
    """
    app = Flask(__name__)

    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Load configuration
    config = get_config(config_name)
    app.config.from_object(config)
    disable_auth = os.getenv("DISABLE_AUTH", "").lower() in ("1", "true", "yes", "on")
    if disable_auth:
        # Allow all requests through login_required for isolated/personal deployments
        app.config["LOGIN_DISABLED"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["RATELIMIT_ENABLED"] = False

        @app.context_processor
        def _noop_csrf_token():
            return {"csrf_token": lambda: ""}

    # Setup logging
    setup_logging(app, config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    mail.init_app(app)  # <--- Initialize Mail
    if not disable_auth:
        csrf.init_app(app)
    cache.init_app(app)
    if not disable_auth:
        limiter.init_app(app)

    # Configure login manager
    login_manager.init_app(app)
    if disable_auth:
        login_manager.login_view = None
        login_manager.login_message = None
        login_manager.login_message_category = None
        login_manager.anonymous_user = NoAuthUser
    else:
        login_manager.login_view = "main.landing"
        login_manager.login_message = "Please log in to access this page."
        login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    register_blueprints(app)

    # Register CLI commands
    register_commands(app)

    return app


def setup_logging(app: Flask, config):
    """Configure application logging with rotation"""
    log_level = getattr(logging, config.LOG_LEVEL)

    # File handler
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_BACKUP_COUNT,
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
    from web.routes.auth import auth_bp
    from web.routes.analytics import analytics_bp
    from web.routes.api_v1 import api_v1_bp
    from web.routes.main import main_bp
    from web.routes.plays import plays_bp
    from web.routes.reports import reports_bp
    from web.routes.advanced_analytics_api import advanced_api_bp
    from web.routes.health import health_bp
    from web.routes.pdf_export import pdf_export_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
    app.register_blueprint(analytics_bp)
    app.register_blueprint(plays_bp)
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(advanced_api_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(pdf_export_bp, url_prefix="/api/pdf")


def register_commands(app: Flask):
    """Register CLI commands"""
    from core.commands import seed_command

    app.cli.add_command(seed_command)
