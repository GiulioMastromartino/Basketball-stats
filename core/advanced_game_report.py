"""Advanced game report metrics computation.

Provides dataclasses and formulas for computing advanced basketball metrics
for teams and players, following Dean Oliver's Basketball on Paper methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _safe_div(n: float, d: float) -> float:
    """Safe division returning 0.0 if denominator is zero."""
    return float(n) / float(d) if d else 0.0


def _pct(n: float, d: float) -> float:
    """Compute percentage (0-100 scale)."""
    return 100.0 * _safe_div(n, d)


def _round(x: float, nd: int = 1) -> float:
    """Round to specified decimal places."""
    return round(float(x), nd)


@dataclass(frozen=True)
class TeamBox:
    """Team box score statistics."""
    pts: int
    fgm: int
    fga: int
    tpm: int
    tpa: int
    ftm: int
    fta: int
    orb: int
    drb: int
    trb: int
    ast: int
    stl: int
    blk: int
    tov: int


@dataclass(frozen=True)
class PlayerBox:
    """Player box score statistics."""
    name: str
    minutes: float
    pts: int
    fgm: int
    fga: int
    tpm: int
    tpa: int
    ftm: int
    fta: int
    orb: int
    drb: int
    trb: int
    ast: int
    stl: int
    blk: int
    tov: int


def possessions(box: TeamBox) -> float:
    """Estimate team possessions using Dean Oliver formula.
    
    Formula: FGA + 0.44*FTA - ORB + TOV
    """
    return box.fga + 0.44 * box.fta - box.orb + box.tov


def team_advanced(team: TeamBox, opp: TeamBox) -> Dict[str, Any]:
    """Compute advanced metrics for a team.
    
    Args:
        team: Team box score
        opp: Opponent box score
        
    Returns:
        Dictionary of advanced metrics including:
        - Efficiency: OER, DER, NET
        - Four Factors: eFG%, TOV%, ORB%, FTr
        - Advanced: TS%, 3PAr, AST%, STL%, BLK%, DRB%, TRB%
        - Points breakdown: PPFT, PP2PS, PP3PS
    """
    team_poss = possessions(team)
    opp_poss = possessions(opp)

    # Efficiency ratings (per 100 possessions)
    oer = 100.0 * _safe_div(team.pts, team_poss)
    der = 100.0 * _safe_div(opp.pts, opp_poss)
    net = oer - der

    # Four Factors
    efg = _safe_div(team.fgm + 0.5 * team.tpm, team.fga)
    tov_pct = _pct(team.tov, team_poss)
    orb_pct = _pct(team.orb, (team.orb + opp.drb))
    ftr = _safe_div(team.fta, team.fga)

    # Advanced metrics
    tpar = _pct(team.tpa, team.fga)  # 3-point attempt rate
    ts = _safe_div(team.pts, 2.0 * (team.fga + 0.44 * team.fta))  # true shooting
    ast_pct = _pct(team.ast, team.fgm)
    stl_pct = _pct(team.stl, opp_poss)
    
    # Block percentage (blocks per opponent 2PA)
    opp_2pa = max(0, opp.fga - opp.tpa)
    blk_pct = _pct(team.blk, opp_2pa)
    
    drb_pct = _pct(team.drb, (team.drb + opp.orb))
    trb_pct = _pct(team.trb, (team.trb + opp.trb))

    # Points per attempt breakdown
    team_2pa = max(0, team.fga - team.tpa)
    team_3pa = team.tpa
    ppft = _safe_div(team.ftm, team.fta)
    pp2ps = _safe_div(max(0, team.pts - team.ftm - 3 * team.tpm), team_2pa)
    pp3ps = _safe_div(3 * team.tpm, team_3pa)

    return {
        "possessions": _round(team_poss, 1),
        "oer": _round(oer, 1),
        "der": _round(der, 1),
        "net": _round(net, 1),
        # Four factors
        "efg_pct": _round(100.0 * efg, 1),
        "tov_pct": _round(tov_pct, 1),
        "orb_pct": _round(orb_pct, 1),
        "ftr": _round(100.0 * ftr, 1),
        # Advanced
        "tpar": _round(tpar, 1),
        "ts_pct": _round(100.0 * ts, 1),
        "ast_pct": _round(ast_pct, 1),
        "stl_pct": _round(stl_pct, 1),
        "blk_pct": _round(blk_pct, 1),
        "drb_pct": _round(drb_pct, 1),
        "trb_pct": _round(trb_pct, 1),
        # Points breakdown
        "ppft": _round(ppft, 2),
        "pp2ps": _round(pp2ps, 2),
        "pp3ps": _round(pp3ps, 2),
        # Display helpers
        "fg": f"{team.fgm}-{team.fga}",
        "fg_pct": _round(_pct(team.fgm, team.fga), 1),
        "tp": f"{team.tpm}-{team.tpa}",
        "tp_pct": _round(_pct(team.tpm, team.tpa), 1),
    }


def player_advanced(
    p: PlayerBox,
    team: TeamBox,
    team_minutes_total: float
) -> Dict[str, Any]:
    """Compute advanced metrics for a player.
    
    Args:
        p: Player box score
        team: Team box score (for usage rate calculation)
        team_minutes_total: Total team minutes (5 * game_minutes)
                          e.g., 200 for 40-minute games, 240 for 48-minute games
    
    Returns:
        Dictionary with player name and advanced metrics:
        - Basic: MIN, PTS, REB, AST
        - Advanced: TS%, eFG%, USG%, TOV%
    """
    # True shooting and effective field goal percentage
    ts = _safe_div(p.pts, 2.0 * (p.fga + 0.44 * p.fta))
    efg = _safe_div(p.fgm + 0.5 * p.tpm, p.fga)
    
    # Turnover percentage
    tov_denom = (p.fga + 0.44 * p.fta + p.tov)
    tov_pct = _pct(p.tov, tov_denom)

    # Usage percentage (Dean Oliver formula)
    # What % of team plays the player used while on court
    team_denom = (team.fga + 0.44 * team.fta + team.tov)
    player_plays = (p.fga + 0.44 * p.fta + p.tov)
    usg = 100.0 * _safe_div(
        player_plays * (team_minutes_total / 5.0),
        p.minutes * team_denom
    )

    return {
        "name": p.name,
        "min": _round(p.minutes, 1),
        "pts": p.pts,
        "reb": p.trb,
        "ast": p.ast,
        "ts_pct": _round(100.0 * ts, 1),
        "efg_pct": _round(100.0 * efg, 1),
        "usg_pct": _round(usg, 1),
        "tov_pct": _round(tov_pct, 1),
    }


def build_advanced_game_report(
    *,
    game: Dict[str, Any],
    team_box: TeamBox,
    opp_box: TeamBox,
    players: List[PlayerBox],
    team_minutes_total: float,
    team_shots: Optional[List[Dict[str, Any]]] = None,
    opp_shots: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build complete advanced game report.
    
    Args:
        game: Game metadata dict (date, teams, score, etc.)
        team_box: Team box score
        opp_box: Opponent box score
        players: List of player box scores
        team_minutes_total: Total team minutes (5 * game_minutes)
        team_shots: Optional list of shot data [{x, y, made}, ...]
        opp_shots: Optional list of opponent shot data
        
    Returns:
        Complete report dict suitable for template rendering:
        {
            "title": str,
            "generated_at": str,
            "team": dict (team advanced metrics),
            "opp": dict (opponent advanced metrics),
            "players": list (player advanced metrics sorted by minutes/points)
        }
    """
    team_adv = team_advanced(team_box, opp_box)
    opp_adv = team_advanced(opp_box, team_box)

    # Add shot charts if provided
    if team_shots is not None:
        team_adv["shots"] = team_shots
    if opp_shots is not None:
        opp_adv["shots"] = opp_shots

    # Compute player metrics and sort by minutes then points
    player_rows = [
        player_advanced(p, team_box, team_minutes_total)
        for p in players
    ]
    player_rows.sort(key=lambda r: (r["min"], r["pts"]), reverse=True)

    return {
        "title": "Advanced Game Report",
        "generated_at": game.get("generated_at"),
        "team": team_adv,
        "opp": opp_adv,
        "players": player_rows,
    }
