import sys
from pathlib import Path
import os

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core import create_app, db, bcrypt
from core.models import User, PlayType, Game, Play, Player, PlayerGameStats

def quick_start():
    app = create_app()
    with app.app_context():
        # 1. Create Tables
        db.create_all()
        
        # 2. Check/Create PlayTypes
        if not PlayType.query.first():
            types = ["Offense", "Defense", "Special"]
            for t in types:
                db.session.add(PlayType(name=t))
            db.session.commit()
            print("Created PlayTypes")

        # 3. Check/Create Admin
        # Use env vars if available, else defaults
        admin_email = os.getenv("ADMIN_EMAIL", "admin@local.com")
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        
        if not User.query.filter_by(username=admin_user).first():
            hashed_pw = bcrypt.generate_password_hash(admin_pass).decode('utf-8')
            admin = User(
                username=admin_user,
                email=admin_email,
                password_hash=hashed_pw,
                role='admin',
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print(f"Created Admin User: {admin_user} ({admin_email})")
        else:
            print("Admin user already exists")

        print("\nQuick start complete! You can now run 'flask run'")

if __name__ == "__main__":
    quick_start()
