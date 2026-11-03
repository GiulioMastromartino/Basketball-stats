"""
Unit tests for multi-server architecture hardening.

Tests config parsing, instance-identifiable health probes, duplicate-game
detection (409), and DB-level dedupe + unique index.
"""

import importlib
import json
import os

import pytest
import config as config_module
from config import get_config
from core.db_migrations import dedupe_games, add_games_unique_index
from core.models import Game, db
from core.services.game_service import DuplicateGameError


def _reload_config_with_env(env_updates, env_removals=None):
    """Reload config module with modified env vars, restoring originals after."""
    env_removals = env_removals or []
    original = {}
    for k in list(env_updates.keys()) + list(env_removals):
        original[k] = os.environ.get(k)
    for k, v in env_updates.items():
        os.environ[k] = v
    for k in env_removals:
        os.environ.pop(k, None)
    importlib.reload(config_module)
    config = get_config()
    # Restore original env and reload again so other tests aren't affected.
    for k, v in original.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(config_module)
    return config


# =============================================================================
# Config tests
# =============================================================================


class TestMultiServerConfig:
    """Tests for cluster configuration parsing."""

    def test_node_name_default(self):
        """NODE_NAME defaults to 'basketball-stats'."""
        config = _reload_config_with_env({}, ["NODE_NAME"])
        assert config.NODE_NAME == "basketball-stats"

    def test_node_name_from_env(self):
        """NODE_NAME is read from env var."""
        config = _reload_config_with_env({"NODE_NAME": "node2"}, [])
        assert config.NODE_NAME == "node2"

    def test_auto_migrate_default_off(self):
        """AUTO_MIGRATE defaults to False when unset."""
        config = _reload_config_with_env({}, ["AUTO_MIGRATE"])
        assert config_module.Config.AUTO_MIGRATE is False

    def test_auto_migrate_on(self):
        """AUTO_MIGRATE is parsed as boolean."""
        config = _reload_config_with_env({"AUTO_MIGRATE": "true"}, [])
        assert config.AUTO_MIGRATE is True

    def test_ratelimit_storage_uri_from_uri_key(self):
        """RATELIMIT_STORAGE_URI takes precedence over RATELIMIT_STORAGE_URL."""
        config = _reload_config_with_env(
            {"RATELIMIT_STORAGE_URI": "redis://:pass@truenas:6379/0",
             "RATELIMIT_STORAGE_URL": "memory://"},
            [],
        )
        assert config.RATELIMIT_STORAGE_URI == "redis://:pass@truenas:6379/0"

    def test_ratelimit_storage_uri_falls_back_to_url_key(self):
        """RATELIMIT_STORAGE_URI falls back to RATELIMIT_STORAGE_URL."""
        config = _reload_config_with_env(
            {"RATELIMIT_STORAGE_URL": "redis://:pass@truenas:6379/0"},
            ["RATELIMIT_STORAGE_URI"],
        )
        assert config.RATELIMIT_STORAGE_URI == "redis://:pass@truenas:6379/0"

    def test_ratelimit_storage_uri_defaults_to_memory(self):
        """RATELIMIT_STORAGE_URI defaults to memory:// when unset."""
        config = _reload_config_with_env(
            {},
            ["RATELIMIT_STORAGE_URI", "RATELIMIT_STORAGE_URL"],
        )
        assert config.RATELIMIT_STORAGE_URI == "memory://"


# =============================================================================
# Health endpoint tests
# =============================================================================


class TestInstanceIdentifiableHealth:
    """Tests that health probes identify the node (NODE_NAME:pid)."""

    def test_health_live_returns_instance(self, client):
        """GET /health/live returns instance = NODE_NAME:pid."""
        response = client.get("/health/live")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "alive"
        assert "instance" in data
        assert data["instance"].startswith("basketball-stats:")

    def test_health_ready_returns_instance(self, client):
        """GET /health/ready returns instance = NODE_NAME:pid."""
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert "instance" in data
        assert data["instance"].startswith("basketball-stats:")


