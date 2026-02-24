#!/usr/bin/env python3
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 3600

    # Fix for SQLAlchemy 1.4+ which dropped support for 'postgres://'
    # Koyeb (and others) often provide DATABASE_URL as 'postgres://'
    _db_url = os.getenv("DATABASE_URL")
    if _db_url and _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = _db_url or f"sqlite:///{BASE_DIR / 'basketball_stats.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300}
    GAMES_DIR = os.getenv("GAMES_DIR", str(BASE_DIR / "Games"))
    OUTPUT_DIR = os.getenv("OUTPUT_DIR", str(BASE_DIR / "Output"))
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    CACHE_TYPE = os.getenv("CACHE_TYPE", "SimpleCache")
    CACHE_DEFAULT_TIMEOUT = int(os.getenv("CACHE_TIMEOUT", "300"))
    RATELIMIT_STORAGE_URL = os.getenv("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_STRATEGY = "fixed-window"
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_HEADERS_ENABLED = True
    ROLLING_WINDOW = int(os.getenv("ROLLING_WINDOW", "3"))
    TOP_SCORERS_LIMIT = int(os.getenv("TOP_SCORERS_LIMIT", "10"))
    DEFAULT_PAGE_SIZE = int(os.getenv("DEFAULT_PAGE_SIZE", "50"))
    MAX_PAGE_SIZE = int(os.getenv("MAX_PAGE_SIZE", "200"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", str(BASE_DIR / "basketball_stats.log"))
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 5
    FILENAME_PATTERN = r"^([^_]+)_(\d+)-(\d+)_(\d{2})-(\d{2})-(\d{4})_([FSP])$"
    GAME_TYPE_MAP = {"F": "Friendly", "S": "Season", "P": "Playoff"}
    REQUIRED_CSV_COLUMNS = [
        "Name",
        "MIN",
        "PTS",
        "FGM",
        "FGA",
        "FG%",
        "3PM",
        "3PA",
        "3P%",
        "FTM",
        "FTA",
        "FT%",
        "OREB",
        "DREB",
        "REB",
        "AST",
        "TOV",
        "STL",
        "BLK",
        "PF",
    ]
    MAX_POINTS_PER_GAME = 200
    MAX_MINUTES = 60
    MIN_PERCENT = 0.0
    MAX_PERCENT = 100.0

    # Email Config
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() in ["true", "on", "1"]
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    # Default sender to username if not explicitly set (Critical for Gmail)
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER") or os.getenv("MAIL_USERNAME")

    # WorkOS Configuration
    WORKOS_API_KEY = os.getenv("WORKOS_API_KEY")
    WORKOS_CLIENT_ID = os.getenv("WORKOS_CLIENT_ID")
    WORKOS_COOKIE_PASSWORD = os.getenv("WORKOS_COOKIE_PASSWORD")
    WORKOS_REDIRECT_URI = os.getenv(
        "WORKOS_REDIRECT_URI"
    )  # Must be set per environment


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = "DEBUG"
    # Development defaults for WorkOS
    WORKOS_REDIRECT_URI = os.getenv(
        "WORKOS_REDIRECT_URI", "http://localhost:8080/auth/callback"
    )


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    CACHE_TYPE = "SimpleCache"
    RATELIMIT_ENABLED = False
    SECRET_KEY = "test-secret-key"
    WORKOS_REDIRECT_URI = "http://localhost:8080/auth/callback"


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    LOG_LEVEL = "INFO"
    # In production, WORKOS_REDIRECT_URI must be set via environment variable
    # No default - will raise error if not configured


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(env_name=None):
    return config_map.get(
        env_name or os.getenv("FLASK_ENV", "development"), DevelopmentConfig
    )
