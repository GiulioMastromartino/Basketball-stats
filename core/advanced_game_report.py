"""Advanced game report metrics computation.

Provides dataclasses and formulas for computing advanced basketball metrics
for teams and players, following Dean Oliver's Basketball on Paper methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.advanced_analytics import classify_shot_zone, DEFAULT_ZONE_VALUES


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


# ============================================================
# TIME-EVOLUTION TRACKING
# Track team and player stats as they evolve during the game
# ============================================================


@dataclass
class TeamTimeSnapshot:
    """Team statistics snapshot at a specific game moment.

    Tracks cumulative stats from game start to this moment.
    """

    game_seconds: int  # Absolute game time (0-2400 for regulation)
    quarter: int  # Current quarter (1-4, 5+ for OT)
    time_remaining: str  # MM:SS remaining in quarter
    team_score: int  # Cumulative team points
    opp_score: int  # Cumulative opponent points
    margin: int  # Point differential

    # Cumulative counting stats
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

    # Running advanced metrics
    possessions: int = 0
    oer: float = 0.0  # Offensive efficiency (pts/100 poss)
    der: float = 0.0  # Defensive efficiency (if opp stats available)
    efg_pct: float = 0.0  # Effective FG%
    ts_pct: float = 0.0  # True shooting %
    tov_pct: float = 0.0  # Turnover %
    orb_pct: float = 0.0  # Offensive rebound %
    ft_rate: float = 0.0  # FT rate (FTA/FGA)

    # Lineup context
    lineup: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate derived metrics after initialization."""
        # Possessions estimate (simplified)
        if self.fga > 0 or self.fta > 0 or self.tov > 0:
            poss = self.fga + 0.44 * self.fta + self.tov - self.orb
            object.__setattr__(self, "possessions", max(1, int(poss)))

        # Offensive efficiency
        if self.possessions > 0:
            object.__setattr__(
                self, "oer", _round(100 * self.team_score / self.possessions, 1)
            )

        # Effective FG%
        if self.fga > 0:
            efg = 100 * (self.fgm + 0.5 * self.tpm) / self.fga
            object.__setattr__(self, "efg_pct", _round(efg, 1))

        # True shooting %
        if self.fga > 0 or self.fta > 0:
            ts_denom = 2 * (self.fga + 0.44 * self.fta)
            if ts_denom > 0:
                object.__setattr__(
                    self, "ts_pct", _round(100 * self.team_score / ts_denom, 1)
                )

        # Turnover rate
        denom = self.fga + 0.44 * self.fta + self.tov
        if denom > 0:
            object.__setattr__(self, "tov_pct", _round(100 * self.tov / denom, 1))

        # FT rate
        if self.fga > 0:
            object.__setattr__(self, "ft_rate", _round(self.fta / self.fga, 2))


@dataclass
class PlayerTimeSnapshot:
    """Player statistics snapshot at a specific game moment.

    Tracks cumulative stats for a single player from game start to this moment.
    """

    player_name: str
    game_seconds: int
    quarter: int
    time_remaining: str

    # Cumulative counting stats
    pts: int = 0
    fgm: int = 0
    fga: int = 0
    tpm: int = 0
    tpa: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0
    plus_minus: int = 0

    # Running advanced metrics
    ts_pct: float = 0.0
    efg_pct: float = 0.0
    usg_pct: float = 0.0  # Usage % (requires team context)

    def __post_init__(self):
        """Calculate derived metrics."""
        if self.fga > 0:
            efg = 100 * (self.fgm + 0.5 * self.tpm) / self.fga
            object.__setattr__(self, "efg_pct", _round(efg, 1))

        if self.fga > 0 or self.fta > 0:
            ts_denom = 2 * (self.fga + 0.44 * self.fta)
            if ts_denom > 0:
                object.__setattr__(self, "ts_pct", _round(100 * self.pts / ts_denom, 1))


@dataclass
class GameEvolutionReport:
    """Complete time-evolution report for a game.

    Contains snapshots of team and player stats at key moments throughout the game.
    """

    game_id: int
    opponent: str
    date: str
    final_team_score: int
    final_opp_score: int
    result: str  # 'W' or 'L'

    # Time-series data
    team_snapshots: List[TeamTimeSnapshot] = field(default_factory=list)
    player_snapshots: Dict[str, List[PlayerTimeSnapshot]] = field(default_factory=dict)

    # Quarter boundaries (indexes into snapshots)
    quarter_boundaries: Dict[int, int] = field(default_factory=dict)

    # Key moments
    max_lead: int = 0
    max_deficit: int = 0
    lead_changes: int = 0
    scoring_runs: List[Dict] = field(default_factory=list)

    # Per-quarter summaries
    quarter_summaries: Dict[int, Dict] = field(default_factory=dict)


