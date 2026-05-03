#!/usr/bin/env python3
"""
Migration: Add players table and populate with existing player names.

This script:
1. Creates the players table if it does not exist
2. Populates it with unique player names from player_stats (idempotent)
3. Sets all players as active by default

Safe to re-run: existing players are never duplicated or overwritten.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.models import db, Player, PlayerStat


def create_app():
    """Create Flask app for database context."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///basketball_stats.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def run_migration():
    """Run the players table migration."""
    app = create_app()

    with app.app_context():
        # Step 1: Create players table if it doesn't exist
        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)

        if "players" not in inspector.get_table_names():
            print("Creating players table...")
            Player.__table__.create(db.engine)
            print("Players table created successfully.")
        else:
            print("Players table already exists, checking population...")

        # Step 2: Get unique player names from player_stats
        print("\nExtracting unique player names from player_stats...")
        player_names = db.session.query(PlayerStat.player_name).distinct().all()
        player_names = [name[0] for name in player_names if name[0]]
        print(f"Found {len(player_names)} unique player names")

        # Step 3: Check existing players
        existing_names = {p.name: p for p in Player.query.all()}
        print(f"Already have {len(existing_names)} players in database")

        # Step 4: Add missing players (always runs — safe due to name check above)
        added_count = 0
        for name in sorted(player_names):
            if name not in existing_names:
                player = Player(name=name, email=None, active=True)
                db.session.add(player)
                added_count += 1
                print(f"  Added: {name}")

        db.session.commit()
        print(f"\nAdded {added_count} new players")

        # Step 5: Activate any players that were created with active=0
        inactive = Player.query.filter_by(active=False).count()
        if inactive > 0:
            print(f"Found {inactive} inactive players — activating all...")
            db.session.execute(
                Player.__table__.update().where(
                    Player.__table__.c.active == False  # noqa: E712
                ).values(active=True)
            )
            db.session.commit()
            print(f"Activated {inactive} players.")

        # Step 6: Verify
        total_players = Player.query.count()
        active_players = Player.query.filter_by(active=True).count()
        print(f"Total players: {total_players} ({active_players} active)")


if __name__ == "__main__":
    run_migration()
