from flask import Flask
from flask_migrate import Migrate
from core.models import db, User  # Import your models
from config import Config

def create_app():
    app = Flask(__name__, template_folder="../web/templates", static_folder="../web/static")
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Flask-Migrate

    with app.app_context():
        # Import routes
        from web.routes.main import main_bp
        from web.routes.auth import auth_bp
        from web.routes.analytics import analytics_bp
        from web.routes.api import api_bp

        # Register blueprints
        app.register_blueprint(main_bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(analytics_bp)
        app.register_blueprint(api_bp, url_prefix='/api')

        # Create database tables if they don't exist
        # db.create_all()  <-- Commented out to use migrations instead

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
