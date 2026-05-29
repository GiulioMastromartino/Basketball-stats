#!/usr/bin/env python3
"""
Multi-tenant migration: creates organizations, teams, and assigns existing
users/data to a default org.

Run: python scripts/migrate_multi_tenant.py
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from config import get_config
from core.models import (
    db, Organization, Team, OrganizationMembership, TeamAssignment,
    User, Game, Play, PlayType, Lineup, Player, SystemSetting,
    PlaySequence, ShotEvent, GameEvent, LineupSegment, Possession,
    PlayerLineupStats, ShotZone,
)


def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config(os.getenv("FLASK_ENV", "development")))
    db.init_app(app)
    return app


def migrate():
    app = create_app()
    with app.app_context():
        db.create_all()

        # Check if already migrated
        existing_org = Organization.query.first()
        if existing_org:
            print(f"[SKIP] Organization '{existing_org.name}' already exists. Migration already completed.")
            return

        print("=== Multi-Tenant Migration ===\n")

        # Step 1: Create default organization
        print("[1/6] Creating default organization...")
        org = Organization(name="Default Organization", slug="default", created_at=datetime.utcnow())
        db.session.add(org)
        db.session.flush()
        print(f"  Created organization: {org.name} (id={org.id})")

        # Step 2: Create default team
        print("[2/6] Creating default team...")
        team = Team(
            organization_id=org.id,
            name="Default Team",
            slug="default",
            created_at=datetime.utcnow(),
        )
        db.session.add(team)
        db.session.flush()
        print(f"  Created team: {team.name} (id={team.id})")

        # Step 3: Assign all existing users
        print("[3/6] Assigning users to organization...")
        users = User.query.all()
        for user in users:
            user.organization_id = org.id
            membership = OrganizationMembership(
                user_id=user.id,
                organization_id=org.id,
                is_gm=True,
                created_at=datetime.utcnow(),
            )
            db.session.add(membership)
            print(f"  User '{user.username}' → GM of '{org.name}'")
        db.session.flush()

        # Step 4: Assign all existing games
        print("[4/6] Assigning games to default team...")
        for game in Game.query.all():
            game.team_id = team.id
        count = Game.query.count()
        print(f"  {count} games assigned to team '{team.name}'")

        # Step 5: Assign plays, play_types, lineups, players
        print("[5/6] Assigning plays, play types, lineups, and players...")

        for play in Play.query.all():
            play.team_id = team.id
        print(f"  {Play.query.count()} plays")

        for pt in PlayType.query.all():
            pt.team_id = team.id
        print(f"  {PlayType.query.count()} play types")

        for lineup in Lineup.query.all():
            lineup.team_id = team.id
        print(f"  {Lineup.query.count()} lineups")

        for player in Player.query.all():
            player.team_id = team.id
        print(f"  {Player.query.count()} players")

        for setting in SystemSetting.query.all():
            setting.organization_id = org.id
        print(f"  {SystemSetting.query.count()} system settings")

        # Step 6: Commit
        print("\n[6/6] Committing migration...")
        db.session.commit()
        print("  Migration completed successfully!")

        print(f"\n=== Summary ===")
        print(f"  Organization: {org.name} (slug: {org.slug})")
        print(f"  Team: {team.name} (slug: {team.slug})")
        print(f"  Users: {len(users)}")
        print(f"  Games: {count}")
        print(f"  All existing data assigned to default org/team.")


if __name__ == "__main__":
    migrate()
