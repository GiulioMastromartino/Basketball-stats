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
    # We use local imports inside the factory to prevent circular import issues
    # but we must ensure the models are loaded before we query them
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

        # Seeding Logic - Safely inside app_context
        # Import models here to ensure they are registered with SQLAlchemy
        from core.models import User, PlayType
        
        # 1. Ensure tables exist
        db.create_all()
        
        # 2. Seed PlayTypes
        if not PlayType.query.first():
            types = ["Offense", "Defense", "Special"]
            for t_name in types:
                db.session.add(PlayType(name=t_name))
            db.session.commit()
            app.logger.info(f"Seeded default PlayTypes: {', '.join(types)}")
            
        # 3. Seed/Fix Admin
        admin_email = os.getenv("ADMIN_EMAIL", "admin@local.com")
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        
        user = User.query.filter_by(username=admin_user).first()
        if not user:
            app.logger.info(f"Seeding admin for environment: {os.getenv('FLASK_ENV', 'unknown')}")
            hashed_pw = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
            new_admin = User(
                username=admin_user,
                email=admin_email,
                password_hash=hashed_pw,
                role='admin',
                is_admin=True
            )
            db.session.add(new_admin)
            db.session.commit()
            app.logger.info(f"✓ Admin user created. Username: '{admin_user}'")
        elif user.email != admin_email and admin_email != "admin@local.com":
             user.email = admin_email
             db.session.commit()
             app.logger.info(f"✓ Updated admin email to match environment: {admin_email}")

    return app
