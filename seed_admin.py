import os
import sys
from pathlib import Path

# Ensure the current directory is in the path so imports work
sys.path.append(str(Path(__file__).parent))

from core.models import User, db
from web import create_app

def create_admin():
    """Ensure a default admin user exists."""
    env = os.getenv("FLASK_ENV", "development")
    print(f"Seeding admin for environment: {env}")
    app = create_app(env)
    
    with app.app_context():
        # Check if any user exists (to prevent overwriting if custom users are made)
        # Or just check for 'admin' specifically
        if not User.query.filter_by(username="admin").first():
            print("Creating default admin user...")
            try:
                admin = User(username="admin", email="admin@local.com", is_admin=True)
                # Use env var for password if available, else default
                password = os.getenv("ADMIN_PASSWORD", "admin123")
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                print(f"✓ Admin user created. Username: 'admin', Password: '{password}'")
            except Exception as e:
                print(f"❌ Failed to create admin user: {e}")
                db.session.rollback()
        else:
            print("✓ Admin user already exists")

if __name__ == "__main__":
    create_admin()
