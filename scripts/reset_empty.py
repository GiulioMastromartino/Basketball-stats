import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from web import create_app
from core.models import (
    db, bcrypt, User, Organization, Team,
    OrganizationMembership, TeamAssignment,
    PlayType, Game, Play,
)


def reset_db():
    app = create_app()
    with app.app_context():
        print("Dropping all tables...")
        db.drop_all()
        print("Creating all tables...")
        db.create_all()

        # Create PlayTypes
        types = ["Offense", "Defense", "Special"]
        for t in types:
            db.session.add(PlayType(name=t))

        # Create Org & Team
        org = Organization(name="Default Organization")
        db.session.add(org)
        db.session.flush()

        team = Team(name="Default Team", organization_id=org.id, slug="default-team")
        db.session.add(team)
        db.session.flush()

        # Create Admin
        print("Creating admin user...")

        admin_email = os.getenv("ADMIN_EMAIL", "admin@local.com")
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")

        hashed_pw = bcrypt.generate_password_hash(admin_pass).decode("utf-8")
        admin = User(
            username=admin_user,
            email=admin_email,
            password_hash=hashed_pw,
            organization_id=org.id,
        )
        db.session.add(admin)
        db.session.flush()

        membership = OrganizationMembership(
            user_id=admin.id, organization_id=org.id, is_gm=True
        )
        db.session.add(membership)

        ta = TeamAssignment(user_id=admin.id, team_id=team.id, is_coach=True)
        db.session.add(ta)

        db.session.commit()
        print(f"Database reset complete. Admin: {admin_user} ({admin_email})")


if __name__ == "__main__":
    reset_db()
