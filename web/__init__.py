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
from flask_migrate import Migrate
from sqlalchemy import inspect, text
from config import get_config
from core.models import User, bcrypt, db, PlayType
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
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    mail.init_app(app)  # <--- Initialize Mail
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
    
    # Register CLI commands
    register_commands(app)

    # Auto-fix schema for dev/demo (Plays feature)
    # WARNING: Only run this in DEBUG mode or if explicitly enabled
    # In production, use 'flask db upgrade' via Flask-Migrate instead.
    if app.config.get("DEBUG") or app.config.get("AUTO_MIGRATE"):
        with app.app_context():
            try:
                inspector = inspect(db.engine)

                # Check for plays table
                if inspector.has_table("plays"):
                    columns = [c['name'] for c in inspector.get_columns("plays")]

                    # Check for critical new columns
                    missing_columns = []
                    if "canvas_data" not in columns:
                        missing_columns.append("canvas_data")
                    if "diagram_svg" not in columns:
                        missing_columns.append("diagram_svg")

                    if missing_columns:
                        app.logger.warning(f"Detected outdated Plays schema (missing: {missing_columns}). Recreating tables...")

                        # Drop dependent table first
                        if inspector.has_table("play_sequences"):
                            db.session.execute(text("DROP TABLE play_sequences"))
                            app.logger.info("Dropped play_sequences table.")

                        if inspector.has_table("shot_events"):
                            pass

                        db.session.execute(text("DROP TABLE plays"))
                        db.session.commit()
                        app.logger.info("Dropped plays table.")
                        
                        # Disabled auto create_all to let migrations handle it
                        # db.create_all()
                else:
                    # Disabled auto create_all to let migrations handle it
                    # db.create_all()
                    pass

                # Ensure PlayType table exists and is seeded if needed (safely)
                # But generally rely on migrations. Only seeding if table exists but empty.
                if inspector.has_table("play_types"):
                     if PlayType.query.count() == 0:
                        default_types = ["Offense", "Defense", "Special"]
                        for t in default_types:
                            db.session.add(PlayType(name=t))
                        db.session.commit()
                        app.logger.info("Seeded default PlayTypes: Offense, Defense, Special")

            except Exception as e:
                app.logger.error(f"Schema auto-fix failed: {e}")

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
    # Import blueprints here to avoid circular imports
    from web.routes.analytics import analytics_bp
    from web.routes.api import api_bp
    from web.routes.auth import auth_bp
    from web.routes.main import main_bp
    from web.routes.plays import plays_bp
    from web.routes.play_builder_api import builder_api_bp
    from web.routes.reports import reports_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(analytics_bp)
    app.register_blueprint(plays_bp)
    app.register_blueprint(builder_api_bp, url_prefix="/api/v1")
    app.register_blueprint(reports_bp)


def register_commands(app: Flask):
    """Register CLI commands"""
    from core.commands import seed_command
    app.cli.add_command(seed_command)
