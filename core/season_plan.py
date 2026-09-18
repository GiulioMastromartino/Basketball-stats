"""Season planner (Slice N2).

Sept–June calendar (the org season convention) with per-month game density
and load-management flags. Pure functions over ``YYYY-MM-DD`` dated games
so the planner is unit-testable without a database.
"""

SEASON_MONTHS = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun"]

# Month index (1-12) -> season column. July/August are off-season.
_MONTH_TO_COLUMN = {9: 0, 10: 1, 11: 2, 12: 3, 1: 4, 2: 5,
                    3: 6, 4: 7, 5: 8, 6: 9}

# Phase focus per season column (0-9).
_PHASE_FOCUS = (
    "Preseason: conditioning + install base offense",
    "Early season: rotation auditions, keep minutes even",
    "Early season: lock 9-man rotation",
    "Holiday stretch: load management, protect legs",
    "Mid season: peak intensity, scout-driven prep",
    "Mid season: playoff seeding push",
    "Playoff prep: shorten rotation, clutch lineups",
    "Playoffs: 8-man rotation, matchup game-plans",
    "Playoffs/finals: recovery-first scheduling",
    "Transition: exit interviews, development plans",
)

HIGH_LOAD_GAMES = 8   # >8 games in a month -> rotate deep
LOW_LOAD_GAMES = 3    # <3 games in a month -> development window


def month_column(month: int):
    """Map calendar month (1-12) to a 0-9 season column (None off-season)."""
    return _MONTH_TO_COLUMN.get(month)


def load_flag(game_count: int) -> str:
    """Classify a month's load for rotation guidance."""
    if game_count > HIGH_LOAD_GAMES:
        return "high"
    if game_count < LOW_LOAD_GAMES:
        return "development"
    return "normal"


def build_season_plan(games_by_month: dict, season_label: str = "") -> dict:
    """Build the Sept–June calendar from {month_number: game_count}.

    Returns ``{"season": label, "months": [...], "summary": {...}}`` where
    each month row carries focus text, load flag, and rotation guidance.
    Unknown/off-season months are ignored.
    """
    months = []
    for month_num, label in zip(
        (9, 10, 11, 12, 1, 2, 3, 4, 5, 6), SEASON_MONTHS
    ):
        count = int((games_by_month or {}).get(month_num, 0) or 0)
        flag = load_flag(count)
        if flag == "high":
            rotation = "Rotate 10+: cap starters, rest vets in low-leverage games"
        elif flag == "development":
            rotation = "Development window: bench minutes, try new lineups"
        else:
            rotation = "Standard 9-man rotation"
        months.append({
            "month": label,
            "month_number": month_num,
            "games": count,
            "load": flag,
            "focus": _PHASE_FOCUS[_MONTH_TO_COLUMN[month_num]],
            "rotation_guidance": rotation,
        })
    total = sum(m["games"] for m in months)
    peak = max(months, key=lambda m: m["games"])
    return {
        "season": season_label,
        "months": months,
        "summary": {
            "total_games": total,
            "peak_month": peak["month"],
            "high_load_months": [m["month"] for m in months if m["load"] == "high"],
            "development_months": [m["month"] for m in months
                                   if m["load"] == "development"],
        },
    }


def _coerce_season_id(season_id):
    """Normalize a season scope to int | 'ALL' (raises ValueError if bad).

    Routes validate user input before calling; this guards the contract
    for any other (programmer) caller.
    """
    if season_id is None or season_id == "ALL":
        return "ALL"
    try:
        return int(season_id)
    except (TypeError, ValueError):
        raise ValueError(f"invalid season_id: {season_id!r}")


def games_per_month(team_id: int, season_id=None) -> dict:
    """Count a team's games per calendar month from ``Game.sort_date``."""
    from core.models import Game

    season_id = _coerce_season_id(season_id)
    query = Game.query.filter_by(team_id=team_id)
    if season_id != "ALL":
        query = query.filter(Game.season_id == season_id)
    counts = {}
    for game in query.all():
        try:
            month = int((game.sort_date or "").split("-")[1])
        except (IndexError, ValueError, AttributeError):
            continue
        if month in _MONTH_TO_COLUMN:
            counts[month] = counts.get(month, 0) + 1
    return counts
