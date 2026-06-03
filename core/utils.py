"""
Shared utility functions for basketball statistics calculations.

Re-exports from core.stat_formulas (the single source of truth for NBA-standard formulas).
New code should import directly from core.stat_formulas.
"""

from statistics import mean
from core import rust_analytics
from core.stat_formulas import (
    FT_ATTEMPT_WEIGHT,
    THREE_POINT_WEIGHT,
    safe_divide,
    safe_percentage,
    parse_minutes as _parse_minutes,
    possessions as _possessions,
    offensive_rating as _offensive_rating,
    true_shooting_percent as _true_shooting_percent,
    effective_field_goal_percent as _effective_field_goal_percent,
    usage_percent as _usage_percent,
    ast_tov_ratio as _ast_tov_ratio,
    player_efficiency_rating as _player_efficiency_rating,
    game_score as _game_score,
    two_point_stats as _two_point_stats,
    fta_rate as _fta_rate,
    per_100_possessions as _per_100_possessions,
    per_100_minutes as _per_100_minutes,
    pace as _pace,
)


def parse_minutes(minutes_str):
    """Convert MM:SS string to decimal minutes"""
    return _parse_minutes(minutes_str)


def calculate_possessions(fga, fta, oreb, tov):
    """Calculate possessions used by a player using Rust."""
    return _possessions(fga, fta, oreb, tov)


def calculate_ortg(points, possessions):
    """Calculate offensive rating (points per 100 possessions) using Rust."""
    return _offensive_rating(points, possessions)


def calculate_ppp(points, possessions):
    """Calculate points per possession"""
    return safe_divide(points, possessions)


def calculate_ts_percent(points, fga, fta):
    """Calculate True Shooting Percentage using Rust (returns 0-100)"""
    return _true_shooting_percent(points, fga, fta)


def calculate_efg_percent(fgm, tpm, fga):
    """Calculate Effective Field Goal Percentage using Rust (returns 0-100)"""
    return _effective_field_goal_percent(fgm, tpm, fga)


def calculate_usg_percent(possessions, team_possessions):
    """Calculate usage percentage (returns 0-100).

    Note: This is a simplified version that does not account for minutes.
    For the NBA-standard formula (Dean Oliver with minutes scaling),
    use stat_formulas.usage_percent() instead.
    """
    return safe_percentage(possessions, team_possessions)


def calculate_ast_tov_ratio(ast, tov):
    """Calculate assist-to-turnover ratio"""
    return _ast_tov_ratio(ast, tov)


def calculate_oreb_percent(oreb, total_reb):
    """Calculate offensive rebound percentage (returns 0-100).

    Note: This computes OREB / TotalRebounds, which differs from the
    NBA-standard ORB% formula (OREB / (OREB + OppDREB)). Use
    stat_formulas.orb_pct() when opponent DREB is available.
    """
    return safe_percentage(oreb, total_reb)


def calculate_efficiency(points, reb, ast, stl, blk, fgm, fga, ftm, fta, tov):
    """Calculate player efficiency rating"""
    return _player_efficiency_rating(points, reb, ast, stl, blk, fgm, fga, ftm, fta, tov)


def calculate_game_score(
    points, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov
):
    """Calculate Hollinger's Game Score"""
    return _game_score(points, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov)


def calculate_two_point_stats(fgm, fga, tpm, tpa):
    """Calculate 2-point makes, attempts, and percentage (returns percentage 0-100)"""
    return _two_point_stats(fgm, fga, tpm, tpa)


def calculate_fta_rate(fta, fga):
    """Calculate free throw attempt rate (returns 0-100)"""
    return _fta_rate(fta, fga)


def normalize_per_100_possessions(value, possessions):
    """Normalize a counting stat to per 100 possessions"""
    return _per_100_possessions(value, possessions)


def calculate_per_100_minutes(value, minutes):
    """Normalize stat to per 100 minutes"""
    return _per_100_minutes(value, minutes)


def calculate_pace(possessions, minutes, standard_game_minutes=40.0):
    """Calculate pace (possessions per standard game length)"""
    return _pace(possessions, minutes, standard_game_minutes)


