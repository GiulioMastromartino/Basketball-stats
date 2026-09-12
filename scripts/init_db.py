#!/usr/bin/env python3
"""
Initialize database with all tables from SQLAlchemy models.
Replaces Flask-Migrate for fresh database deployments.

This script:
1. Creates all tables from models (db.create_all)
2. Detects and adds missing columns to existing tables
3. Backfills lineup data to link segments to lineups
4. Backfills players table from player_stats
5. Seeds default data

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
from core.models import (
    db, User, SystemSetting, Game, PlayerStat, Player,
    Play, PlaySequence, PlayType, ShotEvent, GameEvent,
    LineupSegment, Lineup, Possession, ShotZone, PlayerLineupStats,
    Organization, Team, OrganizationMembership, TeamAssignment,
    bcrypt,
)
from sqlalchemy import inspect, text


def add_missing_columns(app):
    """Detect and add missing columns to existing tables."""
    with app.app_context():
        print("\n[Schema Check] Detecting and adding missing columns...")

        inspector = inspect(db.engine)

        # Define columns to check for each table
        # Format: {table_name: {column_name: column_definition}}
        columns_to_add = {
            # Users table
            "users": {
                "organization_id": "INTEGER",
                "workos_id": "VARCHAR(255)",
                "email_verified": "BOOLEAN DEFAULT 0",
                "role": "VARCHAR(20) DEFAULT 'editor'",
                "otp_code": "VARCHAR(6)",
                "otp_expiry": "DATETIME",
            },
            # System settings table
            "system_settings": {
                "organization_id": "INTEGER",
                "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            },
            # Games table
            "games": {
                "team_id": "INTEGER",
                "source": "VARCHAR(20) DEFAULT 'IMPORT'",
                "schema_version": "INTEGER DEFAULT 1",
                "season_id": "INTEGER",
            },
            # Plays table
            "plays": {
                "team_id": "INTEGER",
                "source": "VARCHAR(20) DEFAULT 'imported'",
                "canvas_data": "JSON",
                "diagram_svg": "TEXT",
                "difficulty": "VARCHAR(20) DEFAULT 'Medium'",
                "personnel_required": "TEXT",
                "tags": "TEXT",
            },
            # Game events table
            "game_events": {
                "quarter": "INTEGER",
                "time_remaining": "VARCHAR(10)",
                "score_margin": "INTEGER",
                "possession_number": "INTEGER",
                "game_seconds": "INTEGER",
                "x_loc": "FLOAT",
                "y_loc": "FLOAT",
                "zone": "VARCHAR(50)",
                "lineup_segment_id": "INTEGER",
            },
            # Shot events table
            "shot_events": {
                "zone": "VARCHAR(50)",
            },
            # Play types table
            "play_types": {
                "team_id": "INTEGER",
            },
            # Lineups table - these columns were added in later migrations
            "lineups": {
                "team_id": "INTEGER",
                "fgm": "INTEGER DEFAULT 0",
                "fga": "INTEGER DEFAULT 0",
                "tpm": "INTEGER DEFAULT 0",
                "tpa": "INTEGER DEFAULT 0",
                "ftm": "INTEGER DEFAULT 0",
                "fta": "INTEGER DEFAULT 0",
                "oreb": "INTEGER DEFAULT 0",
                "dreb": "INTEGER DEFAULT 0",
                "ast": "INTEGER DEFAULT 0",
                "stl": "INTEGER DEFAULT 0",
                "blk": "INTEGER DEFAULT 0",
                "tov": "INTEGER DEFAULT 0",
                "reb_conceded": "INTEGER DEFAULT 0",
                "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "last_updated": "DATETIME DEFAULT CURRENT_TIMESTAMP",
            },
            # Lineup segments table - lineup_id links to lineups
            "lineup_segments": {
                "lineup_id": "INTEGER",
                "duration_seconds": "INTEGER DEFAULT 0",
                "reb_conceded": "INTEGER DEFAULT 0",
            },
            # Player lineup stats table
            "player_lineup_stats": {
                "reb_conceded": "INTEGER DEFAULT 0",
            },
            # Player stats table
            "player_stats": {
                "reb_conceded": "INTEGER DEFAULT 0",
            },
            # Players table columns (handles DBs created before email/active were added)
            "players": {
                "team_id": "INTEGER",
                "email": "VARCHAR(120)",
                "active": "BOOLEAN DEFAULT 1",
            },
        }

        columns_added = 0

        for table_name, columns in columns_to_add.items():
            if not inspector.has_table(table_name):
                print(f"  - Table {table_name} does not exist, skipping column check")
                continue

            existing_cols = [c["name"] for c in inspector.get_columns(table_name)]

            for col_name, col_def in columns.items():
                if col_name not in existing_cols:
                    try:
                        sql = (
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
                        )
                        db.session.execute(text(sql))
                        db.session.commit()
                        print(f"  + Added column {col_name} to {table_name}")
                        columns_added += 1
                    except Exception as e:
                        # Column might already exist (race condition) or other error
                        db.session.rollback()
                        pass

        if columns_added > 0:
            print(f"  ✓ Added {columns_added} missing columns")
        else:
            print("  ✓ All columns up to date")


def add_notification_columns(app):
    """Add notification channel columns to users and players tables.

    Safe to re-run — uses inspect() to check for column existence before ALTER.
    The whatsapp_groups table is handled by db.create_all() via the model.
    """
    with app.app_context():
        print("[Schema Check] Adding notification columns...")
        inspector = inspect(db.engine)

        with db.engine.connect() as conn:
            user_cols = {c["name"] for c in inspector.get_columns("users")}
            if "notification_channel" not in user_cols:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN notification_channel "
                    "VARCHAR(20) DEFAULT 'email'"
                ))
                conn.execute(text(
                    "UPDATE users SET notification_channel = 'email' "
                    "WHERE notification_channel IS NULL"
                ))
                conn.commit()
                print("  ✓ Added notification_channel to users")
            if "whatsapp_phone" not in user_cols:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN whatsapp_phone VARCHAR(20) DEFAULT NULL"
                ))
                conn.commit()
                print("  ✓ Added whatsapp_phone to users")

            player_cols = {c["name"] for c in inspector.get_columns("players")}
            if "notification_channel" not in player_cols:
                conn.execute(text(
                    "ALTER TABLE players ADD COLUMN notification_channel "
                    "VARCHAR(20) DEFAULT 'email'"
                ))
                conn.execute(text(
                    "UPDATE players SET notification_channel = 'email' "
                    "WHERE notification_channel IS NULL"
                ))
                conn.commit()
                print("  ✓ Added notification_channel to players")
            if "whatsapp_phone" not in player_cols:
                conn.execute(text(
                    "ALTER TABLE players ADD COLUMN whatsapp_phone VARCHAR(20) DEFAULT NULL"
                ))
                conn.commit()
                print("  ✓ Added whatsapp_phone to players")


def backfill_lineups(app):
    """Backfill lineup data - create lineups and link segments."""
    with app.app_context():
        print("\n[Backfill] Linking lineup segments to lineups...")

        inspector = inspect(db.engine)

        # Check if lineup_id column exists in lineup_segments
        if inspector.has_table("lineup_segments"):
            cols = [c["name"] for c in inspector.get_columns("lineup_segments")]
            if "lineup_id" not in cols:
                print("  ! lineup_id column missing, skipping backfill")
                return

        # Check if lineups table exists
        if not inspector.has_table("lineups"):
            print("  ! lineups table missing, skipping backfill")
            return

        # Get segments without lineup_id
        segments = LineupSegment.query.filter(
            (LineupSegment.lineup_id == None) | (LineupSegment.lineup_id == 0)
        ).all()

        if not segments:
            # Also check for segments with lineup_id = 0 (invalid)
            zero_linked = LineupSegment.query.filter(
                LineupSegment.lineup_id == 0
            ).count()
            if zero_linked > 0:
                print(f"  ! Found {zero_linked} segments with invalid lineup_id=0")

            print("  ✓ All lineup segments already linked")
            return

        print(f"  Found {len(segments)} segments to link...")

        # Get existing lineups
        lineup_cache = {}
        existing_lineups = Lineup.query.all()
        for lineup in existing_lineups:
            lineup_cache[lineup.lineup_hash] = lineup.id
        print(f"  Found {len(existing_lineups)} existing lineups")

        created_count = 0
        linked_count = 0

        for i, segment in enumerate(segments, 1):
            try:
                lineup_hash = segment.lineup_hash

                # Parse players if stored as string
                players = segment.players
                if isinstance(players, str):
                    import json

                    try:
                        players = json.loads(players)
                    except:
                        players = []

                # Create lineup if doesn't exist
                if lineup_hash not in lineup_cache:
                    lineup = Lineup(
                        lineup_hash=lineup_hash,
                        players=sorted(players) if players else [],
                        is_starting=(created_count == 0),
                    )
                    db.session.add(lineup)
                    db.session.flush()
                    lineup_cache[lineup_hash] = lineup.id
                    created_count += 1

                # Link segment to lineup
                segment.lineup_id = lineup_cache[lineup_hash]
                linked_count += 1

                if i % 100 == 0:
                    db.session.commit()
                    print(f"    Processed {i}/{len(segments)} segments...")

            except Exception as e:
                print(f"    Error processing segment {segment.id}: {e}")
                db.session.rollback()

        db.session.commit()

        # Update cached stats for all lineups
        print("  Updating lineup cached stats...")
        try:
            from core.services.lineup_service import update_lineup_cached_stats

            all_lineups = Lineup.query.all()
            for lineup in all_lineups:
                try:
                    update_lineup_cached_stats(lineup.id)
                except Exception as e:
                    pass  # Stats calculation might fail for empty lineups
        except ImportError:
            print("  ! Could not import lineup_service, skipping stats update")

        print(
            f"  ✓ Created {created_count} new lineups, linked {linked_count} segments"
        )


def add_indexes_if_missing(app):
    """Ensure all required indexes exist."""
    with app.app_context():
        print("\n[Indexes] Checking for missing indexes...")

        inspector = inspect(db.engine)

        indexes_to_create = [
            ("idx_playerstats_player_name", "player_stats", "player_name"),
            ("idx_playerstats_game_id", "player_stats", "game_id"),
            ("idx_playerstats_minutes", "player_stats", "minutes"),
            ("idx_games_sort_date", "games", "sort_date"),
            ("idx_games_game_type", "games", "game_type"),
            ("idx_games_opponent", "games", "opponent"),
            ("idx_games_result", "games", "result"),
            ("idx_playerstats_game_player", "player_stats", "game_id, player_name"),
            ("idx_games_type_date", "games", "game_type, sort_date"),
            # Advanced analytics indexes
            ("idx_lineups_hash", "lineups", "lineup_hash"),
            ("idx_lineups_net_rating", "lineups", "net_rating"),
            ("idx_lineup_segments_game_id", "lineup_segments", "game_id"),
            ("idx_lineup_segments_hash", "lineup_segments", "lineup_hash"),
            ("idx_lineup_segments_lineup_id", "lineup_segments", "lineup_id"),
            ("idx_possessions_game_id", "possessions", "game_id"),
            (
                "idx_player_lineup_stats_segment",
                "player_lineup_stats",
                "lineup_segment_id",
            ),
            ("idx_player_lineup_stats_player", "player_lineup_stats", "player_name"),
        ]

        # Get existing indexes
        existing_indexes = {}
        for table_name in inspector.get_table_names():
            for idx in inspector.get_indexes(table_name):
                existing_indexes[idx["name"]] = table_name

        indexes_created = 0
        for idx_name, table_name, columns in indexes_to_create:
            if table_name not in inspector.get_table_names():
                continue

            if idx_name not in existing_indexes:
                try:
                    sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name}({columns})"
                    db.session.execute(text(sql))
                    db.session.commit()
                    print(f"  + Created index {idx_name}")
                    indexes_created += 1
                except Exception as e:
                    db.session.rollback()
                    pass

        if indexes_created > 0:
            print(f"  ✓ Created {indexes_created} missing indexes")
        else:
            print("  ✓ All indexes up to date")


def backfill_players(app):
    """Ensure all player names from player_stats exist in the players table.

    This is idempotent: safe to run on fresh DBs (no-op) and on existing DBs
    that pre-date the Player model (populates the table from player_stats names).
    analytics_service.build_player_detail() depends on Player rows existing.
    """
    with app.app_context():
        print("\n[Players] Syncing players table from player_stats...")

        inspector = inspect(db.engine)
        if not inspector.has_table("players"):
            print("  ! players table missing — will be created by db.create_all()")
            return

        # Collect unique names already in players
        existing_names = {p.name for p in Player.query.all()}

        # Pull distinct names from player_stats
        distinct = db.session.query(PlayerStat.player_name).distinct().all()
        names_to_add = [
            row[0] for row in distinct if row[0] and row[0] not in existing_names
        ]

        if not names_to_add:
            print("  ✓ Players table already in sync")
            return

        for name in sorted(names_to_add):
            db.session.add(Player(name=name, email=None, active=True))

        db.session.commit()
        print(
            f"  ✓ Added {len(names_to_add)} players: {', '.join(sorted(names_to_add))}"
        )


def seed_default_data(app):
    """Seed default data if not exists."""
    with app.app_context():
        print("\n[Seeding] Checking default data...")

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

        # Seed default organization and team
        print("\n[Multi-Tenant] Setting up default organization and team...")
        org_name = os.getenv("DEFAULT_ORG_NAME", "Default Organization")
        team_name = os.getenv("DEFAULT_TEAM_NAME", "Default Team")

        org = Organization.query.filter_by(name=org_name).first()
        if not org:
            org = Organization(name=org_name)
            db.session.add(org)
            db.session.flush()
            print(f"  ✓ Created organization: {org_name}")
        else:
            print(f"  ✓ Organization already exists: {org_name}")

        team = Team.query.filter_by(name=team_name, organization_id=org.id).first()
        if not team:
            team = Team(name=team_name, organization_id=org.id, slug="default-team")
            db.session.add(team)
            db.session.flush()
            print(f"  ✓ Created team: {team_name}")
        else:
            print(f"  ✓ Team already exists: {team_name}")
        db.session.commit()

        # Create admin user if not exists
        print("\n[Admin] Setting up admin user...")
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

        if not admin_email:
            print("  ⚠ ADMIN_EMAIL not set, skipping admin creation")
        else:
            user = User.query.filter_by(email=admin_email).first()
            if not user:
                user = User.query.filter_by(username=admin_username).first()

            needs_org_membership = True
            if not user:
                hashed_pw = bcrypt.generate_password_hash(admin_password).decode(
                    "utf-8"
                )
                new_admin = User(
                    username=admin_username,
                    email=admin_email,
                    password_hash=hashed_pw,
                    organization_id=org.id,
                )
                db.session.add(new_admin)
                db.session.flush()
                print(f"  ✓ Created admin user: {admin_email}")
                user = new_admin
            else:
                user.email = admin_email
                user.organization_id = org.id
                if admin_password:
                    user.password_hash = bcrypt.generate_password_hash(
                        admin_password
                    ).decode("utf-8")
                # Check if already has membership
                existing_membership = OrganizationMembership.query.filter_by(
                    user_id=user.id, organization_id=org.id
                ).first()
                if existing_membership:
                    needs_org_membership = False
                db.session.commit()
                print(f"  ✓ Updated admin user: {admin_email}")

            # Ensure GM membership for admin
            if needs_org_membership:
                membership = OrganizationMembership(
                    user_id=user.id,
                    organization_id=org.id,
                    is_gm=True,
                )
                db.session.add(membership)
                db.session.flush()

            # Ensure team assignment
            existing_ta = TeamAssignment.query.filter_by(
                user_id=user.id, team_id=team.id
            ).first()
            if not existing_ta:
                ta = TeamAssignment(user_id=user.id, team_id=team.id, is_coach=True)
                db.session.add(ta)

            db.session.commit()
            print(f"  ✓ Admin user is GM of {org_name} and coach of {team_name}")


def init_database():
    """Main initialization function."""
    app = create_app(os.getenv("FLASK_ENV", "development"))

    with app.app_context():
        print("=" * 60)
        print("Initializing database...")
        print("=" * 60)

        # Step 1: Create all tables from models
        print("\n[1/6] Creating tables from models...")
        db.create_all()
        print("  ✓ All tables created")

        # Step 2: Add missing columns to existing tables
        add_missing_columns(app)

        # Step 3: Add missing indexes
        add_indexes_if_missing(app)

        # Step 4: Backfill lineup data
        backfill_lineups(app)

        # Step 5: Backfill players table from player_stats
        backfill_players(app)

        # Step 6: Seed default data
        seed_default_data(app)

        print("\n" + "=" * 60)
        print("Database initialization complete!")
        print("=" * 60)

        # List all tables
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\nTables ({len(tables)}):")
        for t in sorted(tables):
            print(f"  - {t}")


if __name__ == "__main__":
    init_database()
