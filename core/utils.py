"""
Shared utility functions for basketball statistics calculations
"""
from statistics import mean

FT_ATTEMPT_WEIGHT = 0.44
THREE_POINT_WEIGHT = 0.5


def safe_divide(numerator, denominator, default=0.0):
    """Safe division with zero-check"""
    return numerator / denominator if denominator != 0 else default


def safe_percentage(numerator, denominator, decimals=1):
    """Calculate percentage safely (returns 0-100 range)"""
    result = safe_divide(numerator * 100, denominator)
    return round(result, decimals)


def parse_minutes(minutes_str):
    """Convert MM:SS string to decimal minutes"""
    if not minutes_str or minutes_str in ["00:00", "0", "0:00"]:
        return 0.0

    try:
        if ":" in minutes_str:
            parts = minutes_str.split(":")
            if len(parts) != 2:
                return 0.0
            minutes, seconds = map(int, parts)
            if not (0 <= seconds < 60):
                return 0.0
            return float(minutes) + (seconds / 60.0)
        return float(minutes_str)
    except (ValueError, AttributeError):
        return 0.0


def calculate_possessions(fga, fta, oreb, tov):
    """Calculate possessions used by a player"""
    return fga + (FT_ATTEMPT_WEIGHT * fta) - oreb + tov


def calculate_ortg(points, possessions):
    """Calculate offensive rating (points per 100 possessions)"""
    return safe_divide(points * 100, possessions)


def calculate_ppp(points, possessions):
    """Calculate points per possession"""
    return safe_divide(points, possessions)


def calculate_ts_percent(points, fga, fta):
    """Calculate True Shooting Percentage (returns 0-100)"""
    denominator = 2 * (fga + FT_ATTEMPT_WEIGHT * fta)
    return safe_percentage(points, denominator)


def calculate_efg_percent(fgm, tpm, fga):
    """Calculate Effective Field Goal Percentage (returns 0-100)"""
    return safe_percentage(fgm + THREE_POINT_WEIGHT * tpm, fga)


def calculate_usg_percent(possessions, team_possessions):
    """Calculate usage percentage (returns 0-100)"""
    return safe_percentage(possessions, team_possessions)


def calculate_ast_tov_ratio(ast, tov):
    """Calculate assist-to-turnover ratio"""
    return safe_divide(ast, tov, default=ast)


def calculate_oreb_percent(oreb, total_reb):
    """Calculate offensive rebound percentage (returns 0-100)"""
    return safe_percentage(oreb, total_reb)


def calculate_efficiency(points, reb, ast, stl, blk, fgm, fga, ftm, fta, tov):
    """Calculate player efficiency rating"""
    return points + reb + ast + stl + blk - (fga - fgm) - (fta - ftm) - tov


def calculate_game_score(points, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov):
    """
    Calculate Hollinger's Game Score
    Formula: PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM) + 0.7*OREB + 0.3*DREB 
             + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV
    """
    game_score = (
        points
        + 0.4 * fgm
        - 0.7 * fga
        - 0.4 * (fta - ftm)
        + 0.7 * oreb
        + 0.3 * dreb
        + stl
        + 0.7 * ast
        + 0.7 * blk
        - 0.4 * pf
        - tov
    )
    return game_score


def calculate_two_point_stats(fgm, fga, tpm, tpa):
    """Calculate 2-point makes, attempts, and percentage (returns percentage 0-100)"""
    two_pt_made = fgm - tpm
    two_pt_att = fga - tpa
    two_pt_pct = safe_percentage(two_pt_made, two_pt_att)

    return {
        "two_pt_made": two_pt_made,
        "two_pt_att": two_pt_att,
        "two_pt_pct": two_pt_pct,
    }


def calculate_fta_rate(fta, fga):
    """Calculate free throw attempt rate (returns 0-100)"""
    return safe_percentage(fta, fga)


def normalize_per_100_possessions(value, possessions):
    """Normalize a counting stat to per 100 possessions"""
    return safe_divide(value * 100, possessions)


def calculate_per_100_minutes(value, minutes):
    """Normalize stat to per 100 minutes"""
    return safe_divide(value * 100, minutes)


def normalize_date_to_display(date_str: str) -> str:
    """Return DD/MM/YYYY."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    date_str = date_str.replace("-", "/")
    parts = date_str.split("/")
    if len(parts) != 3:
        return ""
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
            "points": 0, "ppg": 0, "minutes": 0, "mpg": 0,
            "reb": 0, "rpg": 0, "ast": 0, "apg": 0,
            "fgm": 0, "fga": 0, "fg_percent": 0,
            "tpm": 0, "tpa": 0, "tp_percent": 0,
            "ftm": 0, "fta": 0, "ft_percent": 0,
            "oreb": 0, "dreb": 0,
            "stl": 0, "spg": 0, "blk": 0, "bpg": 0, 
            "tov": 0, "topg": 0, "pf": 0, "pfpg": 0,
            "pm": 0, "games_played": 0
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
    total_pm = sum(getattr(s, 'plus_minus', 0) for s in stats)

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
        
        "games_played": count
    }
