#!/usr/bin/env python3
import argparse
import os

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
        db.create_all()
        
        # Auto-migration fix for existing databases
        # Check if 'source' column exists in 'games' table
        try:
            with db.engine.connect() as conn:
                # SQLite specific check
                result = conn.execute(text("PRAGMA table_info(games)"))
                columns = [row[1] for row in result.fetchall()]
                
                if 'source' not in columns:
                    print("Migrating database: Adding 'source' column to 'games' table...")
                    conn.execute(text("ALTER TABLE games ADD COLUMN source VARCHAR(20) DEFAULT 'IMPORT'"))
                    conn.commit()
                    print("Migration successful.")
        except Exception as e:
            print(f"Auto-migration warning: {e}")

    return app

# Support for 'flask run' and 'flask db' commands
# Flask checks for 'app' or 'application' in FLASK_APP module
app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="development")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    
    # Overwrite the default app if args are provided (though typically same env)
    if args.env != os.getenv("FLASK_ENV", "development"):
        app = create_app(args.env)
        
    app.run(host=args.host, port=args.port, debug=app.config["DEBUG"])
