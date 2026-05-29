"""
Test the production migration script (scripts/migrate.py).

Verifies that migrate.py correctly upgrades an existing database
that was created before schema changes (e.g. adding team_id, organization_id).
This catches the scenario where db.create_all() creates new tables but
does not add columns to existing tables — which causes 500 errors in production.

Each test creates an isolated in-memory SQLite database with only the
"old" schema — without multi-tenant tables — then runs migrate.py and
asserts the new schema is present.
"""

import os
import sys
import pytest
from datetime import datetime
from sqlalchemy import inspect, MetaData, Table, Column, String, Integer, Boolean, Float, DateTime, JSON, Text, BigInteger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _build_old_tables():
    """Build the old schema table definitions as lists of column kwargs.
    Returns a dict of {table_name: [column_kwargs, ...]}.
    Each test gets fresh Column objects so they can be reused across fixtures.
    """
    return {
        "users": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "username", "type_": String(80), "unique": True, "nullable": False},
            {"name": "email", "type_": String(120), "unique": True, "nullable": False},
            {"name": "password_hash", "type_": String(255)},
            {"name": "workos_id", "type_": String(255)},
            {"name": "email_verified", "type_": Boolean, "default": False},
            {"name": "otp_code", "type_": String(6)},
            {"name": "otp_expiry", "type_": DateTime},
            {"name": "is_admin", "type_": Boolean, "default": False},
        ],
        "games": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "date", "type_": String(10), "nullable": False},
            {"name": "opponent", "type_": String(100), "nullable": False},
            {"name": "team_score", "type_": Integer, "nullable": False},
            {"name": "opponent_score", "type_": Integer, "nullable": False},
            {"name": "result", "type_": String(1), "nullable": False},
            {"name": "game_type", "type_": String(20), "nullable": False},
            {"name": "sort_date", "type_": String(10), "nullable": False},
            {"name": "source", "type_": String(20), "default": "IMPORT"},
            {"name": "schema_version", "type_": Integer, "default": 1},
        ],
        "player_stats": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "game_id", "type_": Integer, "nullable": False},
            {"name": "player_name", "type_": String(100)},
            {"name": "minutes", "type_": String(10)},
            {"name": "points", "type_": Integer, "default": 0},
            {"name": "fgm", "type_": Integer, "default": 0},
            {"name": "fga", "type_": Integer, "default": 0},
            {"name": "fg_percent", "type_": Float, "default": 0.0},
            {"name": "tpm", "type_": Integer, "default": 0},
            {"name": "tpa", "type_": Integer, "default": 0},
            {"name": "tp_percent", "type_": Float, "default": 0.0},
            {"name": "ftm", "type_": Integer, "default": 0},
            {"name": "fta", "type_": Integer, "default": 0},
            {"name": "ft_percent", "type_": Float, "default": 0.0},
            {"name": "oreb", "type_": Integer, "default": 0},
            {"name": "dreb", "type_": Integer, "default": 0},
            {"name": "reb", "type_": Integer, "default": 0},
            {"name": "ast", "type_": Integer, "default": 0},
            {"name": "stl", "type_": Integer, "default": 0},
            {"name": "blk", "type_": Integer, "default": 0},
            {"name": "tov", "type_": Integer, "default": 0},
            {"name": "pf", "type_": Integer, "default": 0},
            {"name": "plus_minus", "type_": Integer, "default": 0},
            {"name": "reb_conceded", "type_": Integer, "default": 0},
        ],
        "plays": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "name", "type_": String(100), "unique": True, "nullable": False},
            {"name": "description", "type_": Text},
            {"name": "play_type", "type_": String(50), "default": "Offense"},
            {"name": "source", "type_": String(20), "default": "imported"},
            {"name": "image_filename", "type_": String(255)},
            {"name": "created_at", "type_": DateTime},
            {"name": "updated_at", "type_": DateTime},
            {"name": "canvas_data", "type_": JSON},
            {"name": "diagram_svg", "type_": Text},
            {"name": "difficulty", "type_": String(20)},
            {"name": "personnel_required", "type_": Text},
            {"name": "tags", "type_": Text},
        ],
        "play_types": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "name", "type_": String(50), "unique": True, "nullable": False},
        ],
        "players": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "name", "type_": String(100), "unique": True, "nullable": False},
            {"name": "email", "type_": String(120)},
            {"name": "active", "type_": Boolean, "default": True},
            {"name": "created_at", "type_": DateTime},
        ],
        "lineups": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "lineup_hash", "type_": String(64), "unique": True, "nullable": False},
            {"name": "players", "type_": JSON, "nullable": False},
            {"name": "display_name", "type_": String(100)},
            {"name": "is_starting", "type_": Boolean, "default": False},
            {"name": "total_seconds", "type_": Integer, "default": 0},
            {"name": "total_possessions", "type_": Integer, "default": 0},
            {"name": "points_scored", "type_": Integer, "default": 0},
            {"name": "points_allowed", "type_": Integer, "default": 0},
            {"name": "games_played", "type_": Integer, "default": 0},
            {"name": "segment_count", "type_": Integer, "default": 0},
            {"name": "ortg", "type_": Float, "default": 0},
            {"name": "drtg", "type_": Float, "default": 0},
            {"name": "net_rating", "type_": Float, "default": 0},
            {"name": "fgm", "type_": Integer, "default": 0},
            {"name": "fga", "type_": Integer, "default": 0},
            {"name": "tpm", "type_": Integer, "default": 0},
            {"name": "tpa", "type_": Integer, "default": 0},
            {"name": "ftm", "type_": Integer, "default": 0},
            {"name": "fta", "type_": Integer, "default": 0},
            {"name": "oreb", "type_": Integer, "default": 0},
            {"name": "dreb", "type_": Integer, "default": 0},
            {"name": "ast", "type_": Integer, "default": 0},
            {"name": "stl", "type_": Integer, "default": 0},
            {"name": "blk", "type_": Integer, "default": 0},
            {"name": "tov", "type_": Integer, "default": 0},
            {"name": "pf", "type_": Integer, "default": 0},
            {"name": "reb_conceded", "type_": Integer, "default": 0},
            {"name": "created_at", "type_": DateTime},
            {"name": "last_updated", "type_": DateTime},
        ],
        "system_settings": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "key", "type_": String(50), "unique": True, "nullable": False},
            {"name": "value", "type_": String(255)},
            {"name": "description", "type_": String(255)},
        ],
        "shot_events": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "game_id", "type_": Integer, "nullable": False},
            {"name": "player_name", "type_": String(100)},
            {"name": "shot_type", "type_": String(10)},
            {"name": "result", "type_": String(10)},
            {"name": "points", "type_": Integer, "default": 0},
            {"name": "x_loc", "type_": Float},
            {"name": "y_loc", "type_": Float},
            {"name": "zone", "type_": String(50)},
            {"name": "quarter", "type_": Integer},
            {"name": "play_id", "type_": Integer},
        ],
        "game_events": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "game_id", "type_": Integer, "nullable": False},
            {"name": "event_type", "type_": String(50)},
            {"name": "player_name", "type_": String(100)},
            {"name": "detail", "type_": String(255)},
            {"name": "timestamp", "type_": BigInteger, "default": 0},
            {"name": "shot_attempt", "type_": String(10)},
            {"name": "play_id", "type_": Integer},
            {"name": "quarter", "type_": Integer},
            {"name": "time_remaining", "type_": String(10)},
            {"name": "score_margin", "type_": Integer},
            {"name": "possession_number", "type_": Integer},
            {"name": "game_seconds", "type_": Integer},
            {"name": "x_loc", "type_": Float},
            {"name": "y_loc", "type_": Float},
            {"name": "zone", "type_": String(50)},
            {"name": "lineup_segment_id", "type_": Integer},
        ],
        "lineup_segments": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "game_id", "type_": Integer, "nullable": False},
            {"name": "start_timestamp", "type_": BigInteger, "nullable": False},
            {"name": "end_timestamp", "type_": BigInteger},
            {"name": "quarter", "type_": Integer},
            {"name": "players", "type_": JSON, "nullable": False},
            {"name": "lineup_hash", "type_": String(64), "nullable": False},
            {"name": "points_scored", "type_": Integer, "default": 0},
            {"name": "points_allowed", "type_": Integer, "default": 0},
            {"name": "possessions", "type_": Integer, "default": 0},
            {"name": "reb_conceded", "type_": Integer, "default": 0},
            {"name": "duration_seconds", "type_": Integer, "default": 0},
            {"name": "lineup_id", "type_": Integer},
        ],
        "possessions": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "game_id", "type_": Integer, "nullable": False},
            {"name": "start_event_id", "type_": Integer, "nullable": False},
            {"name": "end_event_id", "type_": Integer},
            {"name": "team_possession", "type_": Boolean, "default": True},
            {"name": "quarter", "type_": Integer},
            {"name": "points", "type_": Integer, "default": 0},
            {"name": "play_id", "type_": Integer},
        ],
        "shot_zones": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "zone_name", "type_": String(50), "unique": True, "nullable": False},
            {"name": "zone_type", "type_": String(20), "nullable": False},
            {"name": "expected_value", "type_": Float, "nullable": False},
            {"name": "description", "type_": String(255)},
            {"name": "x_min", "type_": Float},
            {"name": "x_max", "type_": Float},
            {"name": "y_min", "type_": Float},
            {"name": "y_max", "type_": Float},
        ],
        "play_sequences": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "play_id", "type_": Integer, "nullable": False},
            {"name": "sequence_number", "type_": Integer, "nullable": False},
            {"name": "element_data", "type_": JSON},
            {"name": "caption", "type_": String(255)},
        ],
        "player_lineup_stats": [
            {"name": "id", "type_": Integer, "primary_key": True},
            {"name": "lineup_segment_id", "type_": Integer, "nullable": False},
            {"name": "player_name", "type_": String(100), "nullable": False},
            {"name": "points", "type_": Integer, "default": 0},
            {"name": "fga", "type_": Integer, "default": 0},
            {"name": "fgm", "type_": Integer, "default": 0},
            {"name": "tpa", "type_": Integer, "default": 0},
            {"name": "tpm", "type_": Integer, "default": 0},
            {"name": "fta", "type_": Integer, "default": 0},
            {"name": "ftm", "type_": Integer, "default": 0},
            {"name": "oreb", "type_": Integer, "default": 0},
            {"name": "dreb", "type_": Integer, "default": 0},
            {"name": "ast", "type_": Integer, "default": 0},
            {"name": "stl", "type_": Integer, "default": 0},
            {"name": "blk", "type_": Integer, "default": 0},
            {"name": "tov", "type_": Integer, "default": 0},
            {"name": "reb_conceded", "type_": Integer, "default": 0},
        ],
    }

