import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core import create_app, db
from core.models import User

def fix_admin_email():
    app = create_app()
    with app.app_context():
        target_email = os.getenv("ADMIN_EMAIL")
        if not target_email:
            print("ERROR: ADMIN_EMAIL environment variable is not set!")
            print("Please check your .env file or export the variable.")
            sys.exit(1)
            
        print(f"Target Email from Env: {target_email}")
        
        # Look for admin by username 'admin'
        admin = User.query.filter_by(username="admin").first()
        
        if not admin:
            print("Admin user 'admin' not found in database.")
            # Try finding by role?
            admin = User.query.filter_by(role='admin').first()
            if admin:
                print(f"Found alternative admin with username: {admin.username}")
        
        if admin:
            print(f"Current Admin Email in DB: {admin.email}")
            if admin.email != target_email:
                admin.email = target_email
                db.session.commit()
                print(f"SUCCESS: Updated Admin Email to: {admin.email}")
            else:
                print("Admin email is already correct.")
        else:
            print("No admin user found to update.")

if __name__ == "__main__":
    fix_admin_email()
