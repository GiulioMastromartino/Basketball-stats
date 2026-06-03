#!/usr/bin/env python3
"""
Enhanced Flask Application Factory
Includes authentication, CSRF, rate limiting, caching, structured logging,
Prometheus metrics, and request diagnostics.
"""

import logging
import os
import time
import uuid
from logging.handlers import RotatingFileHandler

from flask import Flask, g, request, session
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, AnonymousUserMixin, current_user
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from prometheus_flask_exporter import PrometheusMetrics
from sqlalchemy import inspect, text
from config import get_config
from core.models import User, bcrypt, db, PlayType
from core.db_migrations import add_missing_columns as auto_add_missing_columns
from core import mail
from core.logger import configure_root_logger, get_logger


# Initialize extensions
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
)
cache = Cache()
migrate = Migrate()
metrics = PrometheusMetrics.for_app_factory(
    group_by="endpoint",
    path="/metrics",
    default_labels={"app": "basketball-stats"},
)


class NoAuthUser(AnonymousUserMixin):
    id = 0
    username = "local"
    email = "local@localhost"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_gm(self):
        return True

    @property
    def is_manager(self):
        return True

    @property
    def is_admin(self):
        return True

    @property
    def is_coach(self):
        return True

    @property
    def organization_id(self):
        return None

    @property
    def assigned_teams(self):
        return []


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
    mail.init_app(app)
    if not disable_auth:
        csrf.init_app(app)
    cache.init_app(app)
    if not disable_auth:
        limiter.init_app(app)

    # Initialize Prometheus metrics
    if config.METRICS_ENABLED:
        metrics.init_app(app)

    # Request diagnostics middleware
    @app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.start_time = time.time()

        request_logger = get_logger("access")
        request_logger.info(
            "Request started",
            extra={"extra_fields": {"method": request.method, "path": request.path}},
        )

    @app.before_request
    def _set_team_context():
        """Ensure current_team_id is set in session for authenticated users."""
        if current_user.is_authenticated and current_user.organization_id:
            if not session.get("current_team_id"):
                teams = current_user.assigned_teams
                if teams:
                    session["current_team_id"] = teams[0].id
                    session["current_team_name"] = teams[0].name

    @app.context_processor
    def _inject_team_context():
        ctx = {
            "current_team_id": session.get("current_team_id"),
            "current_team_name": session.get("current_team_name"),
        }
        try:
            if current_user.is_authenticated:
                ctx["assigned_teams"] = current_user.assigned_teams
        except Exception:
            ctx["assigned_teams"] = []
        return ctx

    @app.after_request
    def _log_response(response):
        duration_ms = round((time.time() - g.get("start_time", time.time())) * 1000, 2)
        response.headers["X-Request-ID"] = g.get("request_id", "")
        response.headers["X-Request-Duration-Ms"] = str(duration_ms)

        request_logger = get_logger("access")
        request_logger.info(
            "Request completed",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        return response

    # Configure login manager
    login_manager.init_app(app)
    if disable_auth:
        login_manager.login_view = None
        login_manager.login_message = None
        login_manager.login_message_category = None
        login_manager.anonymous_user = NoAuthUser
    else:
        login_manager.login_view = "auth.login"
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
    """Configure structured logging with rotation and optional JSON output"""
    log_level = getattr(logging, config.LOG_LEVEL)
    log_file = config.LOG_FILE
    if log_file == "/dev/stdout":
        log_file = None

    configure_root_logger(
        level=log_level,
        fmt=config.LOG_FORMAT,
        log_file=log_file,
        max_bytes=config.LOG_MAX_BYTES,
        backup_count=config.LOG_BACKUP_COUNT,
        app=app,
    )


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
