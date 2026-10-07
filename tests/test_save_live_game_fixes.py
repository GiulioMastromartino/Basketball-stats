"""
Regression tests for the save-live-game fixes.

Covers:
- auditor POST /live-game/save -> 403, no Game created
- generic 500 hides exception text, includes request_id
- cross-tenant play_id is never hijacked; whitespace play_name creates no Play
- strict validation (impossible date, missing opponent, garbage scores,
  non-dict rows, duplicate guard)
"""

import ast
import copy
import inspect
import json

import pytest
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
)
from sqlalchemy import (
    inspect as sa_inspect,
)
from sqlalchemy.exc import IntegrityError

from core.models import (
    Game,
    GameEvent,
    OrganizationMembership,
    Play,
    ShotEvent,
    Team,
    TeamAssignment,
    User,
    db,
)


def _base_payload(opponent="Regression Opp", date="2024-03-10"):
    """Minimal valid LIVE-style payload with unique opponent/date."""
    return {
        "date": date,
        "opponent": opponent,
        "team_score": 75,
        "opponent_score": 68,
        "game_type": "Season",
        "player_stats": {
            "John Doe": {
                "points": 18,
                "fgm": 7,
                "fga": 14,
                "tpm": 2,
                "tpa": 5,
                "ftm": 2,
                "fta": 3,
                "oreb": 1,
                "dreb": 4,
                "ast": 3,
                "stl": 2,
                "blk": 1,
                "tov": 2,
                "pf": 3,
                "plus_minus": 8,
                "minutes": "24:30",
            }
        },
        "shot_locations": [
            {
                "shooter": "John Doe",
                "type": "2pt",
                "result": "made",
                "points": 2,
                "x": 250,
                "y": 100,
                "quarter": 1,
                "play_id": None,
            }
        ],
        "game_events": [
            {
                "type": "SHOT_2PT",
                "player": "John Doe",
                "quarter": 1,
                "clockSeconds": 90,
                "time_remaining": "8:30",
                "score_margin": 2,
                "game_seconds": 90,
                "possession_number": 1,
                "timestamp": 1708176000000,
            }
        ],
    }


class TestAuditorSaveBlocked:
    """Auditors have read-only access to the live-game save endpoint."""

    @pytest.mark.integration
    def test_auditor_post_save_403_no_game(
        self, client, db_session, default_org, default_team, live_game_payload
    ):
        auditor = User(
            username="auditor_save",
            email="auditor_save@test.com",
            organization_id=default_org.id,
            is_auditor=True,
        )
        auditor.set_password("password123")
        db_session.add(auditor)
        db_session.flush()
        db_session.add(
            OrganizationMembership(
                user_id=auditor.id,
                organization_id=default_org.id,
                is_gm=False,
            )
        )
        db_session.add(
            TeamAssignment(
                user_id=auditor.id, team_id=default_team.id, is_coach=False
            )
        )
        db_session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(auditor.id)
            sess["_fresh"] = True
            sess["current_team_id"] = default_team.id
            sess["current_team_name"] = default_team.name

        response = client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        assert response.status_code == 403
        assert "read-only" in response.get_data(as_text=True).lower()
        assert Game.query.filter_by(opponent="Test Team").first() is None


class TestGeneric500:
    """Unexpected failures return a generic body without leaking internals."""

    @pytest.mark.integration
    def test_500_hides_exception_and_has_request_id(
        self, auth_client, live_game_payload, monkeypatch
    ):
        import web.routes.main as main_routes

        def _boom(*args, **kwargs):
            raise RuntimeError("secret")

        monkeypatch.setattr(
            main_routes, "create_game_from_live_data", _boom
        )

        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        assert response.status_code == 500
        body_text = response.get_data(as_text=True)
        data = json.loads(response.data)
        assert "Failed to save game" in body_text
        assert "secret" not in body_text
        assert "request_id" in data


