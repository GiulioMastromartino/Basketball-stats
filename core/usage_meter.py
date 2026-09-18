"""Usage metering (SaaS readiness, light).

Per-org counters in ``SystemSetting`` (``usage.<name>``) for billable-ish
activity: share actions, API imports, PDF-family renders. Backed by the DB
so counts survive restarts; :func:`bump` never raises (metering must not
break the request it measures).
"""

COUNTERS = ("halftime_shares", "comms_previews", "video_exports",
            "api_imports", "social_cards")


def _key(name: str) -> str:
    return f"usage.{name}"


def bump(name: str, amount: int = 1) -> int:
    """Increment counter ``name``; returns the new value (0 on error)."""
    if name not in COUNTERS:
        raise ValueError(f"unknown usage counter: {name}")
    try:
        from core.models import SystemSetting, db

        row = SystemSetting.query.filter_by(key=_key(name)).first()
        current = int((row.value if row else None) or 0)
        current += max(0, int(amount or 0))
        if row is None:
            row = SystemSetting(key=_key(name),
                                description="Usage metering counter")
            db.session.add(row)
        row.value = str(current)
        db.session.commit()
        return current
    except Exception:
        try:
            from core.models import db as _db
            _db.session.rollback()
        except Exception:
            pass
        return 0


def get_usage() -> dict:
    """Return all counters (missing rows read as 0; never raises)."""
    try:
        from core.models import SystemSetting

        rows = SystemSetting.query.filter(
            SystemSetting.key.like("usage.%")).all()
        values = {r.key[len("usage."):]: int(r.value or 0) for r in rows}
    except Exception:
        values = {}
    return {name: values.get(name, 0) for name in COUNTERS}
