"""Usage metering (SaaS readiness, light).

Per-organization counters in ``SystemSetting`` (``usage.<name>.org<id>``)
for billable-ish activity: share actions, API imports, PDF-family
renders. Backed by the DB so counts survive restarts.

Contract: :func:`bump` never raises for *known* counters (returns 0 on
DB trouble so metering can't break the request it measures); unknown
counter names raise ``ValueError`` immediately since those are always
programmer errors. Increments are single-statement upserts
(``ON CONFLICT DO UPDATE``, valid on both PostgreSQL and SQLite), so
concurrent workers can't lose counts.
"""

from sqlalchemy import text

COUNTERS = ("halftime_shares", "comms_previews", "video_exports",
            "api_imports", "social_cards")


def _key(name: str, organization_id=None) -> str:
    base = f"usage.{name}"
    if organization_id is None:
        return base
    return f"{base}.org{int(organization_id)}"


def _org_id_for_team(team_id):
    """Organization owning a team (None when unresolvable — global key)."""
    if team_id is None:
        return None
    try:
        from core.models import Team
        team = Team.query.get(team_id)
        return team.organization_id if team else None
    except Exception:
        return None


def bump(name: str, amount: int = 1, team_id=None) -> int:
    """Increment counter ``name``; returns the new value (0 on error)."""
    if name not in COUNTERS:
        raise ValueError(f"unknown usage counter: {name}")
    try:
        from core.models import SystemSetting, db

        org_id = _org_id_for_team(team_id)
        key = _key(name, org_id)
        inc = max(0, int(amount or 0))
        db.session.execute(
            text(
                "INSERT INTO system_settings "
                "(key, value, description, organization_id) "
                "VALUES (:k, :v0, 'Usage metering counter', :org) "
                "ON CONFLICT(key) DO UPDATE SET value = "
                "CAST(system_settings.value AS INTEGER) + :inc"
            ),
            {"k": key, "v0": str(inc), "org": org_id, "inc": inc},
        )
        db.session.commit()
        row = SystemSetting.query.filter_by(key=key).first()
        return int((row.value if row else None) or 0)
    except Exception:
        try:
            from core.models import db as _db
            _db.session.rollback()
        except Exception:
            pass
        return 0


def get_usage(team_id=None) -> dict:
    """Return all counters for a team (or global ones; never raises)."""
    org_id = _org_id_for_team(team_id)
    try:
        from core.models import SystemSetting

        rows = SystemSetting.query.filter(
            SystemSetting.key.like("usage.%")).all()
        values = {}
        for r in rows:
            key = r.key[len("usage."):]
            if key.endswith(f".org{org_id}") if org_id is not None else \
                    ("." not in key):
                values[key] = int(r.value or 0)
    except Exception:
        values = {}
    if org_id is not None:
        return {name: values.get(f"{name}.org{org_id}", 0)
                for name in COUNTERS}
    return {name: values.get(name, 0) for name in COUNTERS}