# =============================================================================
# DuplicateGameError tests
# =============================================================================


class TestDuplicateGameError:
    """Tests that DuplicateGameError is raised and caught correctly."""

    def test_duplicate_game_error_is_exception(self):
        """DuplicateGameError subclasses Exception."""
        err = DuplicateGameError("Game already exists")
        assert isinstance(err, Exception)
        assert str(err) == "Game already exists"


# =============================================================================
# DB-level dedupe + unique index tests
# =============================================================================


class TestDedupeGames:
    """Tests for dedupe_games() and add_games_unique_index()."""

    def _make_dupes(self, db_session, default_team, count=2):
        """Create `count` duplicate games plus one keeper, return keeper id."""
        keeper = Game(
            team_id=default_team.id, date="17-02-2024", opponent="Rivals",
            team_score=75, opponent_score=68, result="W",
            game_type="Season", sort_date="2024-02-17", source="IMPORT",
        )
        db_session.add(keeper)
        db_session.flush()

        for i in range(count):
            dup = Game(
                team_id=default_team.id, date="17-02-2024", opponent="Rivals",
                team_score=70 + i, opponent_score=65 + i, result="W",
                game_type="Season", sort_date="2024-02-17", source="IMPORT",
            )
            db_session.add(dup)
        db_session.commit()
        return keeper.id

    def test_dedupe_keeps_lowest_id(self, db_session, default_team):
        """dedupe_games keeps the lowest-id game per (team, date, opponent)."""
        keeper_id = self._make_dupes(db_session, default_team, count=2)

        removed = dedupe_games(db)
        assert removed == 2

        db.session.expire_all()
        remaining = (
            Game.query.filter_by(
                team_id=default_team.id,
                sort_date="2024-02-17",
                opponent="Rivals",
            ).all()
        )
        assert len(remaining) == 1
        assert remaining[0].id == keeper_id

    def test_dedupe_is_idempotent(self, db_session, default_team):
        """Running dedupe_games twice returns 0 the second time."""
        keeper_id = self._make_dupes(db_session, default_team, count=1)

        removed1 = dedupe_games(db)
        assert removed1 == 1
        removed2 = dedupe_games(db)
        assert removed2 == 0

    def test_add_games_unique_index_creates_index(self, db_session, default_team):
        """add_games_unique_index dedupes then creates the unique index."""
        from sqlalchemy import inspect as sa_inspect

        keeper_id = self._make_dupes(db_session, default_team, count=1)

        result = add_games_unique_index(db)
        assert result is True

        inspector = sa_inspect(db.engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("games")}
        constraints = {
            c["name"] for c in inspector.get_unique_constraints("games")
        }
        assert "uq_games_team_date_opponent" in indexes or \
            "uq_games_team_date_opponent" in constraints

    def test_add_games_unique_index_is_idempotent(self, db_session, default_team):
        """Running add_games_unique_index twice succeeds both times."""
        self._make_dupes(db_session, default_team, count=1)

        assert add_games_unique_index(db) is True
        assert add_games_unique_index(db) is True

    def test_unique_index_rejects_new_duplicates(self, db_session, default_team):
        """After the unique index exists, inserting a duplicate raises."""
        from sqlalchemy.exc import IntegrityError

        keeper = Game(
            team_id=default_team.id, date="17-02-2024", opponent="Rivals",
            team_score=75, opponent_score=68, result="W",
            game_type="Season", sort_date="2024-02-17", source="IMPORT",
        )
        db_session.add(keeper)
        db_session.commit()

        add_games_unique_index(db)

        with pytest.raises(IntegrityError):
            db_session.add(Game(
                team_id=default_team.id,
                date="17-02-2024", opponent="Rivals",
                team_score=99, opponent_score=1, result="W",
                game_type="Season", sort_date="2024-02-17", source="IMPORT",
            ))
            db_session.commit()
        db_session.rollback()
