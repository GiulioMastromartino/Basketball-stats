#!/usr/bin/env python3
"""
Production migration script.

Replaces the fragile `flask db init && flask db migrate && flask db upgrade`
chain that broke whenever the container was rebuilt (missing revision history).

Strategy:
   1.  db.create_all()        - creates any missing tables, never drops existing ones
   1b. add_missing_columns    - adds new columns (team_id, organization_id) to existing tables
   2.  Seed players           - populate players from distinct player_stats names (idempotent)
   3.  Activate inactive      - fix any players seeded with active=0
   4.  alembic stamp head     - baseline for future flask db migrate / upgrade
   5.  promote_admin          - elevate ADMIN_EMAIL user if present
   6.  multi-tenant migrate   - ensure default org/team, assign existing data

Safe to re-run on every deploy.
"""
import os
import sys
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
_scripts_dir = str(Path(__file__).parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from web import create_app
from core.models import (
    db, Organization, Team, OrganizationMembership, TeamAssignment,
    Player, PlayerStat, User, Game, Play, PlayType, Lineup,
    SystemSetting,
)
from init_db import add_missing_columns, add_notification_columns
from sqlalchemy import text


def run(app=None):
    """Run the production migration.

    Args:
        app: Optional Flask app instance. If None, creates one using the
             default config (for CLI usage). Tests should pass their own app.
    """
    if app is None:
        app = create_app()

    with app.app_context():
        # ── 1. Create all tables that don't exist yet ──────────────────────
        print("[migrate] Running db.create_all()...")
        db.create_all()
        print("[migrate] db.create_all() complete.")

        # ── 1b. Add missing columns to existing tables ─────────────────────
        # db.create_all() only creates new tables, it doesn't add columns
        # to tables that already exist. This handles the multi-tenant migration
        # where existing tables need team_id, organization_id, etc.
        print("[migrate] Adding missing columns to existing tables...")
        try:
            add_missing_columns(app)
            print("[migrate] Missing columns added successfully.")
        except Exception as e:
            print(f"[migrate] Warning: add_missing_columns failed: {e}")

        # ── 1c. Add notification columns to users and players ─────────────
        print("[migrate] Adding notification columns...")
        try:
            add_notification_columns(app)
            print("[migrate] Notification columns added successfully.")
        except Exception as e:
            print(f"[migrate] Warning: add_notification_columns failed: {e}")

        # ── 2. Seed players from player_stats (idempotent) ─────────────────
        try:
            rows = db.session.query(PlayerStat.player_name).distinct().all()
            names_in_stats = [r[0] for r in rows if r[0]]
            print(f"[migrate] Found {len(names_in_stats)} unique player name(s) in player_stats.")

            existing = {p.name for p in Player.query.all()}
            added = 0
            for name in sorted(names_in_stats):
                if name not in existing:
                    db.session.add(Player(name=name, email=None, active=True))
                    added += 1
                    print(f"[migrate]   + {name}")

            if added:
                db.session.commit()
                print(f"[migrate] Seeded {added} new player(s).")
            else:
                print("[migrate] Players table already up-to-date.")
        except Exception as e:
            print(f"[migrate] Warning: player seeding failed: {e}")
            db.session.rollback()

        # ── 3. Activate any players that ended up with active=0 ────────────
        try:
            inactive = Player.query.filter_by(active=False).count()
            if inactive > 0:
                print(f"[migrate] Activating {inactive} inactive player(s)...")
                db.session.execute(
                    Player.__table__.update()
                    .where(Player.__table__.c.active == False)  # noqa: E712
                    .values(active=True)
                )
                db.session.commit()
                print(f"[migrate] Activated {inactive} player(s).")
            else:
                print("[migrate] All players already active.")
        except Exception as e:
            print(f"[migrate] Warning: could not check players table: {e}")
            db.session.rollback()

        # ── 4. Stamp alembic head so flask db migrate works on next deploy ──
        try:
            from alembic.config import Config
            from alembic import command as alembic_command

            migrations_dir = Path(app.root_path).parent / "migrations"
            if not migrations_dir.exists():
                print("[migrate] Initialising migrations folder...")
                from flask_migrate import init as migrate_init
                migrate_init(str(migrations_dir))

            alembic_cfg = Config(str(migrations_dir / "alembic.ini"))
            alembic_cfg.set_main_option("script_location", str(migrations_dir))
            alembic_cfg.set_main_option(
                "sqlalchemy.url",
                app.config["SQLALCHEMY_DATABASE_URI"],
            )

            print("[migrate] Stamping alembic head...")
            alembic_command.stamp(alembic_cfg, "head")
            print("[migrate] Alembic stamp complete.")
        except Exception as e:
            print(f"[migrate] Warning: alembic stamp failed (non-fatal): {e}")

        # ── 5. Promote ADMIN_EMAIL user ─────────────────────────────────────
        admin_email = os.getenv("ADMIN_EMAIL")
        if not admin_email:
            print("[migrate] No ADMIN_EMAIL set, skipping admin promotion.")
        else:
            try:
                user = User.query.filter_by(email=admin_email).first()
                if not user:
                    print(f"[migrate] User {admin_email} not found yet (will be promoted on first login).")
                else:
                    # Ensure a default org exists
                    org = Organization.query.first()
                    if not org:
                        org = Organization(name="Default Organization", slug="default")
                        db.session.add(org)
                        db.session.flush()
                        print("[migrate] Created default organization.")

                    team = Team.query.filter_by(organization_id=org.id).first()
                    if not team:
                        team = Team(name="Default Team", organization_id=org.id, slug="default-team")
                        db.session.add(team)
                        db.session.flush()
                        print("[migrate] Created default team.")

                    user.organization_id = org.id

                    # Create or update GM membership
                    membership = OrganizationMembership.query.filter_by(
                        user_id=user.id, organization_id=org.id
                    ).first()
                    if not membership:
                        membership = OrganizationMembership(
                            user_id=user.id, organization_id=org.id, is_gm=True
                        )
                        db.session.add(membership)
                        print(f"[migrate] Promoted {user.email} to GM.")
                    else:
                        membership.is_gm = True
                        print(f"[migrate] {user.email} is already GM.")

                    # Ensure team assignment
                    ta = TeamAssignment.query.filter_by(
                        user_id=user.id, team_id=team.id
                    ).first()
                    if not ta:
                        ta = TeamAssignment(user_id=user.id, team_id=team.id, is_coach=True)
                        db.session.add(ta)
                        print(f"[migrate] Assigned {user.email} as coach.")

                    db.session.commit()
            except Exception as e:
                print(f"[migrate] Warning: admin promotion failed: {e}")
                db.session.rollback()

        # ── 6. Multi-tenant: ensure default org/team and migrate existing data ──
        try:
            org = Organization.query.first()
            if not org:
                org = Organization(name="Default Organization", slug="default")
                db.session.add(org)
                db.session.flush()
                print("[migrate] Created default organization.")
            else:
                print(f"[migrate] Using existing organization: {org.name}")

            team = Team.query.filter_by(organization_id=org.id).first()
            if not team:
                team = Team(name="Default Team", organization_id=org.id, slug="default-team")
                db.session.add(team)
                db.session.flush()
                print("[migrate] Created default team.")
            else:
                print(f"[migrate] Using existing team: {team.name}")

            # Persist org/team now so later introspection fallbacks can
            # safely roll back without discarding them.
            db.session.commit()

            # Assign unassigned users to default org
            unassigned_users = User.query.filter(User.organization_id.is_(None)).all()
            for u in unassigned_users:
                u.organization_id = org.id

                was_admin = False
                try:
                    with db.session.begin_nested():
                        row = db.session.execute(
                            text("SELECT is_admin FROM users WHERE id = :uid"),
                            {"uid": u.id},
                        ).fetchone()
                        was_admin = bool(row[0]) if row else False
                except Exception:
                    pass

                membership = OrganizationMembership.query.filter_by(
                    user_id=u.id, organization_id=org.id
                ).first()
                if not membership:
                    db.session.add(OrganizationMembership(
                        user_id=u.id, organization_id=org.id, is_gm=was_admin
                    ))
                elif was_admin:
                    membership.is_gm = True

                ta = TeamAssignment.query.filter_by(user_id=u.id, team_id=team.id).first()
                if not ta:
                    db.session.add(TeamAssignment(user_id=u.id, team_id=team.id, is_coach=was_admin))
            if unassigned_users:
                print(f"[migrate] Assigned {len(unassigned_users)} user(s) to default org.")

            # Fix existing memberships: promote old admins to GM if they were
            # missed by a previous migration run that set is_gm=False for all.
            try:
                try:
                    cols = db.session.execute(
                        text("PRAGMA table_info(users)")
                    ).fetchall()
                    has_old_admin = any(row[1] == "is_admin" for row in cols)
                except Exception:
                    # Non-SQLite backends (e.g. Postgres) don't support PRAGMA.
                    db.session.rollback()
                    from sqlalchemy import inspect as _inspect

                    with db.engine.connect() as _conn:
                        cols = [
                            c["name"]
                            for c in _inspect(_conn).get_columns("users")
                        ]
                    has_old_admin = "is_admin" in cols
                if has_old_admin:
                    # Raw SQL on legacy columns only: the ORM User model
                    # requires new columns that may not exist yet.
                    rows = db.session.execute(
                        text("SELECT id, is_admin FROM users")
                    ).fetchall()
                    fixed = 0
                    for uid, is_admin in rows:
                        mem = OrganizationMembership.query.filter_by(
                            user_id=uid, organization_id=org.id
                        ).first()
                        if mem and mem.is_gm != bool(is_admin):
                            mem.is_gm = bool(is_admin)
                            fixed += 1
                    if fixed:
                        print(f"[migrate] Fixed GM status for {fixed} existing user(s).")
            except Exception:
                # Never leave a poisoned (aborted) transaction behind:
                # on Postgres any later query in this block would fail.
                db.session.rollback()

            # Assign unassigned games to default team
            unassigned_games = Game.query.filter(Game.team_id.is_(None)).all()
            for g in unassigned_games:
                g.team_id = team.id
            if unassigned_games:
                print(f"[migrate] Assigned {len(unassigned_games)} game(s) to default team.")

            # Assign unassigned plays
            unassigned_plays = Play.query.filter(Play.team_id.is_(None)).all()
            for p in unassigned_plays:
                p.team_id = team.id
            if unassigned_plays:
                print(f"[migrate] Assigned {len(unassigned_plays)} play(s) to default team.")

            # Assign unassigned play types
            unassigned_play_types = PlayType.query.filter(PlayType.team_id.is_(None)).all()
            for pt in unassigned_play_types:
                pt.team_id = team.id
            if unassigned_play_types:
                print(f"[migrate] Assigned {len(unassigned_play_types)} play type(s) to default team.")

            # Assign unassigned lineups
            unassigned_lineups = Lineup.query.filter(Lineup.team_id.is_(None)).all()
            for l in unassigned_lineups:
                l.team_id = team.id
            if unassigned_lineups:
                print(f"[migrate] Assigned {len(unassigned_lineups)} lineup(s) to default team.")

            # Assign season-less games: date-range match, else active season.
            # Seasons are per-team; ensure one exists for the game’s team.
            from core.services.season_service import (
                ensure_default_season,
                match_season_for_date,
            )
            unassigned_season_games = Game.query.filter(Game.season_id.is_(None)).all()
            assigned = 0
            for g in unassigned_season_games:
                if g.team_id is None:
                    continue
                matched = match_season_for_date(g.team_id, g.sort_date)
                if matched is None:
                    matched = ensure_default_season(g.team_id)
                g.season_id = matched.id
                assigned += 1
            if assigned:
                print(f"[migrate] Assigned {assigned} game(s) to seasons.")

            # Assign unassigned players
            unassigned_players = Player.query.filter(Player.team_id.is_(None)).all()
            for p in unassigned_players:
                p.team_id = team.id
            if unassigned_players:
                print(f"[migrate] Assigned {len(unassigned_players)} player(s) to default team.")

            # Assign unassigned system settings
            unassigned_settings = SystemSetting.query.filter(SystemSetting.organization_id.is_(None)).all()
            for s in unassigned_settings:
                s.organization_id = org.id
            if unassigned_settings:
                print(f"[migrate] Assigned {len(unassigned_settings)} setting(s) to default org.")

            db.session.commit()
            print("[migrate] Multi-tenant migration complete.")
        except Exception as e:
            print(f"[migrate] Warning: multi-tenant migration failed: {e}")
            db.session.rollback()

        print("[migrate] Done.")


if __name__ == "__main__":
    run()
