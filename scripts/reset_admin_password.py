import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core import create_app, db, bcrypt
from core.models import User

def reset_admin_password():
    app = create_app()
    with app.app_context():
        # 1. Get password from CLI arg or Env or Default
        if len(sys.argv) > 1:
            new_pass = sys.argv[1]
        else:
            new_pass = os.getenv("ADMIN_PASSWORD", "admin123")
            
        print(f"Resetting admin password to: {new_pass}")
        
        # 2. Find Admin
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        user = User.query.filter_by(username=admin_user).first()
        
        if not user:
            print(f"Error: User '{admin_user}' not found.")
            return

        # 3. Update Password
        user.password_hash = bcrypt.generate_password_hash(new_pass).decode('utf-8')
        db.session.commit()
        print(f"SUCCESS: Password for '{admin_user}' has been updated.")

if __name__ == "__main__":
    reset_admin_password()
