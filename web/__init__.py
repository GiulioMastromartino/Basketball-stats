#!/usr/bin/env python3
"""
Enhanced Flask Application Factory
Includes authentication, CSRF, rate limiting, and caching
"""

import logging
import os
from logging.handlers import RotatingFileHandler

import click
from flask import Flask
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text

from config import get_config
from core.models import User, Game, PlayerStat, ShotEvent, GameEvent, Play, bcrypt, db

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
    bcrypt.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)

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

    # Auto-migrate database schema on startup
    with app.app_context():
        # Ensure all tables exist (creates new tables like game_events, plays if missing)
        db.create_all()
        # Perform schema migrations for existing tables
        auto_migrate_schema()

    return app


def auto_migrate_schema():
    """
    Automatically detect and add missing columns to existing tables.
    This prevents OperationalError when the code expects columns that don't exist.
    """
    try:
        with db.engine.connect() as conn:
            # --- Check 'games' table ---
            result_games = conn.execute(text("PRAGMA table_info(games)"))
            games_columns = [row[1] for row in result_games.fetchall()]
            
            if 'source' not in games_columns:
                print("[AUTO-MIGRATION] Adding 'source' column to 'games' table...")
                conn.execute(text("ALTER TABLE games ADD COLUMN source VARCHAR(20) DEFAULT 'IMPORT'"))
                conn.commit()
                print("[AUTO-MIGRATION] Successfully added 'source' column.")

            # --- Check 'player_stats' table ---
            result_stats = conn.execute(text("PRAGMA table_info(player_stats)"))
            stats_columns = [row[1] for row in result_stats.fetchall()]
            
            if 'plus_minus' not in stats_columns:
                print("[AUTO-MIGRATION] Adding 'plus_minus' column to 'player_stats' table...")
                conn.execute(text("ALTER TABLE player_stats ADD COLUMN plus_minus INTEGER DEFAULT 0"))
                conn.commit()
                print("[AUTO-MIGRATION] Successfully added 'plus_minus' column.")
            
    except Exception as e:
        print(f"[AUTO-MIGRATION] Warning: {e}")


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
    from web.routes.analytics import analytics_bp
    from web.routes.api import api_bp
    from web.routes.auth import auth_bp
    from web.routes.main import main_bp
    from web.routes.plays import plays_bp  # <--- NEW

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(analytics_bp)
    app.register_blueprint(plays_bp)  # <--- NEW


def register_commands(app: Flask):
    """Register custom CLI commands"""
    
    @app.cli.command("reset-stats-db")
    def reset_stats_db():
        """
        Drops Game, PlayerStat, ShotEvent, GameEvent, Play tables 
        to apply new schema changes, but PRESERVES the User table.
        """
        click.echo("WARNING: This will delete all GAMES and STATS.")
        if not click.confirm("Are you sure you want to continue? Users will be preserved."):
            return

        with app.app_context():
            try:
                # Drop tables in dependency order
                click.echo("Dropping tables...")
                ShotEvent.__table__.drop(db.engine, checkfirst=True)
                GameEvent.__table__.drop(db.engine, checkfirst=True)
                PlayerStat.__table__.drop(db.engine, checkfirst=True)
                Game.__table__.drop(db.engine, checkfirst=True)
                Play.__table__.drop(db.engine, checkfirst=True)
                
                click.echo("Recreating all tables...")
                db.create_all()
                
                click.echo("Done! DB reset. User table preserved.")
            except Exception as e:
                click.echo(f"Error resetting DB: {e}")
