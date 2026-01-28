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
            
        # 3. Seed/Fix Admin
        env_email = os.getenv("ADMIN_EMAIL")
        env_user = os.getenv("ADMIN_USERNAME", "admin")
        env_pass = os.getenv("ADMIN_PASSWORD")
        
        # Fallbacks
        create_email = env_email or "admin@local.com"
        create_pass = env_pass or "admin123"
        
        user = User.query.filter_by(username=env_user).first()
        if not user:
            app.logger.info(f"Seeding admin for environment: {os.getenv('FLASK_ENV', 'unknown')}")
            hashed_pw = bcrypt.generate_password_hash(create_pass).decode('utf-8')
            new_admin = User(
                username=env_user,
                email=create_email,
                password_hash=hashed_pw,
                role='admin',
                is_admin=True
            )
            db.session.add(new_admin)
            db.session.commit()
            # Explicitly log the password so user knows what to use
            app.logger.info("="*50)
            app.logger.info(f"✓ ADMIN CREATED")
            app.logger.info(f"Username: {env_user}")
            app.logger.info(f"Password: {create_pass}")
            app.logger.info("="*50)
        else:
            # Auto-healing logic
            updates = False
            
            # Update Email if Env var is set and different
            if env_email and user.email != env_email:
                 user.email = env_email
                 updates = True
                 app.logger.info(f"✓ Fix: Updated admin email to {env_email}")
            
            # Update Password if Env var is set
            if env_pass and not user.check_password(env_pass):
                user.password_hash = bcrypt.generate_password_hash(env_pass).decode('utf-8')
                updates = True
                app.logger.info(f"✓ Fix: Updated admin password to match env: {env_pass}")
                
            if updates:
                db.session.commit()

    return app
