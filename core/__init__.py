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
        
    # Register blueprints (All restored)
    with app.app_context():
        from web.routes.main import main_bp
        from web.routes.auth import auth_bp
        from web.routes.games import games_bp
        from web.routes.plays import plays_bp
        from web.routes.reports import reports_bp
        
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp, url_prefix="/auth")
        app.register_blueprint(games_bp, url_prefix="/games")
        app.register_blueprint(plays_bp, url_prefix="/plays")
        app.register_blueprint(reports_bp, url_prefix="/reports")

        # Seeding Logic
        from core.models import User, PlayType
        
        # 1. Ensure tables exist
        db.create_all()
        
        # 2. Seed PlayTypes
        if not PlayType.query.first():
            types = ["Offense", "Defense", "Special"]
            for t_name in types:
                db.session.add(PlayType(name=t_name))
            db.session.commit()
            
        # 3. Seed/Fix Admin - ROBUST MODE
        env_email = os.getenv("ADMIN_EMAIL")
        env_user = os.getenv("ADMIN_USERNAME", "admin")
        env_pass = os.getenv("ADMIN_PASSWORD")
        
        # Fallbacks
        final_email = env_email or "admin@local.com"
        final_pass = env_pass or "admin123"
        
        user = User.query.filter_by(username=env_user).first()
        
        if not user:
            app.logger.info(f"Seeding NEW admin...")
            hashed_pw = bcrypt.generate_password_hash(final_pass).decode('utf-8')
            new_admin = User(
                username=env_user,
                email=final_email,
                password_hash=hashed_pw,
                role='admin',
                is_admin=True
            )
            db.session.add(new_admin)
            db.session.commit()
            app.logger.info("="*40)
            app.logger.info(f"ADMIN CREATED -> User: {env_user} | Pass: {final_pass}")
            app.logger.info("="*40)
        else:
            # FORCE UPDATE ON EVERY STARTUP to ensure consistency
            # This solves the "I set the env var but the DB is stuck" issue
            
            updates = False
            
            # Always sync email if env var provided
            if env_email and user.email != env_email:
                 user.email = env_email
                 updates = True
                 app.logger.info(f"-> Syncing Admin Email to: {env_email}")
            
            # Always sync password if env var provided
            # We blindly re-hash to be 100% sure it matches the env var
            if env_pass:
                 user.password_hash = bcrypt.generate_password_hash(env_pass).decode('utf-8')
                 updates = True
                 app.logger.info(f"-> Syncing Admin Password to env variable: {env_pass}")
            
            if updates:
                db.session.commit()
                app.logger.info("Admin credentials synchronized with Environment.")

    return app