NEW_TABLES = ["organizations", "teams", "organization_memberships", "team_assignments"]
NEW_COLUMNS = {
    "users": "organization_id",
    "games": "team_id",
    "plays": "team_id",
    "play_types": "team_id",
    "players": "team_id",
    "lineups": "team_id",
    "system_settings": "organization_id",
}


@pytest.fixture
def pre_migration_db():
    """
    Create an in-memory SQLite database that has the OLD schema only
    (without multi-tenant tables/columns). After migration, the new
    tables and columns must appear.
    """
    os.environ.setdefault("DISABLE_AUTH", "1")

    from web import create_app as _create_app
    from core.models import db as _db

    app = _create_app("testing")

    with app.app_context():
        _db.drop_all()

        old_tables = _build_old_tables()
        metadata = MetaData()
        for table_name, column_defs in old_tables.items():
            cols = []
            for kwargs in column_defs:
                name = kwargs.pop("name")
                type_ = kwargs.pop("type_")
                cols.append(Column(name, type_, **kwargs))
            Table(table_name, metadata, *cols)
        metadata.create_all(_db.engine)

        yield app, _db

    with app.app_context():
        _db.drop_all()


@pytest.mark.integration
class TestProductionMigration:

    def test_migrate_creates_new_tables(self, pre_migration_db):
        """Must create organizations, teams, memberships, assignments."""
        from scripts.migrate import run as run_migration

        app, db = pre_migration_db
        with app.app_context():
            inspector = inspect(db.engine)
            for table in NEW_TABLES:
                assert table not in inspector.get_table_names(), f"Setup: {table} should not exist"

            run_migration(app)

            inspector = inspect(db.engine)
            for table in NEW_TABLES:
                assert table in inspector.get_table_names(), f"Migration did not create: {table}"

    def test_migrate_adds_new_columns_to_existing_tables(self, pre_migration_db):
        """Must add team_id, organization_id to existing tables."""
        from scripts.migrate import run as run_migration

        app, db = pre_migration_db
        with app.app_context():
            inspector = inspect(db.engine)
            for table, col in NEW_COLUMNS.items():
                columns = [c["name"] for c in inspector.get_columns(table)]
                assert col not in columns, f"Setup: {table}.{col} should not exist"

            run_migration(app)

            inspector = inspect(db.engine)
            for table, col in NEW_COLUMNS.items():
                columns = [c["name"] for c in inspector.get_columns(table)]
                assert col in columns, f"Migration did not add: {table}.{col}"

    def test_migrate_is_idempotent(self, pre_migration_db):
        """Running twice must be safe."""
        from scripts.migrate import run as run_migration

        app, db = pre_migration_db
        with app.app_context():
            run_migration(app)
            run_migration(app)

    def test_migrate_creates_default_org_and_team(self, pre_migration_db):
        """Must create a default org and team."""
        from scripts.migrate import run as run_migration
        from core.models import Organization, Team

        app, db = pre_migration_db
        with app.app_context():
            run_migration(app)

            org = Organization.query.first()
            assert org is not None
            assert org.slug == "default"

            team = Team.query.filter_by(organization_id=org.id).first()
            assert team is not None

    def test_migrate_assigns_existing_games_to_default_team(self, pre_migration_db):
        """Existing games without team_id must be assigned to the default team."""
        from scripts.migrate import run as run_migration
        from core.models import Game, db as _db

        app, _ = pre_migration_db
        with app.app_context():
            _db.session.execute(
                "INSERT INTO games (date, opponent, team_score, opponent_score, "
                "result, game_type, sort_date) "
                "VALUES ('01-01-2024', 'Old Opponent', 70, 60, 'W', 'Season', '2024-01-01')"
            )
            _db.session.commit()
            game_id = _db.session.execute("SELECT id FROM games LIMIT 1").scalar()

            run_migration(app)

            game = _db.session.get(Game, game_id)
            assert game is not None
            assert game.team_id is not None

    def test_query_by_team_id_works_after_migration(self, pre_migration_db):
        """Querying games by team_id must not 500."""
        from scripts.migrate import run as run_migration
        from core.models import Game, db as _db

        app, _ = pre_migration_db
        with app.app_context():
            _db.session.execute(
                "INSERT INTO games (date, opponent, team_score, opponent_score, "
                "result, game_type, sort_date) "
                "VALUES ('01-01-2024', 'Old Opponent', 70, 60, 'W', 'Season', '2024-01-01')"
            )
            _db.session.commit()

            run_migration(app)

            from core.models import Team
            team = Team.query.first()
            assert team is not None
            games = Game.query.filter_by(team_id=team.id).all()
            assert len(games) == 1

    def test_landing_page_does_not_500_after_migration(self, pre_migration_db):
        """App must serve pages without 500 after migration."""
        from scripts.migrate import run as run_migration

        app, db = pre_migration_db
        with app.app_context():
            run_migration(app)

        client = app.test_client()
        resp = client.get("/landing")
        assert resp.status_code in (200, 302), f"Got {resp.status_code}"
