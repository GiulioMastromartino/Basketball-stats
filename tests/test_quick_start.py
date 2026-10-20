"""Regression tests for the documented first-run setup (``quick_start.py``).

The documented setup used to crash on a fresh installation::

    python quick_start.py --no-run
    -> sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError)
       NOT NULL constraint failed: organizations.slug

because the organization was created without a slug, and the sample games were
created without a ``team_id`` (``games.team_id`` is NOT NULL). The setup
aborted before the admin user, so a fresh install had no organization, no
team and no admin user, and ``cli_import.py`` then aborted with
"no team to import into".

These tests run the real setup function against a temporary SQLite database
(the developer's ``basketball_stats.db`` is never touched).
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from config import TestingConfig, config_map
from core.models import (
    Game,
    Organization,
    OrganizationMembership,
    Team,
    TeamAssignment,
    User,
)

# The repository root holds ``quick_start.py``, but ``scripts/`` holds a
# module with the same name and some tests put ``scripts/`` on ``sys.path``
# (scripts/migrate.py does it at import time). Importing by file path keeps
# this test bound to the root script, whatever else is on sys.path.
QUICK_START_PATH = Path(__file__).resolve().parent.parent / "quick_start.py"


@pytest.fixture(scope="module")
def quick_start_module():
    """The root ``quick_start.py`` module, loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "root_quick_start", QUICK_START_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def quick_start_app(monkeypatch, tmp_path):
    """An app backed by a throw-away SQLite file.

    A file database (not ``:memory:``) so the setup writes real rows that can
    be re-read after the setup finished.
    """

    class _QuickStartTestingConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path}/quick_start_test.db"
        GAMES_DIR = str(tmp_path / "Games")
        OUTPUT_DIR = str(tmp_path / "Output")

    monkeypatch.setitem(config_map, "quick_start_testing", _QuickStartTestingConfig)

    from web import create_app

    app = create_app("quick_start_testing")
    yield app
    with app.app_context():
        from web import db

        db.session.remove()
        db.engine.dispose()


def _run_setup(app, module):
    module.setup_local_environment(app=app)


def test_setup_creates_organization_with_slug(quick_start_app, quick_start_module):
    """The organization must exist AND carry a slug (NOT NULL, UNIQUE)."""
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        orgs = Organization.query.all()
        assert len(orgs) == 1, "setup must not create a second organization"
        org = orgs[0]
        assert org.slug, "organizations.slug is NOT NULL"
        assert org.slug == org.slug.strip().lower()
        assert " " not in org.slug, "the slug must be url-safe"


def test_setup_creates_single_team_attached_to_the_organization(
    quick_start_app, quick_start_module
):
    """Exactly one team, bound to the organization, with the documented slug."""
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        teams = Team.query.all()
        assert len(teams) == 1
        team = teams[0]
        org = Organization.query.one()
        assert team.organization_id == org.id
        assert team.slug == "default-team"


def test_setup_creates_admin_user_with_membership_and_assignment(
    quick_start_app, quick_start_module
):
    """The admin user (plus its org membership / team assignment) must exist."""
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        admin = User.query.filter_by(username="admin").first()
        assert admin is not None, "the admin user is required by the setup"
        assert admin.password_hash, "the admin user needs a password"

        org = Organization.query.one()
        team = Team.query.one()
        assert admin.organization_id == org.id

        membership = OrganizationMembership.query.filter_by(
            user_id=admin.id, organization_id=org.id
        ).first()
        assert membership is not None
        assert membership.is_gm is True

        assignment = TeamAssignment.query.filter_by(
            user_id=admin.id, team_id=team.id
        ).first()
        assert assignment is not None
        assert assignment.is_coach is True


def test_sample_games_are_attached_to_the_team(quick_start_app, quick_start_module):
    """``games.team_id`` is NOT NULL: the sample games must belong to the team."""
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        team = Team.query.one()
        games = Game.query.all()
        assert games, "the setup must create the sample games"
        for game in games:
            assert game.team_id is not None
            assert game.team_id == team.id


