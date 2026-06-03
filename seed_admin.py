import os
import sys
from pathlib import Path

# Ensure the current directory is in the path so imports work
sys.path.append(str(Path(__file__).parent))

from core.models import User, Organization, Team, OrganizationMembership, TeamAssignment, db
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
                password = os.getenv("ADMIN_PASSWORD", "admin123")

                org = Organization.query.first()
                if not org:
                    org = Organization(name="Default Organization")
                    db.session.add(org)
                    db.session.flush()

                team = Team.query.filter_by(organization_id=org.id).first()
                if not team:
                    team = Team(name="Default Team", organization_id=org.id, slug="default-team")
                    db.session.add(team)
                    db.session.flush()

                admin = User(
                    username="admin",
                    email="admin@local.com",
                    organization_id=org.id,
                )
                admin.set_password(password)
                db.session.add(admin)
                db.session.flush()

                membership = OrganizationMembership(
                    user_id=admin.id, organization_id=org.id, is_gm=True
                )
                db.session.add(membership)

                ta = TeamAssignment(user_id=admin.id, team_id=team.id, is_coach=True)
                db.session.add(ta)

                db.session.commit()
                print(f"✓ Admin user created. Username: 'admin', Password: '{password}'")
            except Exception as e:
                print(f"❌ Failed to create admin user: {e}")
                db.session.rollback()
        else:
            print("✓ Admin user already exists")

if __name__ == "__main__":
    create_admin()
