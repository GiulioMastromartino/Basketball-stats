#!/usr/bin/env python3
"""
Production migration script.

Replaces the fragile `flask db init && flask db migrate && flask db upgrade`
chain that broke whenever the container was rebuilt (missing revision history).

Strategy:
  1. db.create_all()        - creates any missing tables, never drops existing ones
  2. Seed players           - populate players from distinct player_stats names (idempotent)
  3. Activate inactive      - fix any players seeded with active=0
  4. alembic stamp head     - baseline for future flask db migrate / upgrade
  5. promote_admin          - elevate ADMIN_EMAIL user if present

Safe to re-run on every deploy.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web import create_app
from core.models import db, Player, PlayerStat, User


def run():
    app = create_app()

    with app.app_context():
        # ── 1. Create all tables that don't exist yet ──────────────────────
        print("[migrate] Running db.create_all()...")
        db.create_all()
        print("[migrate] db.create_all() complete.")

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
                if user:
                    if user.role != "admin":
                        user.role = "admin"
                        user.is_admin = True
                        db.session.commit()
                        print(f"[migrate] Promoted {user.email} to admin.")
                    else:
                        print(f"[migrate] {user.email} is already admin.")
                else:
                    print(f"[migrate] User {admin_email} not found yet (will be promoted on first login).")
            except Exception as e:
                print(f"[migrate] Warning: admin promotion failed: {e}")
                db.session.rollback()

        print("[migrate] Done.")


if __name__ == "__main__":
    run()
