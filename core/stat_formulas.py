"""
NBA-standard basketball statistics formulas.

Single source of truth for all stat computations.
Formulas follow NBA.com and basketball-reference.com conventions.
"""

from core import rust_analytics

# =============================================================================
# Constants
# =============================================================================
FT_ATTEMPT_WEIGHT = 0.44
THREE_POINT_WEIGHT = 0.5
CLUTCH_MARGIN = 5
CLUTCH_TIME_SECONDS = 300


# =============================================================================
# Helpers
# =============================================================================
def safe_divide(numerator, denominator, default=0.0):
    return numerator / denominator if denominator != 0 else default


def safe_percentage(numerator, denominator, decimals=1):
    return rust_analytics.safe_percentage(int(numerator), int(denominator))


def _plays_used(fga, fta, tov):
    """Total play attempts (denominator for TOV%, USG%)."""
    return fga + FT_ATTEMPT_WEIGHT * fta + tov


def _dean_oliver_possessions(fga, fta, oreb, tov):
    """Dean Oliver possessions estimate."""
    return fga + FT_ATTEMPT_WEIGHT * fta - oreb + tov


def parse_minutes(minutes_str):
    """Convert MM:SS string to decimal minutes."""
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


# =============================================================================
# Shooting Percentages
# =============================================================================
def field_goal_percent(fgm, fga):
    """FG% = FGM / FGA * 100"""
    return safe_percentage(fgm, fga)


def three_point_percent(tpm, tpa):
    """3P% = 3PM / 3PA * 100"""
    return safe_percentage(tpm, tpa)


def free_throw_percent(ftm, fta):
    """FT% = FTM / FTA * 100"""
    return safe_percentage(ftm, fta)


def effective_field_goal_percent(fgm, tpm, fga):
    """eFG% = (FGM + 0.5 * 3PM) / FGA * 100"""
    return rust_analytics.calculate_efg_pct(int(fgm), int(tpm), int(fga))


def true_shooting_percent(points, fga, fta):
    """TS% = PTS / (2 * (FGA + 0.44 * FTA)) * 100"""
    return rust_analytics.calculate_true_shooting_pct(int(points), int(fga), int(fta))


def two_point_stats(fgm, fga, tpm, tpa):
    """2-point makes, attempts, and percentage."""
    two_pt_made = fgm - tpm
    two_pt_att = fga - tpa
    two_pt_pct = safe_percentage(two_pt_made, two_pt_att)
    return {
        "two_pt_made": two_pt_made,
        "two_pt_att": two_pt_att,
        "two_pt_pct": two_pt_pct,
    }


# =============================================================================
# Possessions
# =============================================================================
def possessions(fga, fta, oreb, tov):
    """Dean Oliver possessions: FGA + 0.44*FTA - OREB + TOV"""
    return rust_analytics.calculate_possessions(int(fga), int(fta), int(oreb), int(tov))


def player_possessions_used(fga, fta, tov):
    """Player possessions used (for USG%): FGA + 0.44*FTA + TOV"""
    return _plays_used(fga, fta, tov)


# =============================================================================
# Efficiency Ratings
# =============================================================================
def offensive_rating(points, possessions):
    """ORtg = PTS / Poss * 100 (points per 100 possessions)"""
    return rust_analytics.calculate_offensive_rating(int(points), int(possessions))


def defensive_rating(points_allowed, opponent_possessions):
    """DRtg = OppPTS / OppPoss * 100"""
    return rust_analytics.calculate_defensive_rating(int(points_allowed), int(opponent_possessions))


def net_rating(ortg, drtg):
    """Net Rating = ORtg - DRtg"""
    return ortg - drtg


# =============================================================================
# Four Factors (Dean Oliver via NBA.com conventions)
# =============================================================================
def efg_pct(fgm, tpm, fga):
    """eFG% = (FGM + 0.5 * 3PM) / FGA * 100"""
    return effective_field_goal_percent(fgm, tpm, fga)


def tov_pct(tov, fga, fta, tov_extra=0):
    """TOV% = TOV / (FGA + 0.44*FTA + TOV) * 100

    NBA standard: turnovers per 100 play attempts.
    """
    denom = _plays_used(fga, fta, tov + tov_extra)
    return safe_percentage(tov, denom) if denom > 0 else 0.0


def orb_pct(oreb, opp_dreb):
    """ORB% = OREB / (OREB + OppDREB) * 100

    Percentage of offensive rebounds captured out of total available.
    Only computable when opponent defensive rebounds are available.
    """
    total_available = oreb + opp_dreb
    return safe_percentage(oreb, total_available) if total_available > 0 else 0.0


def ftr(fta, fga):
    """FTr = FTA / FGA

    Free Throw Attempt Rate: how many FTA per FGA.
    NBA standard uses FTA/FGA (attempt rate), not FTM/FGA (make rate).
    """
    return safe_divide(fta, fga)


# =============================================================================
# Player-Level Percentages (NBA.com standard)
# =============================================================================
def usage_percent(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes=200.0):
    """USG% = ((FGA + 0.44*FTA + TOV) * (TeamMin/5)) / (MIN * TeamPoss) * 100

    Percentage of team possessions used by player while on court.
    """
    return rust_analytics.calculate_true_usage_rate(
        int(fga), int(fta), int(tov),
        int(team_fga), int(team_fta), int(team_tov),
        minutes, team_minutes,
    )


def assist_percent(ast, minutes, team_minutes, team_fgm, fgm):
    """AST% = AST / (((MIN / (TeamMin/5)) * TeamFGM) - FGM) * 100

    Estimated percentage of teammate field goals a player assisted while on court.
    """
    team_min_per_five = team_minutes / 5.0
    if minutes <= 0 or team_min_per_five <= 0:
        return 0.0
    teammate_fgm = (minutes / team_min_per_five) * team_fgm - fgm
    if teammate_fgm <= 0:
        return 0.0
    return safe_percentage(ast, teammate_fgm)


