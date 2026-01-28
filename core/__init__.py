import os
import logging
from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail

# Initialize extensions
db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "info"

def create_app(config_name="default"):
    from config import get_config
    
    app = Flask(__name__, 
                template_folder="../web/templates",
                static_folder="../web/static")
    
    # Load config
    app.config.from_object(get_config(config_name))
    
    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    
    # Configure logging
    if not app.debug and not app.testing:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        app.logger.addHandler(handler)
        
    # Register blueprints
    from web.routes.main import main_bp
    from web.routes.auth import auth_bp
    # from web.routes.games import games_bp
    # from web.routes.plays import plays_bp
    # from web.routes.reports import reports_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    # app.register_blueprint(games_bp, url_prefix="/games")
    # app.register_blueprint(plays_bp, url_prefix="/plays")
    # app.register_blueprint(reports_bp, url_prefix="/reports")
    
    # REMOVED: Database seeding from create_app to avoid context errors.
    # Database seeding should be done via separate scripts (quick_start.py / reset_empty.py)
    # or by a dedicated CLI command, not implicitly during app factory creation.

    return app