def calculate_time_series(
    events: List[Any],
    snapshot_interval: int = 60,  # Create snapshot every N seconds
    include_all_events: bool = False,  # If True, snapshot at every event
) -> Tuple[List[TeamTimeSnapshot], Dict[str, List[PlayerTimeSnapshot]]]:
    """
    Calculate time-series statistics from game events.

    Args:
        events: List of GameEvent objects sorted by game_seconds
        snapshot_interval: Seconds between snapshots (default 60 = every minute)
        include_all_events: If True, create snapshot at every event

    Returns:
        Tuple of (team_snapshots, player_snapshots_dict)
    """
    team_snapshots = []
    player_snapshots: Dict[str, List[PlayerTimeSnapshot]] = {}

    # Running totals
    team_totals = {
        "fgm": 0,
        "fga": 0,
        "tpm": 0,
        "tpa": 0,
        "ftm": 0,
        "fta": 0,
        "orb": 0,
        "dreb": 0,
        "ast": 0,
        "stl": 0,
        "blk": 0,
        "tov": 0,
        "pts": 0,
    }
    player_totals: Dict[str, Dict] = {}
    opp_score = 0
    team_score = 0

    # Track current lineup
    current_lineup: List[str] = []

    # Track last snapshot time
    last_snapshot_time = -snapshot_interval

    # Event type mappings
    scoring_events = {"SHOT_2PT", "SHOT_3PT", "FT"}

    def _create_team_snapshot(game_seconds: int, quarter: int, time_remaining: str):
        """Create a team snapshot with current totals."""
        return TeamTimeSnapshot(
            game_seconds=game_seconds,
            quarter=quarter,
            time_remaining=time_remaining,
            team_score=team_score,
            opp_score=opp_score,
            margin=team_score - opp_score,
            fgm=team_totals["fgm"],
            fga=team_totals["fga"],
            tpm=team_totals["tpm"],
            tpa=team_totals["tpa"],
            ftm=team_totals["ftm"],
            fta=team_totals["fta"],
            orb=team_totals["orb"],
            drb=team_totals["dreb"],
            ast=team_totals["ast"],
            stl=team_totals["stl"],
            blk=team_totals["blk"],
            tov=team_totals["tov"],
            lineup=current_lineup.copy(),
        )

    def _create_player_snapshot(
        player_name: str, game_seconds: int, quarter: int, time_remaining: str
    ):
        """Create a player snapshot with current totals."""
        p = player_totals.get(player_name, {})
        return PlayerTimeSnapshot(
            player_name=player_name,
            game_seconds=game_seconds,
            quarter=quarter,
            time_remaining=time_remaining,
            pts=p.get("pts", 0),
            fgm=p.get("fgm", 0),
            fga=p.get("fga", 0),
            tpm=p.get("tpm", 0),
            tpa=p.get("tpa", 0),
            ftm=p.get("ftm", 0),
            fta=p.get("fta", 0),
            oreb=p.get("oreb", 0),
            dreb=p.get("dreb", 0),
            ast=p.get("ast", 0),
            stl=p.get("stl", 0),
            blk=p.get("blk", 0),
            tov=p.get("tov", 0),
            pf=p.get("pf", 0),
            plus_minus=p.get("plus_minus", 0),
        )

    def _init_player(player_name: str):
        """Initialize player totals dict."""
        if player_name and player_name not in player_totals:
            player_totals[player_name] = {
                "pts": 0,
                "fgm": 0,
                "fga": 0,
                "tpm": 0,
                "tpa": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "tov": 0,
                "pf": 0,
                "plus_minus": 0,
            }

    def _get_event_attr(event, attr, default=None):
        """Safely get attribute from event (handles both objects and dicts)."""
        # Try object attribute first
        val = getattr(event, attr, None)
        if val is not None:
            return val
        # Try dict get if available
        if hasattr(event, "get"):
            return event.get(attr, default)
        return default

    for event in events:
        event_type = _get_event_attr(event, "event_type", _get_event_attr(event, "type", ""))
        player_name = _get_event_attr(event, "player_name", _get_event_attr(event, "player", ""))
        quarter = _get_event_attr(event, "quarter", 1)
        game_seconds = _get_event_attr(event, "game_seconds", 0)
        time_remaining = _get_event_attr(event, "time_remaining", "10:00")
        detail = _get_event_attr(event, "detail", {})
        score_margin = _get_event_attr(event, "score_margin", 0)

        # Parse detail if string
        if isinstance(detail, str):
            try:
                import ast

                detail = ast.literal_eval(detail) if detail else {}
            except:
                detail = {}

        # Handle different event types
        if event_type == "SHOT_2PT":
            team_totals["fga"] += 1
            shot_result = _get_event_attr(event, "shot_attempt", "")
            if shot_result == "made":
                team_totals["fgm"] += 1
                team_totals["pts"] += 2
                team_score += 2
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["fga"] += 1
                if shot_result == "made":
                    player_totals[player_name]["fgm"] += 1
                    player_totals[player_name]["pts"] += 2

        elif event_type == "SHOT_3PT":
            team_totals["fga"] += 1
            team_totals["tpa"] += 1
            shot_result = _get_event_attr(event, "shot_attempt", "")
            if shot_result == "made":
                team_totals["fgm"] += 1
                team_totals["tpm"] += 1
                team_totals["pts"] += 3
                team_score += 3
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["fga"] += 1
                player_totals[player_name]["tpa"] += 1
                if shot_result == "made":
                    player_totals[player_name]["fgm"] += 1
                    player_totals[player_name]["tpm"] += 1
                    player_totals[player_name]["pts"] += 3

        elif event_type == "FT":
            ftm = detail.get("ftm", 0) if isinstance(detail, dict) else 0
            fta = detail.get("fta", 0) if isinstance(detail, dict) else 0
            team_totals["ftm"] += ftm
            team_totals["fta"] += fta
            team_totals["pts"] += ftm
            team_score += ftm
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["ftm"] += ftm
                player_totals[player_name]["fta"] += fta
                player_totals[player_name]["pts"] += ftm

        elif event_type == "OREB":
            team_totals["orb"] += 1
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["oreb"] += 1

        elif event_type == "DREB":
            team_totals["dreb"] += 1
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["dreb"] += 1

        elif event_type == "AST":
            team_totals["ast"] += 1
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["ast"] += 1

        elif event_type == "STL":
            team_totals["stl"] += 1
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["stl"] += 1

        elif event_type == "BLK":
            team_totals["blk"] += 1
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["blk"] += 1

        elif event_type == "TURNOVER":
            team_totals["tov"] += 1
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["tov"] += 1

        elif event_type == "FOUL":
            if player_name:
                _init_player(player_name)
                player_totals[player_name]["pf"] += 1

        elif event_type == "OPP_SCORE":
            points = detail.get("points", 0) if isinstance(detail, dict) else 0
            if points > 0:
                opp_score += points

        elif event_type == "SUB_IN":
            if player_name and player_name not in current_lineup:
                current_lineup.append(player_name)

        elif event_type == "SUB_OUT":
            if player_name in current_lineup:
                current_lineup.remove(player_name)

        elif event_type == "NEXT_QUARTER":
            # Create snapshot at quarter boundary
            eff_gs = game_seconds if game_seconds is not None else 0
            snapshot = _create_team_snapshot(eff_gs, quarter, time_remaining)
            team_snapshots.append(snapshot)

        # Create snapshot at interval or every event
        # Handle None game_seconds
        effective_game_seconds = game_seconds if game_seconds is not None else 0
        should_snapshot = (
            include_all_events or effective_game_seconds - last_snapshot_time >= snapshot_interval
        )

        if (
            should_snapshot
            and event_type in scoring_events
            or event_type in ["OPP_SCORE", "TURNOVER", "NEXT_QUARTER"]
        ):
            snapshot = _create_team_snapshot(effective_game_seconds, quarter, time_remaining)
            team_snapshots.append(snapshot)
            last_snapshot_time = effective_game_seconds

            # Also create player snapshots
            for pname in player_totals:
                psnap = _create_player_snapshot(
                    pname, effective_game_seconds, quarter, time_remaining
                )
                if pname not in player_snapshots:
                    player_snapshots[pname] = []
                player_snapshots[pname].append(psnap)

    # Final snapshot
    if team_snapshots:
        last = team_snapshots[-1]
        if last.team_score != team_score or last.opp_score != opp_score:
            final_snap = _create_team_snapshot(
                game_seconds=team_snapshots[-1].game_seconds + 1
                if team_snapshots
                else 2400,
                quarter=4,
                time_remaining="0:00",
            )
            team_snapshots.append(final_snap)

    return team_snapshots, player_snapshots


