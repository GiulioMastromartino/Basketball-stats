import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core import create_app, db, bcrypt
from core.models import User, PlayType

def seed_db():
    app = create_app()
    with app.app_context():
        print("Seeding database...")
        
        # 1. Seed PlayTypes
        if not PlayType.query.first():
            types = ["Offense", "Defense", "Special"]
            for t_name in types:
                db.session.add(PlayType(name=t_name))
            db.session.commit()
            print(f"Seeded default PlayTypes: {', '.join(types)}")
            
        # 2. Seed/Fix Admin
        env_email = os.getenv("ADMIN_EMAIL")
        env_user = os.getenv("ADMIN_USERNAME", "admin")
        env_pass = os.getenv("ADMIN_PASSWORD")
        
        # Fallbacks
        final_email = env_email or "admin@local.com"
        final_pass = env_pass or "admin123"
        
        user = User.query.filter_by(username=env_user).first()
        
        if not user:
            print(f"Seeding NEW admin...")
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
            print("="*40)
            print(f"ADMIN CREATED -> User: {env_user}")
            print("="*40)
        else:
            updates = False
            # Sync Email
            if env_email and user.email != env_email:
                 user.email = env_email
                 updates = True
                 print(f"-> Syncing Admin Email to: {env_email}")
            
            # Sync Password
            if env_pass:
                 if not user.check_password(env_pass):
                     user.password_hash = bcrypt.generate_password_hash(env_pass).decode('utf-8')
                     updates = True
                     print(f"-> Syncing Admin Password to env variable")
            
            if updates:
                db.session.commit()
                print("Admin credentials synchronized.")
            else:
                print("Admin credentials already up to date.")

if __name__ == "__main__":
    seed_db()