class TestCrossTenantPlay:
    """A payload must never resolve events to another team's Play."""

    @pytest.mark.integration
    def test_cross_team_play_id_not_hijacked(
        self, auth_client, db_session, default_org, default_team
    ):
        team_b = Team(
            name="Team B", organization_id=default_org.id, slug="team-b-x"
        )
        db_session.add(team_b)
        db_session.commit()
        play_b = Play(
            name="Secret Play",
            team_id=team_b.id,
            play_type="Offense",
            source="manual",
        )
        db_session.add(play_b)
        db_session.commit()
        play_b_id = play_b.id

        payload = _base_payload(opponent="Cross Tenant Opp", date="2024-03-01")
        payload["shot_locations"][0]["play_id"] = play_b_id
        payload["game_events"][0]["play_id"] = play_b_id

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        game = Game.query.filter_by(opponent="Cross Tenant Opp").first()
        assert game is not None
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        event = GameEvent.query.filter_by(game_id=game.id).first()
        assert shot is not None
        assert event is not None
        assert shot.play_id != play_b_id
        assert event.play_id != play_b_id
        for resolved_id in (shot.play_id, event.play_id):
            if resolved_id is not None:
                owner = Play.query.filter_by(id=resolved_id).first()
                assert owner is not None
                assert owner.team_id == default_team.id

    @pytest.mark.integration
    def test_whitespace_play_name_creates_no_play(self, auth_client, db_session):
        payload = _base_payload(opponent="Whitespace Play Opp", date="2024-03-02")
        payload["shot_locations"][0]["play_name"] = "   "
        payload["game_events"][0]["detail"] = {"play_name": "   "}

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        game = Game.query.filter_by(opponent="Whitespace Play Opp").first()
        assert game is not None
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        assert shot is not None
        assert shot.play_id is None
        assert Play.query.filter_by(name="").first() is None
        assert Play.query.filter_by(name="   ").first() is None