def normalize_date_to_display(date_str: str) -> str:
    """Return DD/MM/YYYY. Supports both DD-MM-YYYY and YYYY-MM-DD."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    date_str = date_str.replace("-", "/")
    parts = date_str.split("/")
    if len(parts) != 3:
        return ""

    # Detect if it's YYYY-MM-DD or DD-MM-YYYY
    if len(parts[0]) == 4:
        # YYYY/MM/DD
        year, month, day = parts
    else:
        # DD/MM/YYYY
        day, month, year = parts

    if len(year) == 2:
        year = f"20{year}"
    return f"{int(day):02d}/{int(month):02d}/{int(year):04d}"


def get_player_stats_averages(stats):
    """
    Calculate average statistics for a list of PlayerStat objects.
    Returns a dictionary of averages with per-game naming (ppg, rpg, apg, etc.).
    """
    if not stats:
        return {
            "points": 0,
            "ppg": 0,
            "minutes": 0,
            "mpg": 0,
            "reb": 0,
            "rpg": 0,
            "ast": 0,
            "apg": 0,
            "fgm": 0,
            "fga": 0,
            "fg_percent": 0,
            "tpm": 0,
            "tpa": 0,
            "tp_percent": 0,
            "ftm": 0,
            "fta": 0,
            "ft_percent": 0,
            "oreb": 0,
            "dreb": 0,
            "stl": 0,
            "spg": 0,
            "blk": 0,
            "bpg": 0,
            "tov": 0,
            "topg": 0,
            "pf": 0,
            "pfpg": 0,
            "pm": 0,
            "games_played": 0,
        }

    count = len(stats)

    # Calculate simple totals
    total_points = sum(s.points for s in stats)
    total_minutes = sum(parse_minutes(s.minutes) for s in stats)
    total_reb = sum(s.reb for s in stats)
    total_ast = sum(s.ast for s in stats)
    total_fgm = sum(s.fgm for s in stats)
    total_fga = sum(s.fga for s in stats)
    total_tpm = sum(s.tpm for s in stats)
    total_tpa = sum(s.tpa for s in stats)
    total_ftm = sum(s.ftm for s in stats)
    total_fta = sum(s.fta for s in stats)
    total_oreb = sum(s.oreb for s in stats)
    total_dreb = sum(s.dreb for s in stats)
    total_stl = sum(s.stl for s in stats)
    total_blk = sum(s.blk for s in stats)
    total_tov = sum(s.tov for s in stats)
    total_pf = sum(s.pf for s in stats)
    # Handle potentially missing plus_minus attribute safely
    total_pm = sum(getattr(s, "plus_minus", 0) for s in stats)

    avg_points = round(total_points / count, 1)
    avg_minutes = round(total_minutes / count, 1)
    avg_reb = round(total_reb / count, 1)
    avg_ast = round(total_ast / count, 1)
    avg_stl = round(total_stl / count, 1)
    avg_blk = round(total_blk / count, 1)
    avg_tov = round(total_tov / count, 1)
    avg_pf = round(total_pf / count, 1)
    avg_pm = round(total_pm / count, 1)

    return {
        # Totals (used for calculations)
        "points": avg_points,
        "minutes": avg_minutes,
        "reb": avg_reb,
        "ast": avg_ast,
        "fgm": round(total_fgm / count, 1),
        "fga": round(total_fga / count, 1),
        "fg_percent": safe_percentage(total_fgm, total_fga),
        "tpm": round(total_tpm / count, 1),
        "tpa": round(total_tpa / count, 1),
        "tp_percent": safe_percentage(total_tpm, total_tpa),
        "ftm": round(total_ftm / count, 1),
        "fta": round(total_fta / count, 1),
        "ft_percent": safe_percentage(total_ftm, total_fta),
        "oreb": round(total_oreb / count, 1),
        "dreb": round(total_dreb / count, 1),
        "stl": avg_stl,
        "blk": avg_blk,
        "tov": avg_tov,
        "pf": avg_pf,
        "pm": avg_pm,
        # Per-game aliases (for template compatibility)
        "ppg": avg_points,
        "mpg": avg_minutes,
        "rpg": avg_reb,
        "apg": avg_ast,
        "spg": avg_stl,
        "bpg": avg_blk,
        "topg": avg_tov,
        "pfpg": avg_pf,
        "games_played": count,
    }


def normalize_shot_events(shot_events):
    """
    Normalize shot event coordinates for detail views.
    Converts court coordinates (0-500, 0-470) to percentages (0-100) and
    normalizes already-normalized values. Returns a list of SimpleNamespace
    objects with attributes: game, x_loc, y_loc, result, shot_type, points.
    """
    from types import SimpleNamespace

    normalized = []
    for s in shot_events:
        x = s.x_loc
        y = s.y_loc
        if s.x_loc is not None and s.y_loc is not None:
            x = float(s.x_loc)
            y = float(s.y_loc)
            if x > 100 or y > 100:
                x = (x / 500.0) * 100.0
                y = (y / 470.0) * 100.0
            elif 0 <= x <= 1 and 0 <= y <= 1:
                x *= 100.0
                y *= 100.0
            x = max(0.0, min(100.0, x))
            y = max(0.0, min(100.0, y))
        normalized.append(
            SimpleNamespace(
                game=s.game,
                x_loc=x,
                y_loc=y,
                result=s.result,
                shot_type=s.shot_type,
                points=s.points,
            )
        )
    return normalized


def format_total_minutes(total_minutes):
    """
    Format total minutes (float) as MM:SS string.
    Example: 65.5 minutes -> "65:30"
    """
    whole_minutes = int(total_minutes)
    seconds = int(round((total_minutes - whole_minutes) * 60))
    if seconds == 60:
        whole_minutes += 1
        seconds = 0
    return f"{whole_minutes:02d}:{seconds:02d}"
