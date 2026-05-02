#!/usr/bin/env python3
"""
Migration: Add players table and populate with existing player names.

This script:
1. Creates the players table
2. Populates it with unique player names from player_stats
3. Sets all players as active by default
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.models import db, Player, PlayerStat


def create_app():
    """Create Flask app for database context."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///basketball_stats.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def run_migration():
    """Run the players table migration."""
    app = create_app()

    with app.app_context():
        # Step 1: Create players table if it doesn't exist
        from sqlalchemy import inspect

        inspector = inspect(db.engine)

        if "players" in inspector.get_table_names():
            print("Players table already exists, skipping creation.")
        else:
            print("Creating players table...")
            Player.__table__.create(db.engine)
            print("Players table created successfully.")

        # Step 2: Get unique player names from player_stats
        print("\nExtracting unique player names from player_stats...")
        player_names = db.session.query(PlayerStat.player_name).distinct().all()

        player_names = [name[0] for name in player_names if name[0]]
        print(f"Found {len(player_names)} unique player names")

        # Step 3: Check existing players
        existing_names = {p.name: p for p in Player.query.all()}
        print(f"Already have {len(existing_names)} players in database")

        # Step 4: Add missing players
        added_count = 0
        for name in sorted(player_names):
            if name not in existing_names:
                player = Player(name=name, email=None, active=True)
                db.session.add(player)
                added_count += 1
                print(f"  Added: {name}")

        db.session.commit()
        print(f"\nAdded {added_count} new players")

        # Step 5: Verify
        total_players = Player.query.count()
        print(f"Total players in database: {total_players}")


if __name__ == "__main__":
    run_migration()
