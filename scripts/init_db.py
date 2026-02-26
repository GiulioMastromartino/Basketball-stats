#!/usr/bin/env python3
"""
Initialize database with all tables from SQLAlchemy models.
Replaces Flask-Migrate for fresh database deployments.

Usage:
    python scripts/init_db.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from web import create_app
from core.models import db, User, SystemSetting, Game, PlayerStat
from core.models import Play, PlaySequence, PlayType, ShotEvent, GameEvent
from core.models import LineupSegment, Lineup, Possession, ShotZone, PlayerLineupStats
from core.models import bcrypt


def init_database():
    """Create all tables and seed default data."""
    app = create_app(os.getenv("FLASK_ENV", "development"))

    with app.app_context():
        print("=" * 50)
        print("Initializing database...")
        print("=" * 50)

        # 1. Create all tables from models
        print("\n[1/4] Creating tables from models...")
        db.create_all()
        print("  ✓ All tables created")

        # 2. Create indexes for performance
        print("\n[2/4] Creating performance indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_playerstats_player_name ON player_stats(player_name)",
            "CREATE INDEX IF NOT EXISTS idx_playerstats_game_id ON player_stats(game_id)",
            "CREATE INDEX IF NOT EXISTS idx_playerstats_minutes ON player_stats(minutes)",
            "CREATE INDEX IF NOT EXISTS idx_games_sort_date ON games(sort_date)",
            "CREATE INDEX IF NOT EXISTS idx_games_game_type ON games(game_type)",
            "CREATE INDEX IF NOT EXISTS idx_games_opponent ON games(opponent)",
            "CREATE INDEX IF NOT EXISTS idx_games_result ON games(result)",
            "CREATE INDEX IF NOT EXISTS idx_playerstats_game_player ON player_stats(game_id, player_name)",
            "CREATE INDEX IF NOT EXISTS idx_games_type_date ON games(game_type, sort_date)",
            # Advanced analytics indexes
            "CREATE INDEX IF NOT EXISTS idx_lineups_hash ON lineups(lineup_hash)",
            "CREATE INDEX IF NOT EXISTS idx_lineups_net_rating ON lineups(net_rating)",
            "CREATE INDEX IF NOT EXISTS idx_lineup_segments_game_id ON lineup_segments(game_id)",
            "CREATE INDEX IF NOT EXISTS idx_lineup_segments_hash ON lineup_segments(lineup_hash)",
            "CREATE INDEX IF NOT EXISTS idx_lineup_segments_lineup_id ON lineup_segments(lineup_id)",
            "CREATE INDEX IF NOT EXISTS idx_possessions_game_id ON possessions(game_id)",
            "CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_segment ON player_lineup_stats(lineup_segment_id)",
            "CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_player ON player_lineup_stats(player_name)",
        ]

        from sqlalchemy import text

        for idx_sql in indexes:
            try:
                db.session.execute(text(idx_sql))
            except Exception as e:
                # Index might already exist, continue
                pass
        db.session.commit()
        print("  ✓ Indexes created")

        # 3. Seed default data
        print("\n[3/4] Seeding default data...")

        # Seed PlayTypes
        if not PlayType.query.first():
            play_types = ["Offense", "Defense", "Special"]
            for pt in play_types:
                db.session.add(PlayType(name=pt))
            db.session.commit()
            print(f"  ✓ Seeded PlayTypes: {', '.join(play_types)}")
        else:
            print("  ✓ PlayTypes already exist")

        # Seed ShotZones
        if not ShotZone.query.first():
            shot_zones = [
                ShotZone(
                    zone_name="Rim",
                    zone_type="Paint",
                    expected_value=1.20,
                    description="Layups and dunks at the basket",
                    x_min=210,
                    x_max=290,
                    y_min=0,
                    y_max=100,
                ),
                ShotZone(
                    zone_name="Paint",
                    zone_type="Paint",
                    expected_value=0.85,
                    description="Shots in the paint (non-rim)",
                    x_min=150,
                    x_max=350,
                    y_min=0,
                    y_max=150,
                ),
                ShotZone(
                    zone_name="Midrange",
                    zone_type="Midrange",
                    expected_value=0.75,
                    description="Mid-range jumpers",
                    x_min=0,
                    x_max=500,
                    y_min=100,
                    y_max=350,
                ),
                ShotZone(
                    zone_name="Corner_3",
                    zone_type="Corner_3",
                    expected_value=1.10,
                    description="Corner 3-pointers",
                    x_min=0,
                    x_max=500,
                    y_min=0,
                    y_max=100,
                ),
                ShotZone(
                    zone_name="Above_Break_3",
                    zone_type="Above_Break_3",
                    expected_value=1.05,
                    description="Above-the-break 3-pointers",
                    x_min=0,
                    x_max=500,
                    y_min=300,
                    y_max=470,
                ),
                ShotZone(
                    zone_name="FT",
                    zone_type="FT",
                    expected_value=0.75,
                    description="Free throws",
                    x_min=None,
                    x_max=None,
                    y_min=None,
                    y_max=None,
                ),
            ]
            for sz in shot_zones:
                db.session.add(sz)
            db.session.commit()
            print("  ✓ Seeded ShotZones (6 zones)")
        else:
            print("  ✓ ShotZones already exist")

        # 4. Create admin user if not exists
        print("\n[4/4] Setting up admin user...")
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

        if not admin_email:
            print("  ⚠ ADMIN_EMAIL not set, skipping admin creation")
        else:
            user = User.query.filter_by(email=admin_email).first()
            if not user:
                # Check by username too
                user = User.query.filter_by(username=admin_username).first()

            if not user:
                hashed_pw = bcrypt.generate_password_hash(admin_password).decode(
                    "utf-8"
                )
                new_admin = User(
                    username=admin_username,
                    email=admin_email,
                    password_hash=hashed_pw,
                    role="admin",
                    is_admin=True,
                )
                db.session.add(new_admin)
                db.session.commit()
                print(f"  ✓ Created admin user: {admin_email}")
            else:
                # Update email and ensure admin role
                user.email = admin_email
                user.role = "admin"
                user.is_admin = True
                if admin_password:
                    user.password_hash = bcrypt.generate_password_hash(
                        admin_password
                    ).decode("utf-8")
                db.session.commit()
                print(f"  ✓ Updated admin user: {admin_email}")

        print("\n" + "=" * 50)
        print("Database initialization complete!")
        print("=" * 50)

        # List all tables
        from sqlalchemy import inspect

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\nTables created ({len(tables)}):")
        for t in sorted(tables):
            print(f"  - {t}")


if __name__ == "__main__":
    init_database()