def build_evolution_report(
    game_id: int,
    events: List[Any],
    opponent: str = "",
    date: str = "",
    snapshot_interval: int = 60,
) -> GameEvolutionReport:
    """
    Build a complete game evolution report with time-series statistics.

    Args:
        game_id: Game identifier
        events: List of GameEvent objects sorted by game_seconds
        opponent: Opponent team name
        date: Game date string
        snapshot_interval: Seconds between snapshots (default 60)

    Returns:
        GameEvolutionReport with all time-series data
    """
    # Sort events by game_seconds (handle None values)
    def get_game_seconds(e):
        gs = getattr(e, "game_seconds", None)
        if gs is None:
            gs = getattr(e, "get", lambda k, d=0: d)("game_seconds", 0)
        return gs if gs is not None else 0
    
    sorted_events = sorted(events, key=get_game_seconds)

    # Calculate time series
    team_snapshots, player_snapshots = calculate_time_series(
        sorted_events, snapshot_interval=snapshot_interval, include_all_events=False
    )

    # Determine final scores
    final_team_score = team_snapshots[-1].team_score if team_snapshots else 0
    final_opp_score = team_snapshots[-1].opp_score if team_snapshots else 0
    result = "W" if final_team_score > final_opp_score else "L"

    # Find quarter boundaries
    quarter_boundaries = {}
    for i, snap in enumerate(team_snapshots):
        if snap.quarter not in quarter_boundaries:
            quarter_boundaries[snap.quarter] = i

    # Calculate max lead/deficit
    max_lead = 0
    max_deficit = 0
    lead_changes = 0
    prev_margin = 0

    for snap in team_snapshots:
        if snap.margin > max_lead:
            max_lead = snap.margin
        if snap.margin < max_deficit:
            max_deficit = snap.margin

        # Lead change detection
        if prev_margin > 0 and snap.margin < 0:
            lead_changes += 1
        elif prev_margin < 0 and snap.margin > 0:
            lead_changes += 1
        prev_margin = snap.margin

    # Detect scoring runs (5+ consecutive points)
    scoring_runs = []
    run_score = 0
    run_start_idx = 0
    run_type = None

    for i, snap in enumerate(team_snapshots):
        margin_change = snap.margin - (team_snapshots[i - 1].margin if i > 0 else 0)

        if margin_change > 0:  # Team scored
            if run_type == "team":
                run_score += margin_change
            else:
                run_score = margin_change
                run_start_idx = i
                run_type = "team"

            if run_score >= 5:
                scoring_runs.append(
                    {
                        "type": "team",
                        "points": run_score,
                        "start_idx": run_start_idx,
                        "end_idx": i,
                        "start_game_seconds": team_snapshots[
                            run_start_idx
                        ].game_seconds,
                        "end_game_seconds": snap.game_seconds,
                    }
                )
        elif margin_change < 0:  # Opponent scored
            if run_type == "opp":
                run_score += abs(margin_change)
            else:
                run_score = abs(margin_change)
                run_start_idx = i
                run_type = "opp"

            if run_score >= 5:
                scoring_runs.append(
                    {
                        "type": "opp",
                        "points": run_score,
                        "start_idx": run_start_idx,
                        "end_idx": i,
                        "start_game_seconds": team_snapshots[
                            run_start_idx
                        ].game_seconds,
                        "end_game_seconds": snap.game_seconds,
                    }
                )
        else:
            # Reset run
            run_score = 0
            run_type = None

    # Build quarter summaries
    quarter_summaries = {}
    for q in range(1, 5):
        q_snaps = [s for s in team_snapshots if s.quarter == q]
        if q_snaps:
            q_start_score = (
                q_snaps[0].team_score
                - (q_snaps[0].fgm - q_snaps[0].tpm) * 2
                - q_snaps[0].tpm * 3
                - q_snaps[0].ftm
            )
            quarter_summaries[q] = {
                "team_pts": q_snaps[-1].team_score - q_snaps[0].team_score
                if len(q_snaps) > 1
                else q_snaps[0].team_score,
                "opp_pts": q_snaps[-1].opp_score - q_snaps[0].opp_score
                if len(q_snaps) > 1
                else q_snaps[0].opp_score,
                "fgm": q_snaps[-1].fgm - q_snaps[0].fgm
                if len(q_snaps) > 1
                else q_snaps[0].fgm,
                "fga": q_snaps[-1].fga - q_snaps[0].fga
                if len(q_snaps) > 1
                else q_snaps[0].fga,
                "tov": q_snaps[-1].tov - q_snaps[0].tov
                if len(q_snaps) > 1
                else q_snaps[0].tov,
            }

    return GameEvolutionReport(
        game_id=game_id,
        opponent=opponent,
        date=date,
        final_team_score=final_team_score,
        final_opp_score=final_opp_score,
        result=result,
        team_snapshots=team_snapshots,
        player_snapshots=player_snapshots,
        quarter_boundaries=quarter_boundaries,
        max_lead=max_lead,
        max_deficit=abs(max_deficit),
        lead_changes=lead_changes,
        scoring_runs=scoring_runs,
        quarter_summaries=quarter_summaries,
    )