def steal_percent(stl, minutes, team_minutes, opp_possessions):
    """STL% = STL * (TeamMin / 5) / (MIN * OppPoss) * 100

    Estimated percentage of opponent possessions ending in a steal by this player.
    """
    if minutes <= 0 or opp_possessions <= 0:
        return 0.0
    team_min_per_five = team_minutes / 5.0
    return safe_percentage(stl * team_min_per_five, minutes * opp_possessions)


def block_percent(blk, minutes, team_minutes, opp_fga, opp_tpa):
    """BLK% = BLK * (TeamMin / 5) / (MIN * Opp2PA) * 100

    Estimated percentage of opponent 2-point attempts blocked by this player.
    """
    opp_2pa = max(0, opp_fga - opp_tpa)
    if minutes <= 0 or opp_2pa <= 0:
        return 0.0
    team_min_per_five = team_minutes / 5.0
    return safe_percentage(blk * team_min_per_five, minutes * opp_2pa)


def def_rebound_percent(dreb, minutes, team_minutes, team_dreb, opp_oreb):
    """DRB% = DREB * (TeamMin / 5) / (MIN * (TeamDREB + OppOREB)) * 100

    Estimated percentage of available defensive rebounds obtained by player.
    """
    if minutes <= 0:
        return 0.0
    available = team_dreb + opp_oreb
    if available <= 0:
        return 0.0
    team_min_per_five = team_minutes / 5.0
    return safe_percentage(dreb * team_min_per_five, minutes * available)


def off_rebound_percent(oreb, minutes, team_minutes, team_oreb, opp_dreb):
    """ORB% (player) = OREB * (TeamMin / 5) / (MIN * (TeamOREB + OppDREB)) * 100

    Estimated percentage of available offensive rebounds obtained by player.
    """
    if minutes <= 0:
        return 0.0
    available = team_oreb + opp_dreb
    if available <= 0:
        return 0.0
    team_min_per_five = team_minutes / 5.0
    return safe_percentage(oreb * team_min_per_five, minutes * available)


def rebound_percent(reb, minutes, team_minutes, team_reb, opp_reb):
    """REB% = REB * (TeamMin / 5) / (MIN * (TeamREB + OppREB)) * 100

    Estimated percentage of all available rebounds obtained by player.
    """
    if minutes <= 0:
        return 0.0
    available = team_reb + opp_reb
    if available <= 0:
        return 0.0
    team_min_per_five = team_minutes / 5.0
    return safe_percentage(reb * team_min_per_five, minutes * available)


# =============================================================================
# Composite Metrics
# =============================================================================
def player_efficiency_rating(points, reb, ast, stl, blk, fgm, fga, ftm, fta, tov):
    """Simple efficiency: PTS + REB + AST + STL + BLK - (FGA-FGM) - (FTA-FTM) - TOV"""
    return points + reb + ast + stl + blk - (fga - fgm) - (fta - ftm) - tov


def game_score(points, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov):
    """Hollinger's Game Score:
    PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM) + 0.7*OREB + 0.3*DREB
    + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV
    """
    return (
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


def pie(p, t):
    """Player Impact Estimate (PIE).

    p: dict with pts, fgm, fga, ftm, fta, dreb, oreb, ast, stl, blk, pf, tov
    t: team-level dict with same keys

    PIE = (PTS + FGM + FTM - FGA - FTA + DREB + 0.5*OREB + AST + STL + 0.5*BLK - PF - TOV)
        / (TeamPTS + TeamFGM + TeamFTM - TeamFGA - TeamFTA + TeamDREB + 0.5*TeamOREB
           + TeamAST + TeamSTL + 0.5*TeamBLK - TeamPF - TeamTOV)
        * 100
    """
    def _value(stats):
        return (
            stats["pts"] + stats["fgm"] + stats["ftm"]
            - stats["fga"] - stats["fta"]
            + stats["dreb"] + 0.5 * stats["oreb"]
            + stats["ast"] + stats["stl"] + 0.5 * stats["blk"]
            - stats["pf"] - stats["tov"]
        )

    player_val = _value(p)
    team_val = _value(t) if t else 0
    return safe_percentage(player_val, team_val, decimals=1)


# =============================================================================
# Ratios
# =============================================================================
def ast_tov_ratio(ast, tov):
    return safe_divide(ast, tov, default=ast)


def points_per_shot(points, fga):
    return rust_analytics.calculate_points_per_shot(int(points), int(fga))


def points_per_possession(points, possessions):
    return safe_divide(points, possessions)


def fta_rate(fta, fga):
    return safe_percentage(fta, fga) if fga > 0 else 0.0


def assist_ratio(ast, fga, tov, fta):
    return rust_analytics.calculate_assist_ratio(int(ast), int(fga), int(tov), int(fta))


def turnover_ratio(tov, fga, fta, ora=0):
    return rust_analytics.calculate_turnover_ratio(int(tov), int(fga), int(fta), int(ora))


# =============================================================================
# Normalization
# =============================================================================
def per_100_possessions(value, possessions):
    return safe_divide(value * 100, possessions)


def per_100_minutes(value, minutes):
    return safe_divide(value * 100, minutes)


def pace(possessions, minutes, standard_game_minutes=40.0):
    if minutes <= 0:
        return 0.0
    return (possessions / minutes) * standard_game_minutes


# =============================================================================
# Clutch
# =============================================================================
def is_clutch(margin, time_remaining_seconds):
    return rust_analytics.is_clutch_situation(margin, time_remaining_seconds)