def test_setup_is_idempotent(quick_start_app, quick_start_module):
    """Running the setup twice must not raise and must not duplicate anything."""
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        games_after_first_run = Game.query.count()
        assert games_after_first_run > 0

    # Second run: must not raise.
    _run_setup(quick_start_app, quick_start_module)
    # ... and a third one, for good measure.
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        assert Organization.query.count() == 1
        assert Team.query.count() == 1
        assert User.query.filter_by(username="admin").count() == 1
        assert OrganizationMembership.query.count() == 1
        assert TeamAssignment.query.count() == 1
        assert Game.query.count() == games_after_first_run, (
            "the sample games must not be duplicated"
        )


def test_setup_reuses_an_existing_organization(quick_start_app, quick_start_module):
    """An organization that already exists (slug taken) is reused, not cloned."""
    with quick_start_app.app_context():
        from web import db

        db.create_all()
        existing = Organization(
            name="Existing Organization", slug="existing-organization"
        )
        db.session.add(existing)
        db.session.flush()
        team = Team(
            name="Existing Team",
            organization_id=existing.id,
            slug="existing-team",
        )
        db.session.add(team)
        db.session.commit()
        existing_id = existing.id

    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        assert Organization.query.count() == 1
        assert Organization.query.one().id == existing_id
        assert Team.query.count() == 1


def test_setup_gives_a_legacy_organization_without_slug_a_slug(
    quick_start_app, quick_start_module
):
    """Rows predating the NOT NULL slug column get one instead of crashing."""
    with quick_start_app.app_context():
        from web import db

        # Recreate the table the way it looked before slug became NOT NULL,
        # then insert a row without a slug: that is what an old database
        # looks like to the setup.
        db.session.execute(text("DROP TABLE organizations"))
        db.session.execute(
            text(
                "CREATE TABLE organizations ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR(100) NOT NULL, "
                "slug VARCHAR(50), "
                "created_at DATETIME, "
                "timezone VARCHAR(50) NOT NULL DEFAULT 'UTC', "
                "sport VARCHAR(50) NOT NULL DEFAULT 'basketball', "
                "season_convention VARCHAR(20) NOT NULL DEFAULT 'sept-june'"
                ")"
            )
        )
        db.session.execute(
            text(
                "INSERT INTO organizations (name, created_at, timezone, sport, "
                "season_convention) VALUES ('Legacy Org', '2024-01-01 00:00:00', "
                "'UTC', 'basketball', 'sept-june')"
            )
        )
        db.session.commit()

    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        org = Organization.query.one()
        assert org.slug, "a legacy organization without slug must get one"


def test_setup_only_touches_the_configured_database(quick_start_app, tmp_path):
    """The setup must only write to the database the app is configured with."""
    with quick_start_app.app_context():
        from web import db

        uri = str(db.engine.url)
        assert str(tmp_path) in uri


def test_setup_uses_the_documented_slugs(quick_start_module):
    """The slugs are part of the contract with the rest of the project."""
    assert quick_start_module.ORG_SLUG == "default-organization"
    assert quick_start_module.TEAM_SLUG == "default-team"


def test_tables_exist_after_setup(quick_start_app, quick_start_module):
    """The setup creates the full schema (games.team_id NOT NULL included)."""
    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        from web import db

        inspector = inspect(db.engine)
        assert inspector.has_table("organizations")
        assert inspector.has_table("teams")
        assert inspector.has_table("games")

        game_columns = {c["name"]: c for c in inspector.get_columns("games")}
        assert game_columns["team_id"]["nullable"] is False


def test_cli_import_can_resolve_the_team_after_setup(quick_start_app, quick_start_module):
    """The reported symptom: after setup, cli_import.py aborted with
    "database spans multiple organizations" / "no team to import into"."""
    import cli_import

    _run_setup(quick_start_app, quick_start_module)

    with quick_start_app.app_context():
        team = Team.query.one()
        # No explicit --team/--team-id: the single default team must resolve.
        assert cli_import.resolve_team() is team
        # ... and it must also resolve by name and by slug (CLI contract).
        assert cli_import.resolve_team(team="Default Team") is team
        assert cli_import.resolve_team(team="default-team") is team
        assert cli_import.resolve_team(team_id=team.id) is team
