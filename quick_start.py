#!/usr/bin/env python3
"""One-command local setup for the HoopsStats basketball stats analyzer.

Creates the database, the default organization + team, the local admin user
and a small set of sample games.

The script is idempotent: every object is looked up before it is created, so
running it twice never duplicates the organization/team/user and never trips a
UNIQUE constraint. That matters because ``organizations.slug`` and
``games.team_id`` are NOT NULL: creating an organization without a slug (or a
game without a team) aborts the setup halfway through and leaves a fresh
installation with no organization, no team and no admin user.
"""
import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.exc import IntegrityError

from config import get_config
from core.models import (
    Game,
    Organization,
    OrganizationMembership,
    PlayerStat,
    Team,
    TeamAssignment,
    User,
    db,
)
from web import create_app

# Defaults for the local installation. The slugs are stable, url-safe and
# match the ones used by the rest of the project (e.g. core/services/
# lineup_service.py), so scripts that resolve a team by slug keep working.
ORG_NAME = "Default Organization"
ORG_SLUG = "default-organization"
TEAM_NAME = "Default Team"
TEAM_SLUG = "default-team"
ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@local.com"
DEFAULT_ADMIN_PASSWORD = "admin123"


def slugify(value, fallback="default"):
    """Turn a display name into a url-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or fallback


def _unique_org_slug(base_slug, exclude_id=None):
    """Return a slug no other organization is using.

    ``organizations.slug`` is UNIQUE, so a taken slug must never be reused
    for a second organization: derive ``<base>-2``, ``<base>-3``, ... until
    the candidate is free.
    """
    candidate = base_slug
    suffix = 2
    while True:
        query = Organization.query.filter_by(slug=candidate)
        if exclude_id is not None:
            query = query.filter(Organization.id != exclude_id)
        if query.first() is None:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def ensure_organization():
    """Return the organization to use, creating it with a unique slug if needed.

    Reuses the organization that is already in the database: a second setup
    run (or a database seeded by another tool) must not create a duplicate.
    """
    org = Organization.query.order_by(Organization.id).first()
    if org is not None:
        # Rows written before the slug column became NOT NULL have none:
        # give them one instead of failing the whole setup.
        if not org.slug:
            org.slug = _unique_org_slug(
                slugify(org.name, ORG_SLUG), exclude_id=org.id
            )
            db.session.flush()
        return org

    slug = _unique_org_slug(slugify(ORG_NAME, ORG_SLUG))
    org = Organization(name=ORG_NAME, slug=slug)
    db.session.add(org)
    try:
        db.session.flush()
    except IntegrityError:
        # Another organization already owns the slug: reuse it rather than
        # crashing the setup.
        db.session.rollback()
        org = Organization.query.filter_by(slug=slug).first()
        if org is None:
            raise
    return org


def ensure_team(org):
    """Return the team of ``org``, creating the default one if needed."""
    team = Team.query.filter_by(organization_id=org.id, slug=TEAM_SLUG).first()
    if team is None:
        # A team created elsewhere (another tool, another slug) is still the
        # team's team: reuse it instead of adding a second one.
        team = Team.query.filter_by(organization_id=org.id).order_by(Team.id).first()
    if team is None:
        team = Team(name=TEAM_NAME, organization_id=org.id, slug=TEAM_SLUG)
        db.session.add(team)
        db.session.flush()
    return team


def ensure_admin(org, team):
    """Create the local admin user and its org/team links when missing."""
    admin = User.query.filter_by(username=ADMIN_USERNAME).first()
    if admin is None:
        admin = User(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            organization_id=org.id,
        )
        admin.set_password(os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD))
        db.session.add(admin)
        try:
            db.session.flush()
        except IntegrityError:
            # e.g. the email is already taken by another account: fall back
            # to the existing user instead of aborting the setup.
            db.session.rollback()
            admin = User.query.filter_by(username=ADMIN_USERNAME).first()
            if admin is None:
                raise
    elif not admin.organization_id:
        admin.organization_id = org.id
        db.session.flush()

    membership = OrganizationMembership.query.filter_by(
        user_id=admin.id, organization_id=org.id
    ).first()
    if membership is None:
        db.session.add(
            OrganizationMembership(
                user_id=admin.id, organization_id=org.id, is_gm=True
            )
        )

    assignment = TeamAssignment.query.filter_by(
        user_id=admin.id, team_id=team.id
    ).first()
    if assignment is None:
        db.session.add(
            TeamAssignment(user_id=admin.id, team_id=team.id, is_coach=True)
        )

    db.session.flush()
    return admin


def create_sample_data(team):
    """Insert the demo games and their player stats for ``team``.

    ``games.team_id`` is NOT NULL (games are multi-tenant), so every sample
    game is attached to the team that was just created.
    """
    games = [
        {
            "date": "15/03",
            "opponent": "Lakers",
            "team_score": 105,
            "opponent_score": 98,
            "result": "W",
            "game_type": "Season",
            "sort_date": "2024-03-15",
        },
        {
            "date": "20/03",
            "opponent": "Warriors",
            "team_score": 92,
            "opponent_score": 95,
            "result": "L",
            "game_type": "Season",
            "sort_date": "2024-03-20",
        },
        {
            "date": "25/03",
            "opponent": "Celtics",
            "team_score": 110,
            "opponent_score": 108,
            "result": "W",
            "game_type": "Playoff",
            "sort_date": "2024-03-25",
        },
    ]
    players = [
        {"name": "John Doe", "points": 28, "reb": 8, "ast": 6},
        {"name": "Jane Smith", "points": 22, "reb": 12, "ast": 4},
        {"name": "Mike Johnson", "points": 18, "reb": 5, "ast": 9},
    ]
    for gd in games:
        game = Game(team_id=team.id, **gd)
        db.session.add(game)
        db.session.flush()
        for p in players:
            stat = PlayerStat(
                game_id=game.id,
                player_name=p["name"],
                points=p["points"],
                reb=p["reb"],
                ast=p["ast"],
                minutes="30:00",
                fgm=int(p["points"] * 0.4),
                fga=int(p["points"] * 0.8),
                fg_percent=50.0,
                tpm=2,
                tpa=5,
                tp_percent=40.0,
                ftm=2,
                fta=3,
                ft_percent=66.7,
                oreb=2,
                dreb=p["reb"] - 2,
                stl=2,
                blk=1,
                tov=2,
                pf=2,
            )
            db.session.add(stat)
    db.session.commit()
    print(f"✓ Sample data created for team '{team.name}'")


def setup_local_environment(app=None):
    """Create the local database, org/team, admin user and sample data.

    ``app`` may be injected (tests point it at a temporary database); by
    default a development app is created.
    """
    print("=" * 60)
    print("BASKETBALL STATS ANALYZER - LOCAL SETUP")
    print("=" * 60)
    app = app or create_app("development")
    with app.app_context():
        db.create_all()
        print("✓ Database created")

        org = ensure_organization()
        team = ensure_team(org)
        ensure_admin(org, team)
        db.session.commit()
        print(f"✓ Organization: {org.name} (slug: {org.slug})")
        print(f"✓ Team: {team.name} (slug: {team.slug})")
        print(
            f"✓ Admin: {ADMIN_USERNAME}/"
            f"{os.getenv('ADMIN_PASSWORD', DEFAULT_ADMIN_PASSWORD)}"
        )

        # Sample data is per team: a team that already has games keeps them,
        # so a second run does not duplicate the demo games.
        if Game.query.filter_by(team_id=team.id).count() == 0:
            create_sample_data(team)

        for folder in [app.config["GAMES_DIR"], app.config["OUTPUT_DIR"]]:
            os.makedirs(folder, exist_ok=True)
    print("\nReady! Open http://localhost:8080\n")
    return app


def _reset_database():
    """Delete the SQLite database file the development config points at."""
    uri = get_config("development").SQLALCHEMY_DATABASE_URI
    if not uri.startswith("sqlite:///"):
        print(f"⚠ Skipping reset: {uri} is not a local SQLite file")
        return
    path = Path(uri[len("sqlite:///"):])
    if path.exists():
        path.unlink()
        print(f"✓ Database reset ({path})")
    else:
        print("✓ No existing database to reset")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Basketball Stats - Quick Start")
    parser.add_argument(
        "--no-run", action="store_true", help="Setup database only, don't start server"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Reset database before setup"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run server on (default: 8080)"
    )
    args = parser.parse_args(argv)

    if args.reset:
        _reset_database()
        print()

    app = setup_local_environment()

    if not args.no_run:  # START BY DEFAULT
        app.run(host="0.0.0.0", port=args.port, debug=True)
    else:
        print("Setup complete. Run 'python quick_start.py' to start server.")


if __name__ == "__main__":
    main()