class TestSaveValidation:
    """Strict validation: bad dates/opponents rejected, garbage never 500s."""

    @pytest.mark.integration
    def test_impossible_date_400(self, auth_client):
        payload = _base_payload(opponent="Bad Date Opp", date="2024-13-40")

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code == 400

    @pytest.mark.integration
    def test_missing_opponent_400(self, auth_client):
        payload = _base_payload(opponent="Will Be Removed", date="2024-03-04")
        payload.pop("opponent")

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code == 400

        blank = _base_payload(opponent="   ", date="2024-03-05")
        response = auth_client.post(
            "/live-game/save", json=blank, content_type="application/json"
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_garbage_scores_do_not_500(self, auth_client, db_session):
        payload = _base_payload(opponent="Garbage Score Opp", date="2024-03-06")
        payload["team_score"] = "abc"
        payload["opponent_score"] = "xyz"

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code != 500
        assert response.status_code in [200, 201, 400]
        if response.status_code in [200, 201]:
            game = Game.query.filter_by(opponent="Garbage Score Opp").first()
            assert game is not None
            assert game.team_score == 0
            assert game.opponent_score == 0

    @pytest.mark.integration
    def test_non_dict_rows_skipped(self, auth_client, db_session):
        payload = _base_payload(opponent="Non Dict Opp", date="2024-03-07")
        payload["player_stats"]["Ghost"] = "garbage"
        payload["shot_locations"].extend(["garbage", 42, None])
        payload["game_events"].extend(["junk", None, 42])

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        game = Game.query.filter_by(opponent="Non Dict Opp").first()
        assert game is not None
        assert len(ShotEvent.query.filter_by(game_id=game.id).all()) == 1
        assert len(GameEvent.query.filter_by(game_id=game.id).all()) == 1

    @pytest.mark.integration
    def test_duplicate_post_rejected(self, auth_client):
        payload = _base_payload(opponent="Dupe Opp", date="2024-03-08")

        first = auth_client.post(
            "/live-game/save", json=copy.deepcopy(payload),
            content_type="application/json",
        )
        assert first.status_code in [200, 201]

        second = auth_client.post(
            "/live-game/save", json=copy.deepcopy(payload),
            content_type="application/json",
        )

        assert second.status_code in [400, 409]
        assert "already exists" in second.get_data(as_text=True).lower()


class TestScopeLookupFailure500:
    """DB failures during scope checks are server errors, not denials."""

    @pytest.mark.integration
    def test_assigned_teams_failure_is_500_not_403(
        self, auth_client, live_game_payload, monkeypatch
    ):
        import web.routes.main as main_routes

        class _BrokenTeams:
            is_auditor = False
            id = 1

            @property
            def assigned_teams(self):
                raise RuntimeError("db down")

        monkeypatch.setattr(main_routes, "current_user", _BrokenTeams())

        response = auth_client.post(
            "/live-game/save", json=live_game_payload,
            content_type="application/json",
        )

        assert response.status_code == 500
        data = json.loads(response.data)
        assert data["error"] == "Failed to save game"
        assert "request_id" in data
        assert "db down" not in response.get_data(as_text=True)


class TestPlayMapUnresolved:
    """Unresolved team scope must fail closed (no cross-team leak)."""

    def test_play_map_none_team_returns_empty(self, db_session):
        from core.play_analytics import _play_map

        assert _play_map("Offense", team_id=None) == {}


class TestPlaysUniquenessMigration:
    """Composite (team_id, name) uniqueness migration is safe and idempotent."""

    def test_migration_noop_when_composite_present(
        self, app, db_session, default_org
    ):
        from scripts.migrate import migrate_plays_team_unique

        assert migrate_plays_team_unique(app) is True
        # Idempotent: second run is also a clean no-op.
        assert migrate_plays_team_unique(app) is True

    @pytest.mark.integration
    def test_cross_team_same_name_coexists(
        self, app, db_session, default_org, default_team
    ):
        from scripts.migrate import migrate_plays_team_unique

        team_b = Team(
            name="Team B Same Name",
            organization_id=default_org.id,
            slug="team-b-same-name",
        )
        db_session.add(team_b)
        db_session.commit()

        db_session.add(
            Play(name="Shared Play", team_id=default_team.id, play_type="Offense")
        )
        db_session.add(
            Play(name="Shared Play", team_id=team_b.id, play_type="Offense")
        )
        db_session.commit()

        assert (
            Play.query.filter_by(name="Shared Play").count() == 2
        )
        # The migration helper must accept this state (no dupes within a team).
        assert migrate_plays_team_unique(app) is True


def _recreate_legacy_plays_table(app):
    """Replace `plays` with the pre-PR shape: a global UNIQUE(name).

    Built from the live model so it tracks column additions; only the
    __table_args__ differs (UNIQUE(name) instead of UNIQUE(team_id, name)).
    Mirrors what ``db.create_all()`` produced on a deployment predating
    this PR -- SQLite renders that as an inline table constraint.
    """
    engine = db.engine
    meta = MetaData()
    # Stub so the plays.team_id foreign key resolves during DDL compilation.
    Table("teams", meta, Column("id", Integer, primary_key=True))
    legacy = Table(
        "plays",
        meta,
        *(c.copy() for c in Play.__table__.columns),
    )
    legacy.append_constraint(UniqueConstraint("name"))

    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS plays")
    legacy.create(engine)
    return legacy


def _assert_composite_unique_only(engine):
    """The only uniqueness on plays must be UNIQUE(team_id, name)."""
    constraints = sa_inspect(engine).get_unique_constraints("plays")
    assert not any(
        list(c.get("column_names") or []) == ["name"] for c in constraints
    ), "legacy global UNIQUE(plays.name) still present"
    assert any(
        list(c.get("column_names") or []) == ["team_id", "name"] for c in constraints
    ), "composite UNIQUE(team_id, name) missing"


class TestPlaysUniquenessMigrationLegacySQLite:
    """The legacy global UNIQUE(name) must actually be removed.

    Regression: the migration used to report success while that constraint
    survived, because SQLAlchemy reflects an inline SQLite UNIQUE(name) via
    get_unique_constraints (name=None) and never via get_indexes, so the
    drop loop was skipped and the next run early-returned on the composite
    index. Cross-team same-name imports then hit IntegrityError and
    game_service._create_scoped_play silently stored play_id=None.
    """

    def test_legacy_global_unique_is_removed(self, app, db_session, default_team):
        from scripts.migrate import migrate_plays_team_unique

        _recreate_legacy_plays_table(app)
        db_session.add(
            Play(name="Horns", team_id=default_team.id, play_type="Offense")
        )
        db_session.commit()

        assert migrate_plays_team_unique(app) is True

        inspector = sa_inspect(db.engine)
        constraints = inspector.get_unique_constraints("plays")
        assert not any(
            list(c.get("column_names") or []) == ["name"] for c in constraints
        ), "legacy global UNIQUE(plays.name) still present"
        assert any(
            list(c.get("column_names") or []) == ["team_id", "name"]
            for c in constraints
        ), "composite UNIQUE(team_id, name) missing"

    def test_cross_team_same_name_survives_after_migration(
        self, app, db_session, default_org, default_team
    ):
        from scripts.migrate import migrate_plays_team_unique

        _recreate_legacy_plays_table(app)
        assert migrate_plays_team_unique(app) is True

        team_b = Team(
            name="Team B Legacy",
            organization_id=default_org.id,
            slug="team-b-legacy",
        )
        db_session.add(team_b)
        db_session.commit()

        # The whole point of the composite: two teams may reuse a play name.
        db_session.add(Play(name="Iso", team_id=default_team.id, play_type="Offense"))
        db_session.add(Play(name="Iso", team_id=team_b.id, play_type="Offense"))
        db_session.commit()
        assert Play.query.filter_by(name="Iso").count() == 2

        # ...but a single team still cannot.
        with pytest.raises(IntegrityError):
            db_session.add(
                Play(name="Iso", team_id=default_team.id, play_type="Defense")
            )
            db_session.commit()
        db_session.rollback()

    def test_existing_rows_survive_the_rebuild(self, app, db_session, default_team):
        from scripts.migrate import migrate_plays_team_unique

        _recreate_legacy_plays_table(app)
        db_session.add(
            Play(name="Horns", team_id=default_team.id, play_type="Offense")
        )
        db_session.commit()

        assert migrate_plays_team_unique(app) is True
        # Re-runs must be clean no-ops on the already-migrated schema.
        assert migrate_plays_team_unique(app) is True
        _assert_composite_unique_only(db.engine)
        assert Play.query.filter_by(name="Horns").count() == 1

    def test_migration_rebuilds_legacy_table_and_keeps_play_sequences_fk(
        self, app, db_session, default_team
    ):
        """Rebuild renames plays_new -> plays; play_sequences must still resolve."""
        from scripts.migrate import migrate_plays_team_unique

        _recreate_legacy_plays_table(app)
        play = Play(name="Horns", team_id=default_team.id, play_type="Offense")
        db_session.add(play)
        db_session.commit()

        assert migrate_plays_team_unique(app) is True
        _assert_composite_unique_only(db.engine)
        db_session.expire_all()
        assert Play.query.get(play.id) is not None


class TestPostgresIndexProbeBinding:
    """The Postgres index probe must not use ``:idx::regclass``.

    SQLAlchemy's bind-param regex mis-parses ``:idx::regclass`` as the
    parameter ``id``, so ``{"idx": ...}`` never binds and the literal colon
    reaches the server -- the migration then dies on the first index
    (plays_pkey) and run() swallows the error as a warning.
    """

    def test_double_colon_cast_binds_the_wrong_parameter(self):
        from sqlalchemy import text

        assert set(text("WHERE i.indexrelid = :idx::regclass")._bindparams) == {"id"}
        assert set(
            text("WHERE i.indexrelid = CAST(:idx AS regclass)")._bindparams
        ) == {"idx"}

    def test_migration_sql_avoids_the_double_colon_form(self):
        """Check the SQL literals themselves, ignoring explanatory comments."""
        from scripts import migrate as migrate_mod

        source = inspect.getsource(migrate_mod.migrate_plays_team_unique)
        sql_literals = [
            node.value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        for literal in sql_literals:
            assert ":idx::regclass" not in literal, (
                f"SQL literal still uses :idx::regclass -> {literal!r}"
            )
        assert any("CAST(:idx AS regclass)" in lit for lit in sql_literals)
        # A non-unique index on name is a legitimate perf index.
        assert any("i.indisunique" in lit for lit in sql_literals)

    def test_incomplete_legacy_table_is_left_alone(self, app, db_session, default_team):
        """A plays table missing model columns must not be half-migrated."""
        from scripts.migrate import migrate_plays_team_unique

        _recreate_legacy_plays_table(app)
        with db.engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE plays DROP COLUMN tags")

        # Rebuild would copy a column the table does not have, so the
        # migration reports failure and leaves the legacy constraint alone.
        assert migrate_plays_team_unique(app) is False
        inspector = sa_inspect(db.engine)
        assert any(
            list(c.get("column_names") or []) == ["name"]
            for c in inspector.get_unique_constraints("plays")
        )
