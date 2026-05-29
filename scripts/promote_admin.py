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
from core.models import User, Organization, Team, OrganizationMembership, TeamAssignment, db


def promote_admin():
    """Promote user with ADMIN_EMAIL to admin."""
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        print("No ADMIN_EMAIL set, skipping admin promotion.")
        return
    
    app = create_app()
    
    with app.app_context():
        user = User.query.filter_by(email=admin_email).first()

        if not user:
            print(f"User with email {admin_email} not found yet.")
            return

        # Ensure a default org exists
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

        user.organization_id = org.id

        membership = OrganizationMembership.query.filter_by(
            user_id=user.id, organization_id=org.id
        ).first()
        if not membership:
            membership = OrganizationMembership(
                user_id=user.id, organization_id=org.id, is_gm=True
            )
            db.session.add(membership)
            print(f"Promoted {user.email} to GM role.")
        else:
            membership.is_gm = True
            print(f"User {user.email} is already GM.")

        ta = TeamAssignment.query.filter_by(user_id=user.id, team_id=team.id).first()
        if not ta:
            ta = TeamAssignment(user_id=user.id, team_id=team.id, is_coach=True)
            db.session.add(ta)

        db.session.commit()


if __name__ == "__main__":
    promote_admin()
