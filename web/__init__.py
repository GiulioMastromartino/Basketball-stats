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

    # Auto-fix schema for dev/demo (Plays feature)
    # WARNING: Only run this in DEBUG mode or if explicitly enabled
    # In production, use 'flask db upgrade' via Flask-Migrate instead.
    if app.config.get("DEBUG") or app.config.get("AUTO_MIGRATE"):
        with app.app_context():
            try:
                inspector = inspect(db.engine)

                # Check for game_events table and add missing columns
                if inspector.has_table("game_events"):
                    columns = [c["name"] for c in inspector.get_columns("game_events")]

                    missing_game_event_columns = []
                    if "quarter" not in columns:
                        missing_game_event_columns.append("quarter")
                    if "time_remaining" not in columns:
                        missing_game_event_columns.append("time_remaining")
                    if "score_margin" not in columns:
                        missing_game_event_columns.append("score_margin")
                    if "zone" not in columns:
                        missing_game_event_columns.append("zone")

                    if missing_game_event_columns:
                        app.logger.warning(
                            f"Detected outdated game_events schema (missing: {missing_game_event_columns}). Adding columns..."
                        )

                        for col in missing_game_event_columns:
                            try:
                                if col == "quarter":
                                    db.session.execute(
                                        text(
                                            "ALTER TABLE game_events ADD COLUMN quarter INTEGER"
                                        )
                                    )
                                elif col == "time_remaining":
                                    db.session.execute(
                                        text(
                                            "ALTER TABLE game_events ADD COLUMN time_remaining VARCHAR(10)"
                                        )
                                    )
                                elif col == "score_margin":
                                    db.session.execute(
                                        text(
                                            "ALTER TABLE game_events ADD COLUMN score_margin INTEGER"
                                        )
                                    )
                                elif col == "zone":
                                    db.session.execute(
                                        text(
                                            "ALTER TABLE game_events ADD COLUMN zone VARCHAR(50)"
                                        )
                                    )
                                app.logger.info(
                                    f"Added column {col} to game_events table."
                                )
                            except Exception as col_err:
                                app.logger.warning(
                                    f"Could not add column {col}: {col_err}"
                                )

                        db.session.commit()

                # Check for shot_events table and add missing columns
                if inspector.has_table("shot_events"):
                    columns = [c["name"] for c in inspector.get_columns("shot_events")]

                    missing_shot_event_columns = []
                    if "zone" not in columns:
                        missing_shot_event_columns.append("zone")

                    if missing_shot_event_columns:
                        app.logger.warning(
                            f"Detected outdated shot_events schema (missing: {missing_shot_event_columns}). Adding columns..."
                        )

                        for col in missing_shot_event_columns:
                            try:
                                if col == "zone":
                                    db.session.execute(
                                        text(
                                            "ALTER TABLE shot_events ADD COLUMN zone VARCHAR(50)"
                                        )
                                    )
                                app.logger.info(
                                    f"Added column {col} to shot_events table."
                                )
                            except Exception as col_err:
                                app.logger.warning(
                                    f"Could not add column {col}: {col_err}"
                                )

                        db.session.commit()

                # Check for plays table
                if inspector.has_table("plays"):
                    columns = [c["name"] for c in inspector.get_columns("plays")]

                    # Check for critical new columns
                    missing_columns = []
                    if "canvas_data" not in columns:
                        missing_columns.append("canvas_data")
                    if "diagram_svg" not in columns:
                        missing_columns.append("diagram_svg")

                    if missing_columns:
                        app.logger.warning(
                            f"Detected outdated Plays schema (missing: {missing_columns}). Recreating tables..."
                        )

                        # Drop dependent table first
                        if inspector.has_table("play_sequences"):
                            db.session.execute(text("DROP TABLE play_sequences"))
                            app.logger.info("Dropped play_sequences table.")

                        if inspector.has_table("shot_events"):
                            pass

                        db.session.execute(text("DROP TABLE plays"))
                        db.session.commit()
                        app.logger.info("Dropped plays table.")

                        db.create_all()
                else:
                    db.create_all()

                # Seed PlayType table if it exists but is empty
                if inspector.has_table("play_types"):
                    if PlayType.query.count() == 0:
                        default_types = ["Offense", "Defense", "Special"]
                        for t in default_types:
                            db.session.add(PlayType(name=t))
                        db.session.commit()
                        app.logger.info(
                            "Seeded default PlayTypes: Offense, Defense, Special"
                        )

                # Auto-create Advanced Analytics tables if missing
                advanced_tables = {
                    "lineups": """
                        CREATE TABLE IF NOT EXISTS lineups (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            lineup_hash VARCHAR(64) UNIQUE NOT NULL,
                            players JSON NOT NULL,
                            display_name VARCHAR(100),
                            is_starting BOOLEAN DEFAULT 0,
                            total_seconds INTEGER DEFAULT 0,
                            total_possessions INTEGER DEFAULT 0,
                            points_scored INTEGER DEFAULT 0,
                            points_allowed INTEGER DEFAULT 0,
                            games_played INTEGER DEFAULT 0,
                            segment_count INTEGER DEFAULT 0,
                            ortg FLOAT DEFAULT 0,
                            drtg FLOAT DEFAULT 0,
                            net_rating FLOAT DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """,
                    "lineup_segments": """
                        CREATE TABLE IF NOT EXISTS lineup_segments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            game_id INTEGER NOT NULL,
                            start_timestamp BIGINT NOT NULL,
                            end_timestamp BIGINT,
                            quarter INTEGER,
                            players JSON NOT NULL,
                            lineup_hash VARCHAR(64) NOT NULL,
                            points_scored INTEGER DEFAULT 0,
                            points_allowed INTEGER DEFAULT 0,
                            possessions INTEGER DEFAULT 0,
                            duration_seconds INTEGER DEFAULT 0,
                            lineup_id INTEGER,
                            FOREIGN KEY (game_id) REFERENCES games(id),
                            FOREIGN KEY (lineup_id) REFERENCES lineups(id)
                        )
                    """,
                    "possessions": """
                        CREATE TABLE IF NOT EXISTS possessions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            game_id INTEGER NOT NULL,
                            start_event_id INTEGER NOT NULL,
                            end_event_id INTEGER,
                            team_possession BOOLEAN DEFAULT 1,
                            quarter INTEGER,
                            points INTEGER DEFAULT 0,
                            play_id INTEGER,
                            FOREIGN KEY (game_id) REFERENCES games(id),
                            FOREIGN KEY (start_event_id) REFERENCES game_events(id),
                            FOREIGN KEY (end_event_id) REFERENCES game_events(id),
                            FOREIGN KEY (play_id) REFERENCES plays(id)
                        )
                    """,
                    "shot_zones": """
                        CREATE TABLE IF NOT EXISTS shot_zones (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            zone_name VARCHAR(50) UNIQUE NOT NULL,
                            zone_type VARCHAR(20) NOT NULL,
                            expected_value FLOAT NOT NULL,
                            description VARCHAR(255),
                            x_min FLOAT,
                            x_max FLOAT,
                            y_min FLOAT,
                            y_max FLOAT
                        )
                    """,
                    "player_lineup_stats": """
                        CREATE TABLE IF NOT EXISTS player_lineup_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            lineup_segment_id INTEGER NOT NULL,
                            player_name VARCHAR(100) NOT NULL,
                            points INTEGER DEFAULT 0,
                            fga INTEGER DEFAULT 0,
                            fgm INTEGER DEFAULT 0,
                            tpa INTEGER DEFAULT 0,
                            tpm INTEGER DEFAULT 0,
                            fta INTEGER DEFAULT 0,
                            ftm INTEGER DEFAULT 0,
                            oreb INTEGER DEFAULT 0,
                            dreb INTEGER DEFAULT 0,
                            ast INTEGER DEFAULT 0,
                            stl INTEGER DEFAULT 0,
                            blk INTEGER DEFAULT 0,
                            tov INTEGER DEFAULT 0,
                            reb_conceded INTEGER DEFAULT 0,
                            FOREIGN KEY (lineup_segment_id) REFERENCES lineup_segments(id)
                        )
                    """,
                }

                missing_advanced_tables = []
                for table_name, create_sql in advanced_tables.items():
                    if not inspector.has_table(table_name):
                        missing_advanced_tables.append(table_name)

                if missing_advanced_tables:
                    app.logger.warning(
                        f"Creating missing advanced analytics tables: {missing_advanced_tables}"
                    )

                    for table_name in missing_advanced_tables:
                        try:
                            db.session.execute(text(advanced_tables[table_name]))
                            app.logger.info(f"Created table: {table_name}")
                        except Exception as table_err:
                            app.logger.warning(
                                f"Could not create table {table_name}: {table_err}"
                            )

                    db.session.commit()

                    # Seed shot_zones with default values
                    if "shot_zones" in missing_advanced_tables:
                        try:
                            db.session.execute(
                                text("""
                                INSERT INTO shot_zones (zone_name, zone_type, expected_value, description, x_min, x_max, y_min, y_max) VALUES
                                ('Rim', 'Paint', 1.20, 'Layups and dunks at the basket', 210, 290, 0, 100),
                                ('Paint', 'Paint', 0.85, 'Shots in the paint (non-rim)', 150, 350, 0, 150),
                                ('Midrange', 'Midrange', 0.75, 'Mid-range jumpers', 0, 500, 100, 350),
                                ('Corner_3', 'Corner_3', 1.10, 'Corner 3-pointers', 0, 500, 0, 100),
                                ('Above_Break_3', 'Above_Break_3', 1.05, 'Above-the-break 3-pointers', 0, 500, 300, 470),
                                ('FT', 'FT', 0.75, 'Free throws', NULL, NULL, NULL, NULL)
                            """)
                            )
                            db.session.commit()
                            app.logger.info("Seeded default shot_zones data")
                        except Exception as seed_err:
                            app.logger.warning(f"Could not seed shot_zones: {seed_err}")

                    # Create indexes for performance
                    indexes = [
                        "CREATE INDEX IF NOT EXISTS idx_lineups_hash ON lineups(lineup_hash)",
                        "CREATE INDEX IF NOT EXISTS idx_lineups_net_rating ON lineups(net_rating)",
                        "CREATE INDEX IF NOT EXISTS idx_lineup_segments_game_id ON lineup_segments(game_id)",
                        "CREATE INDEX IF NOT EXISTS idx_lineup_segments_hash ON lineup_segments(lineup_hash)",
                        "CREATE INDEX IF NOT EXISTS idx_lineup_segments_lineup_id ON lineup_segments(lineup_id)",
                        "CREATE INDEX IF NOT EXISTS idx_possessions_game_id ON possessions(game_id)",
                        "CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_segment ON player_lineup_stats(lineup_segment_id)",
                        "CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_player ON player_lineup_stats(player_name)",
                    ]
                    for idx_sql in indexes:
                        try:
                            db.session.execute(text(idx_sql))
                        except Exception:
                            pass
                    db.session.commit()
                    app.logger.info("Advanced analytics tables created successfully")

                # Generic auto-migrate: add any missing columns from models
                added_columns = auto_add_missing_columns(db, logger=app.logger)
                if added_columns:
                    app.logger.info(
                        f"Schema auto-migrate: added {added_columns} missing columns"
                    )

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
    from web.routes.auth import auth_bp
    from web.routes.analytics import analytics_bp
    from web.routes.api import api_bp
    from web.routes.main import main_bp
    from web.routes.plays import plays_bp
    from web.routes.play_builder_api import builder_api_bp
    from web.routes.reports import reports_bp
    from web.routes.advanced_analytics_api import advanced_api_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(analytics_bp)
    app.register_blueprint(plays_bp)
    app.register_blueprint(builder_api_bp, url_prefix="/api/v1")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(advanced_api_bp)


def register_commands(app: Flask):
    """Register CLI commands"""
    from core.commands import seed_command

    app.cli.add_command(seed_command)
