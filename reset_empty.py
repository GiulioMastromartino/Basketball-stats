#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.models import User, Organization, Team, OrganizationMembership, TeamAssignment, db
from web import create_app


def reset_empty_database():
    """Reset database without sample data"""
    # Delete existing database
    db_path = Path("basketball_stats.db")
    if db_path.exists():
        db_path.unlink()
        print("✓ Old database deleted")
    
    # Create new database
    app = create_app("development")
    with app.app_context():
        db.create_all()
        print("✓ Database tables created")
        
        # Create org and team
        org = Organization(name="Default Organization")
        db.session.add(org)
        db.session.flush()

        team = Team(name="Default Team", organization_id=org.id, slug="default-team")
        db.session.add(team)
        db.session.flush()

        # Create admin user only
        admin = User(
            username="admin",
            email="admin@local.com",
            organization_id=org.id,
        )
        admin.set_password(os.getenv("ADMIN_PASSWORD", "admin123"))
        db.session.add(admin)
        db.session.flush()

        membership = OrganizationMembership(
            user_id=admin.id, organization_id=org.id, is_gm=True
        )
        db.session.add(membership)

        ta = TeamAssignment(user_id=admin.id, team_id=team.id, is_coach=True)
        db.session.add(ta)

        db.session.commit()
        print("✓ Admin user created (admin/admin123)")
        
        # Create directories
        for folder in [app.config["GAMES_DIR"], app.config["OUTPUT_DIR"]]:
            os.makedirs(folder, exist_ok=True)
        print("✓ Directories created")
    
    print("\n✅ Empty database ready!")
    print("Login: admin / admin123")
    print("\nTo start server: python quick_start.py --run")


if __name__ == "__main__":
    reset_empty_database()
