#!/usr/bin/env python3
"""
Promote user with ADMIN_EMAIL to admin role.
Run on startup to ensure admin access.
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from web import create_app
from core.models import User, db


def promote_admin():
    """Promote user with ADMIN_EMAIL to admin."""
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        print("No ADMIN_EMAIL set, skipping admin promotion.")
        return
    
    app = create_app()
    
    with app.app_context():
        user = User.query.filter_by(email=admin_email).first()
        
        if user:
            if user.role != "admin":
                user.role = "admin"
                user.is_admin = True
                db.session.commit()
                print(f"Promoted {user.email} to admin role.")
            else:
                print(f"User {user.email} is already admin.")
        else:
            print(f"User with email {admin_email} not found yet.")


if __name__ == "__main__":
    promote_admin()
