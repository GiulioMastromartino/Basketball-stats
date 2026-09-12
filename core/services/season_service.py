"""Season management: per-team seasons scoping games and stats."""

from datetime import datetime

from core.models import Game, Season, db


def _validate_range(start_date: str, end_date: str) -> None:
    if not start_date or not end_date or start_date > end_date:
        raise ValueError("Season start_date must be on or before end_date (YYYY-MM-DD)")


def list_seasons(team_id: int):
    return (
        Season.query.filter_by(team_id=team_id)
        .order_by(Season.start_date.desc())
        .all()
    )


def get_season(season_id: int, team_id: int = None):
    query = Season.query.filter_by(id=season_id)
    if team_id is not None:
        query = query.filter_by(team_id=team_id)
    return query.first()


def get_active_season(team_id: int):
    return (
        Season.query.filter_by(team_id=team_id, is_active=True)
        .order_by(Season.start_date.desc())
        .first()
    )


def create_season(team_id: int, name: str, start_date: str, end_date: str,
                  set_active: bool = False) -> Season:
    name = (name or "").strip()
    if not name:
        raise ValueError("Season name is required")
    _validate_range(start_date, end_date)
    if Season.query.filter_by(team_id=team_id, name=name).first():
        raise ValueError(f"Season '{name}' already exists")
    season = Season(team_id=team_id, name=name, start_date=start_date,
                    end_date=end_date, is_active=False)
    db.session.add(season)
    db.session.flush()
    if set_active or get_active_season(team_id) is None:
        set_active_season(team_id, season.id)
    db.session.commit()
    return season


def set_active_season(team_id: int, season_id: int) -> Season:
    if team_id is None:
        raise ValueError("team_id is required")
    season = get_season(season_id, team_id)
    if season is None:
        raise ValueError("Season not found")
    Season.query.filter_by(team_id=team_id, is_active=True).update({"is_active": False})
    season.is_active = True
    db.session.commit()
    return season


def delete_season(team_id: int, season_id: int) -> None:
    if team_id is None:
        raise ValueError("team_id is required")
    season = get_season(season_id, team_id)
    if season is None:
        raise ValueError("Season not found")
    if Game.query.filter_by(season_id=season.id).count():
        raise ValueError("Cannot delete a season that has games assigned")
    db.session.delete(season)
    db.session.commit()


def match_season_for_date(team_id: int, sort_date: str):
    """Return the team's season whose [start_date, end_date] contains sort_date."""
    if not sort_date:
        return None
    return (
        Season.query.filter(
            Season.team_id == team_id,
            Season.start_date <= sort_date,
            Season.end_date >= sort_date,
        )
        .order_by(Season.start_date.desc())
        .first()
    )


def resolve_season_id(team_id: int, season_id: int = None, sort_date: str = None):
    """Resolve which season a game belongs to.

    Precedence: explicit season_id (validated against the team) >
    date-range match > active season > None (unassigned).
    """
    if season_id is not None:
        season = get_season(season_id, team_id)
        return season.id if season else None
    if team_id is None:
        return None
    matched = match_season_for_date(team_id, sort_date)
    if matched:
        return matched.id
    active = get_active_season(team_id)
    return active.id if active else None


def current_season_id_from_session(session, team_id: int):
    """Session-selected season id, or 'ALL' when no specific season is chosen."""
    raw = (session.get("current_season_id") or "ALL")
    if raw == "ALL":
        return "ALL"
    try:
        season_id = int(raw)
    except (TypeError, ValueError):
        return "ALL"
    if get_season(season_id, team_id) is None:
        return "ALL"
    return season_id


def resolve_request_season_id(team_id: int, persist: bool = True):
    """Season scope for the current request: `?season=<id|ALL>` override
    (persisted to the session unless persist=False, for read-only contexts
    like PDF report routes) falling back to the session selection."""
    from flask import request, session

    raw = request.args.get("season")
    if raw is not None:
        raw = raw.strip() or "ALL"
        if raw != "ALL":
            try:
                candidate = int(raw)
            except (TypeError, ValueError):
                candidate = None
            raw = candidate if get_season(candidate, team_id) else "ALL"
        if persist:
            session["current_season_id"] = raw
        return raw
    return current_season_id_from_session(session, team_id)


def season_name_for_date(sort_date: str) -> tuple[str, str, str]:
    """Basketball season for a YYYY-MM-DD date: 1 Sept -> 30 June.

    Returns (name, start_date, end_date), e.g. ("2025/2026", "2025-09-01",
    "2026-06-30"). Name uses full years: yearStart/yearEnd.
    """
    year, month = int(sort_date[:4]), int(sort_date[5:7])
    start_year = year if month >= 9 else year - 1
    end_year = start_year + 1
    return (
        f"{start_year}/{end_year}",
        f"{start_year}-09-01",
        f"{end_year}-06-30",
    )


def ensure_default_season(team_id: int, sort_date: str = None) -> Season:
    """Provision the team's season, following the Sept-June convention."""
    active = get_active_season(team_id)
    if active:
        return active
    existing = list_seasons(team_id)
    if existing:
        return set_active_season(team_id, existing[0].id)
    today = sort_date or datetime.utcnow().strftime("%Y-%m-%d")
    name, start_date, end_date = season_name_for_date(today)
    return create_season(
        team_id,
        name=name,
        start_date=start_date,
        end_date=end_date,
        set_active=True,
    )
