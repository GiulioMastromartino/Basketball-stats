"""Advanced game report metrics computation.

Provides dataclasses and formulas for computing advanced basketball metrics
for teams and players, following Dean Oliver's Basketball on Paper methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from types import SimpleNamespace

from core.advanced_analytics import classify_shot_zone, DEFAULT_ZONE_VALUES
from core.evolution_report import EvolutionReport
from core.services.evolution_report_service import EvolutionReportService


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


@dataclass
class ZoneStats:
    """Zone-based shooting statistics for a single zone.

    Attributes:
        zone: Zone name (Rim, Paint, Midrange, Corner_3, Above_Break_3)
        fgm: Field goals made in this zone
        fga: Field goals attempted in this zone
        fg_pct: Field goal percentage (0-100 scale)
        points: Total points scored from this zone
        pps: Points per shot
        expected_value: Expected points per shot for this zone
        efficiency_delta: Actual PPS minus expected value
    """

    zone: str
    fgm: int = 0
    fga: int = 0
    fg_pct: float = 0.0
    points: int = 0
    pps: float = 0.0
    expected_value: float = 0.0
    efficiency_delta: float = 0.0

    def __post_init__(self):
        if self.fga > 0:
            object.__setattr__(self, "fg_pct", _round(_pct(self.fgm, self.fga), 1))
            object.__setattr__(self, "pps", _round(_safe_div(self.points, self.fga), 2))
        if self.expected_value == 0.0:
            object.__setattr__(
                self, "expected_value", DEFAULT_ZONE_VALUES.get(self.zone, 0.80)
            )
        object.__setattr__(
            self, "efficiency_delta", _round(self.pps - self.expected_value, 2)
        )


@dataclass
class QuarterStats:
    """Per-quarter statistics breakdown.

    Attributes:
        quarter: Quarter number (1-4, or 5+ for OT)
        team_pts: Points scored by team in this quarter
        opp_pts: Points scored by opponent in this quarter
        fgm: Field goals made
        fga: Field goals attempted
        tpm: Three-pointers made
        tpa: Three-pointers attempted
        ftm: Free throws made
        fta: Free throws attempted
        orb: Offensive rebounds
        drb: Defensive rebounds
        ast: Assists
        stl: Steals
        blk: Blocks
        tov: Turnovers
    """

    quarter: int
    team_pts: int = 0
    opp_pts: int = 0
    fgm: int = 0
    fga: int = 0
    tpm: int = 0
    tpa: int = 0
    ftm: int = 0
    fta: int = 0
    orb: int = 0
    drb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0

    @property
    def margin(self) -> int:
        """Point margin for this quarter (positive = team winning)."""
        return self.team_pts - self.opp_pts

    @property
    def fg_pct(self) -> float:
        """Field goal percentage for this quarter."""
        return _round(_pct(self.fgm, self.fga), 1) if self.fga > 0 else 0.0

    @property
    def tp_pct(self) -> float:
        """Three-point percentage for this quarter."""
        return _round(_pct(self.tpm, self.tpa), 1) if self.tpa > 0 else 0.0


@dataclass
class ClutchStats:
    """Clutch time performance statistics (last 5 minutes, margin ≤ 5 points).

    Attributes:
        points: Total points scored in clutch time
        fgm: Field goals made in clutch time
        fga: Field goals attempted in clutch time
        tpm: Three-pointers made in clutch time
        tpa: Three-pointers attempted in clutch time
        ftm: Free throws made in clutch time
        fta: Free throws attempted in clutch time
        tov: Turnovers in clutch time
        orb: Offensive rebounds in clutch time
        drb: Defensive rebounds in clutch time
        ast: Assists in clutch time
        stl: Steals in clutch time
        blk: Blocks in clutch time
        plus_minus: Plus/minus in clutch time
        time_seconds: Total clutch time duration in seconds
        num_possessions: Number of possessions in clutch time
    """

    points: int = 0
    fgm: int = 0
    fga: int = 0
    tpm: int = 0
    tpa: int = 0
    ftm: int = 0
    fta: int = 0
    tov: int = 0
    orb: int = 0
    drb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    plus_minus: int = 0
    time_seconds: int = 0
    num_possessions: int = 0

    @property
    def fg_pct(self) -> float:
        """Field goal percentage in clutch time."""
        return _round(_pct(self.fgm, self.fga), 1) if self.fga > 0 else 0.0

    @property
    def tp_pct(self) -> float:
        """Three-point percentage in clutch time."""
        return _round(_pct(self.tpm, self.tpa), 1) if self.tpa > 0 else 0.0

    @property
    def ft_pct(self) -> float:
        """Free throw percentage in clutch time."""
        return _round(_pct(self.ftm, self.fta), 1) if self.fta > 0 else 0.0

    @property
    def tov_pct(self) -> float:
        """Turnover percentage in clutch time."""
        total_plays = self.fga + 0.44 * self.fta + self.tov
        return _round(_pct(self.tov, total_plays), 1) if total_plays > 0 else 0.0

    @property
    def offensive_rating(self) -> float:
        """Points per 100 possessions in clutch time."""
        if self.num_possessions == 0:
            return 0.0
        return _round(100.0 * _safe_div(self.points, self.num_possessions), 1)


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
    p: PlayerBox, team: TeamBox, team_minutes_total: float
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
    tov_denom = p.fga + 0.44 * p.fta + p.tov
    tov_pct = _pct(p.tov, tov_denom)

    # Usage percentage (Dean Oliver formula)
    # What % of team plays the player used while on court
    team_denom = team.fga + 0.44 * team.fta + team.tov
    player_plays = p.fga + 0.44 * p.fta + p.tov
    usg = 100.0 * _safe_div(
        player_plays * (team_minutes_total / 5.0), p.minutes * team_denom
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


def calculate_zone_stats(shots: Optional[List[Dict[str, Any]]]) -> Dict[str, ZoneStats]:
    """Calculate shooting statistics by zone.

    Uses the classify_shot_zone function from advanced_analytics to determine
    shot zones based on court coordinates.

    Args:
        shots: List of shot dictionaries, each with:
            - x_loc: X coordinate (0-500)
            - y_loc: Y coordinate (0-470)
            - shot_type: '2pt', '3pt', or 'ft'
            - made: Boolean indicating if shot was made (or 'result' == 'made')
            - points: Points scored (optional, derived from shot_type and made)

    Returns:
        Dictionary mapping zone names to ZoneStats objects:
        {
            'Rim': ZoneStats(...),
            'Paint': ZoneStats(...),
            'Midrange': ZoneStats(...),
            'Corner_3': ZoneStats(...),
            'Above_Break_3': ZoneStats(...)
        }
    """
    if not shots:
        return {}

    zone_data: Dict[str, Dict[str, int]] = {
        "Rim": {"fgm": 0, "fga": 0, "points": 0},
        "Paint": {"fgm": 0, "fga": 0, "points": 0},
        "Midrange": {"fgm": 0, "fga": 0, "points": 0},
        "Corner_3": {"fgm": 0, "fga": 0, "points": 0},
        "Above_Break_3": {"fgm": 0, "fga": 0, "points": 0},
    }

    for shot in shots:
        x_loc = shot.get("x_loc")
        y_loc = shot.get("y_loc")
        shot_type = shot.get("shot_type", "2pt")

        # Determine if made
        made = shot.get("made")
        if made is None:
            made = shot.get("result") == "made"
        elif isinstance(made, str):
            made = made.lower() == "made"

        # Get points (default based on shot type and made status)
        points = shot.get("points")
        if points is None:
            if made:
                points = 3 if "3pt" in shot_type.lower() else 2
            else:
                points = 0

        # Classify zone
        zone = classify_shot_zone(x_loc, y_loc, shot_type)

        # Skip FT zone for field goal stats
        if zone == "FT":
            continue

        # Only count zones we track
        if zone not in zone_data:
            continue

        zone_data[zone]["fga"] += 1
        if made:
            zone_data[zone]["fgm"] += 1
            zone_data[zone]["points"] += points

    # Build ZoneStats objects
    result = {}
    for zone, data in zone_data.items():
        if data["fga"] > 0:
            result[zone] = ZoneStats(
                zone=zone,
                fgm=data["fgm"],
                fga=data["fga"],
                points=data["points"],
                expected_value=DEFAULT_ZONE_VALUES.get(zone, 0.80),
            )

    return result


def calculate_quarter_stats(
    events: Optional[List[Dict[str, Any]]],
) -> Dict[int, QuarterStats]:
    """Calculate per-quarter scoring breakdown from game events.

    Args:
        events: List of event dictionaries, each with:
            - quarter: Quarter number (1-4, or 5+ for OT)
            - event_type: Type of event (SHOT_2PT, SHOT_3PT, FT_MADE, etc.)
            - shot_attempt: 'made' or 'missed' for shot events
            - points: Points scored (optional)
            - team: 'home' or 'away' to identify which team scored
            - stat_type: For rebounds/steals/blocks/turnovers

    Returns:
        Dictionary mapping quarter numbers to QuarterStats objects:
        {
            1: QuarterStats(quarter=1, team_pts=25, opp_pts=22, ...),
            2: QuarterStats(quarter=2, team_pts=18, opp_pts=20, ...),
            ...
        }
    """
    if not events:
        return {}

    quarter_data: Dict[int, Dict[str, Any]] = {}

    for event in events:
        quarter = event.get("quarter", 1)
        if quarter is None:
            quarter = 1

        if quarter not in quarter_data:
            quarter_data[quarter] = {
                "team_pts": 0,
                "opp_pts": 0,
                "fgm": 0,
                "fga": 0,
                "tpm": 0,
                "tpa": 0,
                "ftm": 0,
                "fta": 0,
                "orb": 0,
                "drb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "tov": 0,
            }

        data = quarter_data[quarter]
        event_type = event.get("event_type", "")
        team = event.get("team", "home")

        # Determine if this is team or opponent event
        is_team = team == "home" or team is None

        # Handle shot events
        if event_type in ("SHOT_2PT", "SHOT_3PT"):
            data["fga"] += 1 if is_team else 0
            if event_type == "SHOT_3PT":
                data["tpa"] += 1 if is_team else 0

            made = event.get("shot_attempt") == "made" or event.get("result") == "made"
            if made:
                points = event.get("points", 3 if event_type == "SHOT_3PT" else 2)
                data["fgm"] += 1 if is_team else 0
                if event_type == "SHOT_3PT":
                    data["tpm"] += 1 if is_team else 0

                if is_team:
                    data["team_pts"] += points
                else:
                    data["opp_pts"] += points

        # Handle free throws
        elif event_type in ("FT_MADE", "FT_MISS", "FT"):
            fta = event.get("fta", 1)
            is_made = event_type == "FT_MADE" or event.get("result") == "made"

            data["fta"] += fta if is_team else 0
            if is_made:
                ftm = event.get("ftm", fta) if event_type == "FT" else 1
                data["ftm"] += ftm if is_team else 0

                points = ftm if event_type == "FT" else 1
                if is_team:
                    data["team_pts"] += points
                else:
                    data["opp_pts"] += points

        # Handle other events
        elif event_type == "AST" or event.get("ast"):
            data["ast"] += 1 if is_team else 0
        elif event_type == "STL" or event.get("stl"):
            data["stl"] += 1 if is_team else 0
        elif event_type == "BLK" or event.get("blk"):
            data["blk"] += 1 if is_team else 0
        elif event_type == "TOV" or event.get("tov"):
            data["tov"] += 1 if is_team else 0
        elif event_type in ("OREB", "OR"):
            data["orb"] += 1 if is_team else 0
        elif event_type in ("DREB", "DR"):
            data["drb"] += 1 if is_team else 0

        # Handle score updates
        elif event_type == "SCORE_UPDATE":
            if is_team:
                data["team_pts"] = event.get("team_score", data["team_pts"])
            else:
                data["opp_pts"] = event.get("opp_score", data["opp_pts"])

    # Build QuarterStats objects
    result = {}
    for quarter, data in sorted(quarter_data.items()):
        result[quarter] = QuarterStats(
            quarter=quarter,
            team_pts=data["team_pts"],
            opp_pts=data["opp_pts"],
            fgm=data["fgm"],
            fga=data["fga"],
            tpm=data["tpm"],
            tpa=data["tpa"],
            ftm=data["ftm"],
            fta=data["fta"],
            orb=data["orb"],
            drb=data["drb"],
            ast=data["ast"],
            stl=data["stl"],
            blk=data["blk"],
            tov=data["tov"],
        )

    return result


def calculate_clutch_stats(
    events: Optional[List[Dict[str, Any]]],
    final_margin: int = 0,
    time_threshold_seconds: int = 300,
    margin_threshold: int = 5,
) -> ClutchStats:
    """Calculate clutch time performance statistics.

    Clutch time is defined as the last 5 minutes (default) when the score
    margin is within 5 points (default).

    Args:
        events: List of event dictionaries with:
            - quarter: Quarter number
            - time_remaining: Time remaining in quarter (MM:SS or seconds)
            - score_margin: Current score margin (team - opponent)
            - event_type: Type of event
            - shot_attempt: 'made' or 'missed' for shots
            - points: Points scored
        final_margin: Final score margin (used if not in events)
        time_threshold_seconds: Seconds remaining to qualify as clutch (default 300 = 5 min)
        margin_threshold: Score margin to qualify as clutch (default 5 points)

    Returns:
        ClutchStats object with aggregated clutch time statistics
    """
    if not events:
        return ClutchStats()

    def parse_time_to_seconds(time_str) -> int:
        """Convert MM:SS or numeric to total seconds."""
        if time_str is None:
            return 300
        if isinstance(time_str, (int, float)):
            return int(time_str)
        try:
            if ":" in str(time_str):
                parts = str(time_str).split(":")
                return int(parts[0]) * 60 + int(parts[1])
            return int(time_str)
        except (ValueError, AttributeError):
            return 300

    clutch_data = {
        "points": 0,
        "fgm": 0,
        "fga": 0,
        "tpm": 0,
        "tpa": 0,
        "ftm": 0,
        "fta": 0,
        "tov": 0,
        "orb": 0,
        "drb": 0,
        "ast": 0,
        "stl": 0,
        "blk": 0,
        "plus_minus": 0,
        "time_seconds": 0,
        "num_possessions": 0,
    }

    in_clutch = False
    clutch_start_time = 0

    for event in events:
        quarter = event.get("quarter", 4)
        time_remaining = event.get("time_remaining")
        score_margin = event.get("score_margin")

        # Parse time
        time_sec = parse_time_to_seconds(time_remaining)

        # Determine if we're in clutch time (4th quarter or OT, last 5 min, within 5 pts)
        is_fourth_quarter_or_later = quarter >= 4
        is_last_five_minutes = time_sec <= time_threshold_seconds

        # Use event margin or fall back to final_margin
        margin = score_margin if score_margin is not None else final_margin
        is_close_game = abs(margin) <= margin_threshold

        is_clutch_situation = (
            is_fourth_quarter_or_later and is_last_five_minutes and is_close_game
        )

        if is_clutch_situation and not in_clutch:
            in_clutch = True
            clutch_start_time = time_sec

        if not is_clutch_situation:
            continue

        # Track clutch time
        if time_sec < clutch_start_time:
            clutch_data["time_seconds"] = clutch_start_time - time_sec

        event_type = event.get("event_type", "")

        # Handle shot events
        if event_type in ("SHOT_2PT", "SHOT_3PT"):
            clutch_data["fga"] += 1
            if event_type == "SHOT_3PT":
                clutch_data["tpa"] += 1

            made = event.get("shot_attempt") == "made" or event.get("result") == "made"
            if made:
                points = event.get("points", 3 if event_type == "SHOT_3PT" else 2)
                clutch_data["fgm"] += 1
                clutch_data["points"] += points
                if event_type == "SHOT_3PT":
                    clutch_data["tpm"] += 1

        # Handle free throws
        elif event_type in ("FT_MADE", "FT_MISS", "FT"):
            fta = event.get("fta", 1)
            is_made = event_type == "FT_MADE" or event.get("result") == "made"

            clutch_data["fta"] += fta
            if is_made:
                ftm = event.get("ftm", fta) if event_type == "FT" else 1
                clutch_data["ftm"] += ftm
                clutch_data["points"] += ftm

        # Handle other events
        elif event_type == "TOV" or event.get("tov"):
            clutch_data["tov"] += 1
            clutch_data["num_possessions"] += 1
        elif event_type == "AST" or event.get("ast"):
            clutch_data["ast"] += 1
        elif event_type == "STL" or event.get("stl"):
            clutch_data["stl"] += 1
        elif event_type == "BLK" or event.get("blk"):
            clutch_data["blk"] += 1
        elif event_type in ("OREB", "OR"):
            clutch_data["orb"] += 1
        elif event_type in ("DREB", "DR"):
            clutch_data["drb"] += 1

        # Count possessions for shots
        if event_type in ("SHOT_2PT", "SHOT_3PT"):
            clutch_data["num_possessions"] += 1

    # Estimate plus_minus from margin changes
    if in_clutch:
        clutch_data["plus_minus"] = (
            final_margin if abs(final_margin) <= margin_threshold else 0
        )

    # Ensure we have at least some clutch time
    if clutch_data["time_seconds"] == 0 and in_clutch:
        clutch_data["time_seconds"] = time_threshold_seconds

    return ClutchStats(
        points=clutch_data["points"],
        fgm=clutch_data["fgm"],
        fga=clutch_data["fga"],
        tpm=clutch_data["tpm"],
        tpa=clutch_data["tpa"],
        ftm=clutch_data["ftm"],
        fta=clutch_data["fta"],
        tov=clutch_data["tov"],
        orb=clutch_data["orb"],
        drb=clutch_data["drb"],
        ast=clutch_data["ast"],
        stl=clutch_data["stl"],
        blk=clutch_data["blk"],
        plus_minus=clutch_data["plus_minus"],
        time_seconds=clutch_data["time_seconds"],
        num_possessions=clutch_data["num_possessions"],
    )


def build_advanced_game_report(
    *,
    game: Dict[str, Any],
    team_box: TeamBox,
    opp_box: TeamBox,
    players: List[PlayerBox],
    team_minutes_total: float,
    team_shots: Optional[List[Dict[str, Any]]] = None,
    opp_shots: Optional[List[Dict[str, Any]]] = None,
    zone_stats: Optional[Dict[str, ZoneStats]] = None,
    quarters: Optional[List[Dict[str, Any]]] = None,
    clutch: Optional[ClutchStats] = None,
    top_performers: Optional[List[Dict[str, Any]]] = None,
    score_worm: Optional[List[Dict[str, Any]]] = None,
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
        zone_stats: Optional dict mapping zone names to ZoneStats (calculated from team_shots if not provided)
        quarters: Optional list of per-quarter scoring breakdown (Q1, Q2, Q3, Q4, OT)
        clutch: Optional ClutchStats for clutch time performance
        top_performers: Optional list of top 3 players by points [{name, pts, reb, ast}, ...]
        score_worm: Optional list of score progressions [{time, team_score, opp_score}, ...]

    Returns:
        Complete report dict suitable for template rendering:
        {
            "title": str,
            "generated_at": str,
            "team": dict (team advanced metrics),
            "opp": dict (opponent advanced metrics),
            "players": list (player advanced metrics sorted by minutes/points),
            "zone_stats": dict (zone shooting stats),
            "quarters": list (per-quarter stats),
            "clutch": ClutchStats (clutch time performance),
            "top_performers": list (top 3 players),
            "score_worm": list (score progression)
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
    player_rows = [player_advanced(p, team_box, team_minutes_total) for p in players]
    player_rows.sort(key=lambda r: (r["min"], r["pts"]), reverse=True)

    # Calculate zone stats from team_shots if not provided
    calculated_zone_stats = zone_stats
    if calculated_zone_stats is None and team_shots:
        calculated_zone_stats = calculate_zone_stats(team_shots)

    # Calculate top performers from players if not provided
    calculated_top_performers = top_performers
    if calculated_top_performers is None:
        sorted_players = sorted(players, key=lambda p: p.pts, reverse=True)[:3]
        calculated_top_performers = [
            {
                "name": p.name,
                "pts": p.pts,
                "reb": p.trb,
                "ast": p.ast,
                "min": _round(p.minutes, 1),
            }
            for p in sorted_players
        ]

    # Build quarters list
    quarters_list = quarters if quarters is not None else []

    # Build score worm
    score_worm_list = score_worm if score_worm is not None else []

    report = {
        "title": "Advanced Game Report",
        "generated_at": game.get("generated_at") or datetime.now().isoformat(),
        "team": team_adv,
        "opp": opp_adv,
        "players": player_rows,
        "zone_stats": calculated_zone_stats or {},
        "quarters": quarters_list,
        "clutch": clutch,
        "top_performers": calculated_top_performers or [],
        "score_worm": score_worm_list,
    }

    return report


def build_full_game_report(
    *,
    game: Dict[str, Any],
    team_box: TeamBox,
    opp_box: TeamBox,
    players: List[PlayerBox],
    team_minutes_total: float,
    team_shots: Optional[List[Dict[str, Any]]] = None,
    opp_shots: Optional[List[Dict[str, Any]]] = None,
    game_events: Optional[List[Dict[str, Any]]] = None,
    final_margin: int = 0,
) -> Dict[str, Any]:
    """Build a fully-featured advanced game report with all computed statistics.

    This is a convenience function that automatically calculates zone_stats,
    quarter_stats, clutch_stats, top_performers, and score_worm from raw data.

    Args:
        game: Game metadata dict (date, teams, score, etc.)
        team_box: Team box score
        opp_box: Opponent box score
        players: List of player box scores
        team_minutes_total: Total team minutes (5 * game_minutes)
        team_shots: List of shot data for zone calculation
        opp_shots: List of opponent shot data
        game_events: List of game events for quarter/clutch/score_worm calculation
        final_margin: Final score margin (team - opponent)

    Returns:
        Complete report dict with all features computed
    """
    # Calculate zone stats
    zone_stats = calculate_zone_stats(team_shots) if team_shots else None

    # Calculate quarter stats
    quarter_stats_dict = calculate_quarter_stats(game_events) if game_events else {}
    quarters_list = [
        {
            "quarter": qs.quarter,
            "team_pts": qs.team_pts,
            "opp_pts": qs.opp_pts,
            "margin": qs.margin,
            "fg_pct": qs.fg_pct,
            "tp_pct": qs.tp_pct,
        }
        for qs in quarter_stats_dict.values()
    ]

    # Calculate clutch stats
    clutch = (
        calculate_clutch_stats(game_events, final_margin=final_margin)
        if game_events
        else None
    )

    # Calculate top performers
    sorted_players = sorted(players, key=lambda p: p.pts, reverse=True)[:3]
    top_performers = [
        {
            "name": p.name,
            "pts": p.pts,
            "reb": p.trb,
            "ast": p.ast,
            "min": _round(p.minutes, 1),
        }
        for p in sorted_players
    ]

    # Build score worm from events
    score_worm = []
    if game_events:
        for event in game_events:
            if event.get("event_type") in (
                "SCORE_UPDATE",
                "SHOT_2PT",
                "SHOT_3PT",
                "FT_MADE",
            ):
                team_score = event.get("team_score")
                opp_score = event.get("opp_score")
                if team_score is not None and opp_score is not None:
                    score_worm.append(
                        {
                            "time": event.get("time_remaining", "0:00"),
                            "quarter": event.get("quarter", 1),
                            "team_score": team_score,
                            "opp_score": opp_score,
                            "margin": team_score - opp_score,
                        }
                    )

    return build_advanced_game_report(
        game=game,
        team_box=team_box,
        opp_box=opp_box,
        players=players,
        team_minutes_total=team_minutes_total,
        team_shots=team_shots,
        opp_shots=opp_shots,
        zone_stats=zone_stats,
        quarters=quarters_list,
        clutch=clutch,
        top_performers=top_performers,
        score_worm=score_worm,
    )


def _coerce_event(event: Any) -> SimpleNamespace:
    """Normalize dict/dataclass events into an object with GameEvent-like fields."""
    if isinstance(event, dict):
        return SimpleNamespace(
            event_type=event.get("event_type") or event.get("type"),
            player_name=event.get("player_name") or event.get("player"),
            quarter=event.get("quarter"),
            game_seconds=event.get("game_seconds"),
            time_remaining=event.get("time_remaining"),
            shot_attempt=event.get("shot_attempt"),
            detail=event.get("detail"),
            score_margin=event.get("score_margin"),
            timestamp=event.get("timestamp"),
        )

    return SimpleNamespace(
        event_type=getattr(event, "event_type", None) or getattr(event, "type", None),
        player_name=getattr(event, "player_name", None) or getattr(event, "player", None),
        quarter=getattr(event, "quarter", None),
        game_seconds=getattr(event, "game_seconds", None),
        time_remaining=getattr(event, "time_remaining", None),
        shot_attempt=getattr(event, "shot_attempt", None),
        detail=getattr(event, "detail", None),
        score_margin=getattr(event, "score_margin", None),
        timestamp=getattr(event, "timestamp", None),
    )


def calculate_time_series(
    events: List[Any], snapshot_interval: int = 60
) -> Tuple[List[Any], Dict[str, List[Any]]]:
    """
    Convert a list of event dicts/objects into team/player time-series snapshots.
    """
    if not events:
        return [], {}

    coerced = [_coerce_event(e) for e in events]
    coerced.sort(key=lambda e: e.game_seconds or 0)
    return EvolutionReportService._process_events(coerced, snapshot_interval)


def build_evolution_report(
    game_id: int,
    events: List[Any],
    opponent: str,
    date: str,
    snapshot_interval: int = 60,
) -> EvolutionReport:
    """
    Build a lightweight evolution report from event data (no DB required).
    """
    team_snapshots, player_snapshots = calculate_time_series(
        events, snapshot_interval=snapshot_interval
    )

    final_team_score = team_snapshots[-1].team_score if team_snapshots else 0
    final_opp_score = team_snapshots[-1].opp_score if team_snapshots else 0
    result = "W" if final_team_score > final_opp_score else "L"

    quarter_summaries = EvolutionReportService._calculate_quarter_summaries(
        team_snapshots
    )
    scoring_runs = EvolutionReportService._detect_scoring_runs(team_snapshots)
    max_lead, max_deficit, lead_changes = EvolutionReportService._calculate_key_moments(
        team_snapshots
    )
    clutch_time = EvolutionReportService._calculate_clutch_time(team_snapshots)

    return EvolutionReport(
        game_id=game_id,
        opponent=opponent,
        date=date,
        final_team_score=final_team_score,
        final_opp_score=final_opp_score,
        result=result,
        team_snapshots=team_snapshots,
        player_snapshots=player_snapshots,
        quarter_summaries=quarter_summaries,
        max_lead=max_lead,
        max_deficit=max_deficit,
        lead_changes=lead_changes,
        scoring_runs=scoring_runs,
        clutch_time=clutch_time,
    )
