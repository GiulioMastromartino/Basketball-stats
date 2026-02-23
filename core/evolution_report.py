"""
Evolution Report Domain Models

This module contains dataclasses and pure calculation functions for the
evolution report feature. No database access or Flask dependencies.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    Perform safe division, returning default if denominator is zero.

    Args:
        numerator: The numerator for division.
        denominator: The denominator for division.
        default: Value to return if denominator is zero.

    Returns:
        Result of division or default value.
    """
    if denominator == 0:
        return default
    return numerator / denominator


def round_to(value: float, decimals: int = 1) -> float:
    """
    Round a value to specified decimal places.

    Args:
        value: The value to round.
        decimals: Number of decimal places.

    Returns:
        Rounded value.
    """
    return round(value, decimals)


def parse_time_to_seconds(time_str: str) -> int:
    """
    Convert MM:SS time string to total seconds.

    Args:
        time_str: Time in MM:SS format.

    Returns:
        Total seconds as integer.
    """
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        return 0
    except (ValueError, AttributeError):
        return 0


def seconds_to_time(seconds: int) -> str:
    """
    Convert seconds to MM:SS format.

    Args:
        seconds: Total seconds.

    Returns:
        Time string in MM:SS format.
    """
    if seconds < 0:
        seconds = 0
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class TeamSnapshot:
    """
    Team statistics at a specific moment in time during a game.

    Represents cumulative team performance metrics calculated up to a given
    point in the game, along with the current game state.
    """

    game_seconds: int
    quarter: int
    time_remaining: str
    team_score: int
    opp_score: int
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
    lineup: List[str] = field(default_factory=list)
    margin: int = field(init=False)
    possessions: float = field(init=False)
    oer: float = field(init=False)
    der: float = field(init=False)
    efg_pct: float = field(init=False)
    ts_pct: float = field(init=False)
    tov_pct: float = field(init=False)
    orb_pct: float = field(init=False)
    ft_rate: float = field(init=False)

    def __post_init__(self) -> None:
        self.margin = self.team_score - self.opp_score
        total_reb = self.orb + self.drb
        self.possessions = round_to(self.fga + 0.44 * self.fta - self.orb + self.tov)
        self.oer = round_to(safe_div(self.team_score, self.possessions) * 100)
        self.der = round_to(safe_div(self.opp_score, self.possessions) * 100)
        self.efg_pct = round_to(safe_div(self.fgm + 0.5 * self.tpm, self.fga) * 100)
        self.ts_pct = round_to(
            safe_div(self.team_score, 2 * (self.fga + 0.44 * self.fta)) * 100
        )
        self.tov_pct = round_to(
            safe_div(self.tov, self.fga + 0.44 * self.fta + self.tov) * 100
        )
        self.orb_pct = (
            round_to(safe_div(self.orb, self.orb + (total_reb - self.orb)) * 100)
            if total_reb > 0
            else 0.0
        )
        self.ft_rate = round_to(safe_div(self.ftm, self.fga) * 100)

    @property
    def reb(self) -> int:
        return self.orb + self.drb

    @property
    def fg_pct(self) -> float:
        return round_to(safe_div(self.fgm, self.fga) * 100)

    @property
    def tp_pct(self) -> float:
        return round_to(safe_div(self.tpm, self.tpa) * 100)

    @property
    def ft_pct(self) -> float:
        return round_to(safe_div(self.ftm, self.fta) * 100)


@dataclass
class PlayerSnapshot:
    """
    Player statistics at a specific moment in time during a game.

    Represents cumulative player performance metrics calculated up to a given
    point in the game.
    """

    player_name: str
    game_seconds: int
    quarter: int
    time_remaining: str
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
    ts_pct: float = field(init=False)
    efg_pct: float = field(init=False)

    def __post_init__(self) -> None:
        self.efg_pct = round_to(safe_div(self.fgm + 0.5 * self.tpm, self.fga) * 100)
        self.ts_pct = round_to(
            safe_div(self.pts, 2 * (self.fga + 0.44 * self.fta)) * 100
        )

    @property
    def reb(self) -> int:
        return self.oreb + self.dreb

    @property
    def fg_pct(self) -> float:
        return round_to(safe_div(self.fgm, self.fga) * 100)

    @property
    def tp_pct(self) -> float:
        return round_to(safe_div(self.tpm, self.tpa) * 100)

    @property
    def ft_pct(self) -> float:
        return round_to(safe_div(self.ftm, self.fta) * 100)


@dataclass
class ScoringRun:
    """
    Represents a scoring run during a game.

    A scoring run is a sequence where one team scores multiple points
    consecutively without the opponent scoring.
    """

    team: str
    points: int
    start_seconds: int
    end_seconds: int
    start_quarter: int
    end_quarter: int
    lineup: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.team not in ("team", "opp"):
            raise ValueError(f"team must be 'team' or 'opp', got '{self.team}'")

    @property
    def start_time(self) -> str:
        return seconds_to_time(self.start_seconds)

    @property
    def end_time(self) -> str:
        return seconds_to_time(self.end_seconds)


