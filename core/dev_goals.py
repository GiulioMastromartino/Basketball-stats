"""Development-goal tracking (Slice N4 / P3 remainder).

Per-player rolling-window goals such as "FT% >= 75 over the next 5" with
live progress bars computed from PlayerStat rows.
"""

# metric -> (label, lower_is_better)
METRICS = {
    "points": ("Points", False),
    "reb": ("Rebounds", False),
    "ast": ("Assists", False),
    "stl": ("Steals", False),
    "blk": ("Blocks", False),
    "tov": ("Turnovers", True),
    "fg_percent": ("FG%", False),
    "tp_percent": ("3PT%", False),
    "ft_percent": ("FT%", False),
}

DEFAULT_WINDOW = 5


def validate_goal(player_name: str, metric: str, target, window) -> list:
    """Return human-readable problems (empty == valid)."""
    errors = []
    if not (player_name or "").strip():
        errors.append("player_name is required")
    if metric not in METRICS:
        errors.append(f"metric must be one of: {', '.join(sorted(METRICS))}")
    try:
        float(target)
    except (TypeError, ValueError):
        errors.append("target must be a number")
    try:
        window = int(window)
    except (TypeError, ValueError):
        errors.append("window must be an integer")
        return errors
    if not 1 <= window <= 20:
        errors.append("window must be between 1 and 20 games")
    return errors


def goal_progress(goal) -> dict:
    """Progress of a DevelopmentGoal over its rolling window.

    Uses the team's most recent ``window`` games (by sort_date); games the
    player missed simply don't count. Returns current average, games used,
    and whether the target is met.
    """
    from core.models import Game, PlayerStat

    label, lower_is_better = METRICS[goal.metric]
    games = (Game.query.filter_by(team_id=goal.team_id)
             .order_by(Game.sort_date.desc(), Game.id.desc())
             .limit(goal.window).all())
    game_ids = [g.id for g in games]
    rows = []
    if game_ids:
        rows = (PlayerStat.query
                .filter(PlayerStat.game_id.in_(game_ids),
                        PlayerStat.player_name == goal.player_name)
                .all())
    values = [float(getattr(r, goal.metric, 0) or 0) for r in rows]
    current = round(sum(values) / len(values), 1) if values else 0.0
    if lower_is_better:
        achieved = bool(values) and current <= float(goal.target)
        remaining = round(current - float(goal.target), 1)
    else:
        achieved = bool(values) and current >= float(goal.target)
        remaining = round(float(goal.target) - current, 1)
    return {
        "goal_id": goal.id,
        "player_name": goal.player_name,
        "metric": goal.metric,
        "metric_label": label,
        "target": float(goal.target),
        "window": goal.window,
        "games_used": len(values),
        "current": current,
        "remaining": max(0.0, remaining) if not achieved else 0.0,
        "achieved": achieved,
    }
