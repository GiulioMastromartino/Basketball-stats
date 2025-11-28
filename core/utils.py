"""
Shared utility functions for basketball statistics calculations
"""

FT_ATTEMPT_WEIGHT = 0.44
THREE_POINT_WEIGHT = 0.5


def safe_divide(numerator, denominator, default=0.0):
    """Safe division with zero-check"""
    return numerator / denominator if denominator != 0 else default


def safe_percentage(numerator, denominator, decimals=1):
    """Calculate percentage safely"""
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
    """Calculate True Shooting Percentage"""
    denominator = 2 * (fga + FT_ATTEMPT_WEIGHT * fta)
    return safe_percentage(points, denominator)


def calculate_efg_percent(fgm, tpm, fga):
    """Calculate Effective Field Goal Percentage"""
    return safe_percentage(fgm + THREE_POINT_WEIGHT * tpm, fga)


def calculate_usg_percent(possessions, team_possessions):
    """Calculate usage percentage"""
    return safe_percentage(possessions, team_possessions)


def calculate_ast_tov_ratio(ast, tov):
    """Calculate assist-to-turnover ratio"""
    return safe_divide(ast, tov, default=ast)


def calculate_oreb_percent(oreb, total_reb):
    """Calculate offensive rebound percentage"""
    return safe_percentage(oreb, total_reb)


def calculate_efficiency(points, reb, ast, stl, blk, fgm, fga, ftm, fta, tov):
    """Calculate player efficiency rating"""
    return (
        points + reb + ast + stl + blk
        - (fga - fgm)
        - (fta - ftm)
        - tov
    )


def calculate_two_point_stats(fgm, fga, tpm, tpa):
    """Calculate 2-point makes, attempts, and percentage"""
    two_pt_made = fgm - tpm
    two_pt_att = fga - tpa
    two_pt_pct = safe_percentage(two_pt_made, two_pt_att)
    
    return {
        'two_pt_made': two_pt_made,
        'two_pt_att': two_pt_att,
        'two_pt_pct': two_pt_pct
    }


def calculate_fta_rate(fta, fga):
    """Calculate free throw attempt rate (FTA/FGA)"""
    return safe_percentage(fta, fga)


def normalize_per_100_possessions(value, possessions):
    """Normalize a counting stat to per 100 possessions"""
    return safe_divide(value * 100, possessions)


def calculate_per_100_minutes(value, minutes):
    """Normalize stat to per 100 minutes"""
    return safe_divide(value * 100, minutes)