@dataclass
class QuarterSummary:
    """
    Per-quarter statistical summary for a team.

    Contains all relevant counting stats and the margin for a single quarter.
    """

    quarter: int
    team_pts: int
    opp_pts: int
    team_fgm: int
    team_fga: int
    team_tpm: int
    team_tpa: int
    team_ftm: int
    team_fta: int
    team_tov: int
    team_orb: int = 0
    team_dreb: int = 0
    team_ast: int = 0
    margin: int = field(init=False)

    def __post_init__(self) -> None:
        self.margin = self.team_pts - self.opp_pts

    @property
    def pts(self) -> int:
        return self.team_pts

    @property
    def reb(self) -> int:
        return self.team_orb + self.team_dreb

    @property
    def fg_pct(self) -> float:
        return round_to(safe_div(self.team_fgm, self.team_fga) * 100)

    @property
    def tp_pct(self) -> float:
        return round_to(safe_div(self.team_tpm, self.team_tpa) * 100)

    @property
    def ft_pct(self) -> float:
        return round_to(safe_div(self.team_ftm, self.team_fta) * 100)

    @property
    def possessions(self) -> float:
        return round_to(
            self.team_fga + 0.44 * self.team_fta - self.team_orb + self.team_tov
        )

    @property
    def oer(self) -> float:
        return round_to(safe_div(self.team_pts, self.possessions) * 100)

    @property
    def efg_pct(self) -> float:
        return round_to(
            safe_div(self.team_fgm + 0.5 * self.team_tpm, self.team_fga) * 100
        )

    @property
    def ts_pct(self) -> float:
        return round_to(
            safe_div(self.team_pts, 2 * (self.team_fga + 0.44 * self.team_fta)) * 100
        )

    @property
    def tov_pct(self) -> float:
        return round_to(
            safe_div(
                self.team_tov, self.team_fga + 0.44 * self.team_fta + self.team_tov
            )
            * 100
        )

    @property
    def oreb_pct(self) -> float:
        total_reb = self.team_orb + self.team_dreb
        if total_reb == 0:
            return 0.0
        opp_dreb_estimate = max(0, total_reb - self.team_orb)
        return round_to(
            safe_div(self.team_orb, self.team_orb + opp_dreb_estimate) * 100
        )

    @property
    def fta_fga(self) -> float:
        return round_to(safe_div(self.team_fta, self.team_fga) * 100)

    @property
    def ast_tov(self) -> float:
        return round_to(safe_div(self.team_ast, self.team_tov))


@dataclass
class EvolutionReport:
    """
    Complete evolution report for a basketball game.

    Contains all snapshots, summaries, and analysis for a single game,
    including team performance over time, player statistics, and key moments.
    """

    game_id: int
    opponent: str
    date: str
    final_team_score: int
    final_opp_score: int
    result: str
    team_snapshots: List[TeamSnapshot] = field(default_factory=list)
    player_snapshots: Dict[str, List[PlayerSnapshot]] = field(default_factory=dict)
    quarter_summaries: Dict[int, QuarterSummary] = field(default_factory=dict)
    max_lead: int = 0
    max_deficit: int = 0
    lead_changes: int = 0
    scoring_runs: List[ScoringRun] = field(default_factory=list)
    clutch_time: Optional[Dict[str, Any]] = None
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self) -> None:
        if self.result not in ("W", "L"):
            raise ValueError(f"result must be 'W' or 'L', got '{self.result}'")

    @property
    def final_margin(self) -> int:
        """Return the final margin of the game."""
        return self.final_team_score - self.final_opp_score

    @property
    def is_win(self) -> bool:
        """Return True if the game was won."""
        return self.result == "W"

    @property
    def total_possessions(self) -> float:
        """Return total possessions from the last team snapshot."""
        if self.team_snapshots:
            return self.team_snapshots[-1].possessions
        return 0.0

    @property
    def quarters_played(self) -> int:
        """Return the number of quarters played (including OT)."""
        return len(self.quarter_summaries)

    def get_snapshot_at_time(self, game_seconds: int) -> Optional[TeamSnapshot]:
        """
        Get the team snapshot closest to a specific game time.

        Args:
            game_seconds: Target time in seconds.

        Returns:
            TeamSnapshot closest to the target time, or None if no snapshots.
        """
        if not self.team_snapshots:
            return None
        return min(
            self.team_snapshots, key=lambda s: abs(s.game_seconds - game_seconds)
        )

    def get_player_final_stats(self, player_name: str) -> Optional[PlayerSnapshot]:
        """
        Get the final stats for a specific player.

        Args:
            player_name: Name of the player.

        Returns:
            Final PlayerSnapshot for the player, or None if not found.
        """
        snapshots = self.player_snapshots.get(player_name, [])
        if not snapshots:
            return None
        return snapshots[-1]
