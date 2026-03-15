"""Evolution Report Service Layer.

This module contains the business logic for building evolution reports,
including database queries, event processing, and metrics calculation.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.models import Game, GameEvent, PlayerStat, ShotEvent, LineupSegment, db
from core.evolution_report import (
    TeamSnapshot,
    PlayerSnapshot,
    ScoringRun,
    QuarterSummary,
    EvolutionReport,
    safe_div,
    round_to,
)


class EvolutionReportService:
    """
    Service class for building game evolution reports.

    This class provides methods for querying game data, processing events
    into time-series snapshots, calculating advanced metrics, detecting
    scoring runs and lead changes, and building complete EvolutionReport objects.

    The class is stateless - all methods are class methods that operate
    on the provided data without storing instance state.
    """

    @classmethod
    def build_report(cls, game_id: int, snapshot_interval: int = 60) -> EvolutionReport:
        """
        Build a complete evolution report for a game.

        Main entry point for creating evolution reports. Fetches all necessary
        data from the database, processes events into time-series snapshots,
        calculates metrics, and assembles the final report.

        Args:
            game_id: The database ID of the game to analyze.
            snapshot_interval: Seconds between snapshots (default 60 = every minute).

        Returns:
            EvolutionReport containing all time-series data and analysis.

        Raises:
            ValueError: If the game with the given ID doesn't exist.
        """
        game, events, player_stats = cls._fetch_game_data(game_id)

        if game is None:
            raise ValueError(f"Game with id {game_id} not found")

        team_snapshots, player_snapshots = cls._process_events(
            events, snapshot_interval
        )

        quarter_summaries = cls._calculate_quarter_summaries(team_snapshots)

        scoring_runs = cls._detect_scoring_runs(team_snapshots)

        max_lead, max_deficit, lead_changes = cls._calculate_key_moments(team_snapshots)

        clutch_time = cls._calculate_clutch_time(team_snapshots)

        result = "W" if game.team_score > game.opponent_score else "L"

        return EvolutionReport(
            game_id=game_id,
            opponent=game.opponent,
            date=game.date,
            final_team_score=game.team_score,
            final_opp_score=game.opponent_score,
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

    @classmethod
    def _fetch_game_data(
        cls, game_id: int
    ) -> Tuple[Optional[Game], List[GameEvent], List[PlayerStat]]:
        """
        Fetch game, events, and player stats from the database.

        Args:
            game_id: The database ID of the game.

        Returns:
            Tuple of (Game, List[GameEvent], List[PlayerStat]).
            Events are ordered by game_seconds. Returns (None, [], []) if
            game not found.
        """
        game = Game.query.get(game_id)

        if game is None:
            return None, [], []

        events = (
            GameEvent.query.filter_by(game_id=game_id)
            .order_by(GameEvent.game_seconds.asc().nulls_first())
            .all()
        )

        player_stats = PlayerStat.query.filter_by(game_id=game_id).all()

        return game, events, player_stats

    @classmethod
    def _process_events(
        cls, events: List[GameEvent], snapshot_interval: int
    ) -> Tuple[List[TeamSnapshot], Dict[str, List[PlayerSnapshot]]]:
        """
        Process game events into time-series snapshots.

        Core time-series processing that creates snapshots at regular intervals
        and at quarter boundaries. Tracks running totals for team and each player,
        and handles all event types.

        Args:
            events: List of GameEvent objects ordered by game_seconds.
            snapshot_interval: Seconds between snapshots.

        Returns:
            Tuple of (team_snapshots_list, player_snapshots_dict).
        """
        team_snapshots: List[TeamSnapshot] = []
        player_snapshots: Dict[str, List[PlayerSnapshot]] = {}

        if not events:
            return team_snapshots, player_snapshots

        team_totals = {
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
            "pf": 0,
        }
        player_totals: Dict[str, Dict[str, int]] = {}

        team_score = 0
        opp_score = 0
        current_lineup: List[str] = []
        current_quarter = 1
        current_time_remaining = "10:00"

        last_snapshot_time = -snapshot_interval

        quarter_boundaries = {1: 0, 2: 600, 3: 1200, 4: 1800}
        next_quarter_boundary = 600

        def _init_player(player_name: str) -> None:
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

        def _parse_detail(detail: Any) -> Dict:
            if detail is None:
                return {}
            if isinstance(detail, dict):
                return detail
            if isinstance(detail, str):
                try:
                    parsed = json.loads(detail)
                    return parsed if isinstance(parsed, dict) else {}
                except (json.JSONDecodeError, ValueError):
                    try:
                        import ast

                        parsed = ast.literal_eval(detail)
                        return parsed if isinstance(parsed, dict) else {}
                    except (ValueError, SyntaxError):
                        return {}
            return {}

        def _create_team_snapshot(
            game_seconds: int, quarter: int, time_remaining: str
        ) -> TeamSnapshot:
            return TeamSnapshot(
                game_seconds=game_seconds,
                quarter=quarter,
                time_remaining=time_remaining,
                team_score=team_score,
                opp_score=opp_score,
                fgm=team_totals["fgm"],
                fga=team_totals["fga"],
                tpm=team_totals["tpm"],
                tpa=team_totals["tpa"],
                ftm=team_totals["ftm"],
                fta=team_totals["fta"],
                orb=team_totals["orb"],
                drb=team_totals["drb"],
                ast=team_totals["ast"],
                stl=team_totals["stl"],
                blk=team_totals["blk"],
                tov=team_totals["tov"],
                lineup=current_lineup.copy(),
            )

        def _create_player_snapshot(
            player_name: str, game_seconds: int, quarter: int, time_remaining: str
        ) -> PlayerSnapshot:
            p = player_totals.get(player_name, {})
            return PlayerSnapshot(
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

        def _save_snapshot(
            game_seconds: int, quarter: int, time_remaining: str
        ) -> None:
            nonlocal last_snapshot_time
            snapshot = _create_team_snapshot(game_seconds, quarter, time_remaining)
            team_snapshots.append(snapshot)
            last_snapshot_time = game_seconds

            for pname in player_totals:
                psnap = _create_player_snapshot(
                    pname, game_seconds, quarter, time_remaining
                )
                if pname not in player_snapshots:
                    player_snapshots[pname] = []
                player_snapshots[pname].append(psnap)

        def _snapshot_matches_current(snapshot: TeamSnapshot) -> bool:
            return (
                snapshot.team_score == team_score
                and snapshot.opp_score == opp_score
                and snapshot.fgm == team_totals["fgm"]
                and snapshot.fga == team_totals["fga"]
                and snapshot.tpm == team_totals["tpm"]
                and snapshot.tpa == team_totals["tpa"]
                and snapshot.ftm == team_totals["ftm"]
                and snapshot.fta == team_totals["fta"]
                and snapshot.orb == team_totals["orb"]
                and snapshot.drb == team_totals["drb"]
                and snapshot.ast == team_totals["ast"]
                and snapshot.stl == team_totals["stl"]
                and snapshot.blk == team_totals["blk"]
                and snapshot.tov == team_totals["tov"]
                and snapshot.lineup == current_lineup
            )

        prev_quarter = None

        for event in events:
            event_type = event.event_type or ""
            player_name = event.player_name
            quarter = event.quarter or 1
            game_seconds = event.game_seconds if event.game_seconds is not None else 0
            time_remaining = event.time_remaining or "10:00"
            detail = _parse_detail(event.detail)
            shot_attempt = event.shot_attempt or ""

            current_quarter = quarter
            current_time_remaining = time_remaining

            if prev_quarter is not None and quarter != prev_quarter:
                _save_snapshot(game_seconds - 1, prev_quarter, "0:00")

            if event_type == "SHOT_2PT":
                team_totals["fga"] += 1
                if shot_attempt == "made":
                    team_totals["fgm"] += 1
                    team_score += 2
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["fga"] += 1
                    if shot_attempt == "made":
                        player_totals[player_name]["fgm"] += 1
                        player_totals[player_name]["pts"] += 2

            elif event_type == "SHOT_3PT":
                team_totals["fga"] += 1
                team_totals["tpa"] += 1
                if shot_attempt == "made":
                    team_totals["fgm"] += 1
                    team_totals["tpm"] += 1
                    team_score += 3
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["fga"] += 1
                    player_totals[player_name]["tpa"] += 1
                    if shot_attempt == "made":
                        player_totals[player_name]["fgm"] += 1
                        player_totals[player_name]["tpm"] += 1
                        player_totals[player_name]["pts"] += 3

            elif event_type == "FT":
                ftm = detail.get("ftm", 0) if isinstance(detail, dict) else 0
                fta = detail.get("fta", 0) if isinstance(detail, dict) else 0
                team_totals["ftm"] += ftm
                team_totals["fta"] += fta
                team_score += ftm
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["ftm"] += ftm
                    player_totals[player_name]["fta"] += fta
                    player_totals[player_name]["pts"] += ftm

            elif event_type == "FT_MADE":
                team_totals["ftm"] += 1
                team_totals["fta"] += 1
                team_score += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["ftm"] += 1
                    player_totals[player_name]["fta"] += 1
                    player_totals[player_name]["pts"] += 1

            elif event_type == "FT_MISS":
                team_totals["fta"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["fta"] += 1

            elif event_type == "TURNOVER":
                team_totals["tov"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["tov"] += 1

            elif event_type == "AST":
                team_totals["ast"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["ast"] += 1

            elif event_type in ("STL", "STEAL"):
                team_totals["stl"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["stl"] += 1

            elif event_type in ("BLK", "BLOCK"):
                team_totals["blk"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["blk"] += 1

            elif event_type in ("OREB", "REBOUND_OFFENSIVE"):
                team_totals["orb"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["oreb"] += 1

            elif event_type in ("DREB", "REBOUND_DEFENSIVE"):
                team_totals["drb"] += 1
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["dreb"] += 1

            elif event_type in ("FOUL", "FOUL_PERSONAL"):
                if player_name:
                    _init_player(player_name)
                    player_totals[player_name]["pf"] += 1

            elif event_type == "OPP_SCORE":
                points = 0
                if isinstance(detail, dict):
                    points = detail.get("points", 0)
                elif isinstance(detail, str):
                    try:
                        points = int(detail)
                    except (ValueError, TypeError):
                        points = 2
                elif isinstance(detail, (int, float)):
                    points = int(detail)
                else:
                    points = detail.get("points", 2) if detail else 2
                opp_score += points

            elif event_type == "SUB_IN":
                if player_name and player_name not in current_lineup:
                    current_lineup.append(player_name)

            elif event_type == "SUB_OUT":
                if player_name in current_lineup:
                    current_lineup.remove(player_name)

            elif event_type == "NEXT_QUARTER":
                _save_snapshot(game_seconds, quarter, time_remaining)

            if game_seconds - last_snapshot_time >= snapshot_interval:
                _save_snapshot(game_seconds, quarter, time_remaining)

            prev_quarter = quarter

        if not team_snapshots or not _snapshot_matches_current(team_snapshots[-1]):
            final_seconds = events[-1].game_seconds if events else 2400
            if final_seconds is None:
                final_seconds = 2400
            _save_snapshot(final_seconds + 1, current_quarter, "0:00")

        return team_snapshots, player_snapshots

    @classmethod
    def _calculate_quarter_summaries(
        cls, team_snapshots: List[TeamSnapshot]
    ) -> Dict[int, QuarterSummary]:
        """
        Calculate per-quarter statistical summaries.

        Aggregates team statistics for each quarter by comparing
        snapshots at quarter boundaries.

        Args:
            team_snapshots: List of team snapshots ordered by game_seconds.

        Returns:
            Dict mapping quarter numbers to QuarterSummary objects.
        """
        summaries: Dict[int, QuarterSummary] = {}

        quarter_starts: Dict[int, TeamSnapshot] = {}
        quarter_ends: Dict[int, TeamSnapshot] = {}

        for snap in team_snapshots:
            q = snap.quarter
            if q not in quarter_starts:
                quarter_starts[q] = snap
            quarter_ends[q] = snap

        for q in sorted(quarter_starts.keys()):
            start = quarter_starts[q]
            end = quarter_ends[q]

            if start is None or end is None:
                continue

            start_team_pts = start.team_score
            start_opp_pts = start.opp_score
            if q > 1 and (q - 1) in quarter_ends:
                prev_end = quarter_ends[q - 1]
                start_team_pts = prev_end.team_score
                start_opp_pts = prev_end.opp_score

            team_pts = end.team_score - start_team_pts
            opp_pts = end.opp_score - start_opp_pts

            start_fgm = start.fgm
            start_fga = start.fga
            start_tpm = start.tpm
            start_tpa = start.tpa
            start_ftm = start.ftm
            start_fta = start.fta
            start_tov = start.tov
            start_orb = start.orb
            start_dreb = start.drb
            start_ast = start.ast

            if q > 1 and (q - 1) in quarter_ends:
                prev_end = quarter_ends[q - 1]
                start_fgm = prev_end.fgm
                start_fga = prev_end.fga
                start_tpm = prev_end.tpm
                start_tpa = prev_end.tpa
                start_ftm = prev_end.ftm
                start_fta = prev_end.fta
                start_tov = prev_end.tov
                start_orb = prev_end.orb
                start_dreb = prev_end.drb
                start_ast = prev_end.ast

            summaries[q] = QuarterSummary(
                quarter=q,
                team_pts=team_pts,
                opp_pts=opp_pts,
                team_fgm=end.fgm - start_fgm,
                team_fga=end.fga - start_fga,
                team_tpm=end.tpm - start_tpm,
                team_tpa=end.tpa - start_tpa,
                team_ftm=end.ftm - start_ftm,
                team_fta=end.fta - start_fta,
                team_tov=end.tov - start_tov,
                team_orb=end.orb - start_orb,
                team_dreb=end.drb - start_dreb,
                team_ast=end.ast - start_ast,
            )

        return summaries

    @classmethod
    def _detect_scoring_runs(
        cls, team_snapshots: List[TeamSnapshot], min_run: int = 5
    ) -> List[ScoringRun]:
        """
        Detect scoring runs of consecutive points.

        Identifies sequences where one team scores min_run or more points
        without the opponent scoring. The lineup captured is the one at the
        START of the run (when it first becomes a run of 5+ points).

        Args:
            team_snapshots: List of team snapshots ordered by game_seconds.
            min_run: Minimum consecutive points to qualify as a run (default 5).

        Returns:
            List of ScoringRun objects detected in the game.
        """
        runs: List[ScoringRun] = []

        if len(team_snapshots) < 2:
            return runs

        current_run_team: Optional[str] = None
        current_run_points = 0
        current_run_start_seconds = 0
        current_run_quarter = 1
        current_run_lineup: List[str] = []

        def _finalize_run(end_snapshot: TeamSnapshot) -> None:
            if current_run_team is None or current_run_points < min_run:
                return

            runs.append(
                ScoringRun(
                    team=current_run_team,
                    points=current_run_points,
                    start_seconds=current_run_start_seconds,
                    end_seconds=end_snapshot.game_seconds,
                    start_quarter=current_run_quarter,
                    end_quarter=end_snapshot.quarter,
                    lineup=current_run_lineup,
                )
            )

        for i, snap in enumerate(team_snapshots):
            if i == 0:
                continue

            prev_snap = team_snapshots[i - 1]
            margin_change = snap.margin - prev_snap.margin

            if margin_change > 0:
                if current_run_team == "team":
                    current_run_points += margin_change
                else:
                    _finalize_run(prev_snap)
                    current_run_team = "team"
                    current_run_points = margin_change
                    current_run_start_seconds = prev_snap.game_seconds
                    current_run_quarter = prev_snap.quarter
                    current_run_lineup = prev_snap.lineup

            elif margin_change < 0:
                if current_run_team == "opp":
                    current_run_points += abs(margin_change)
                else:
                    _finalize_run(prev_snap)
                    current_run_team = "opp"
                    current_run_points = abs(margin_change)
                    current_run_start_seconds = prev_snap.game_seconds
                    current_run_quarter = prev_snap.quarter
                    current_run_lineup = prev_snap.lineup

            else:
                _finalize_run(prev_snap)
                current_run_team = None
                current_run_points = 0
                current_run_lineup = []

        _finalize_run(team_snapshots[-1])

        return runs

    @classmethod
    def _calculate_key_moments(
        cls, team_snapshots: List[TeamSnapshot]
    ) -> Tuple[int, int, int]:
        """
        Calculate key game moments: max lead, max deficit, and lead changes.

        Analyzes the margin across all snapshots to find the maximum
        lead and deficit, and counts the number of times the lead
        changed hands.

        Args:
            team_snapshots: List of team snapshots ordered by game_seconds.

        Returns:
            Tuple of (max_lead, max_deficit, lead_changes).
        """
        if not team_snapshots:
            return 0, 0, 0

        margins = [snap.margin for snap in team_snapshots]
        max_lead = max([0] + margins)
        final_margin = margins[-1]
        max_deficit = abs(final_margin) if final_margin < 0 else abs(min([0] + margins))
        lead_changes = 0
        prev_margin = margins[0]

        for margin in margins[1:]:
            if prev_margin >= 0 and margin < 0:
                lead_changes += 1
            prev_margin = margin

        return max_lead, max_deficit, lead_changes

    @classmethod
    def _calculate_clutch_time(
        cls, team_snapshots: List[TeamSnapshot]
    ) -> Optional[Dict]:
        """
        Calculate clutch time statistics if applicable.

        Clutch time is defined as the last 5 minutes of the 4th quarter
        (or overtime) when the score margin is within 5 points.

        Args:
            team_snapshots: List of team snapshots ordered by game_seconds.

        Returns:
            Dict with clutch statistics if clutch time occurred, None otherwise.
        """
        if not team_snapshots:
            return None

        clutch_snapshots = [
            snap
            for snap in team_snapshots
            if snap.quarter >= 4 and abs(snap.margin) <= 5
        ]

        if not clutch_snapshots:
            return None

        clutch_start = None
        clutch_end = None
        in_clutch = False

        for snap in team_snapshots:
            if snap.quarter >= 4:
                is_clutch_moment = abs(snap.margin) <= 5
                if is_clutch_moment and not in_clutch:
                    clutch_start = snap
                    in_clutch = True
                elif is_clutch_moment:
                    clutch_end = snap
                elif in_clutch and not is_clutch_moment:
                    pass

        if clutch_start is None:
            return None

        clutch_snaps = [
            snap
            for snap in team_snapshots
            if snap.quarter >= 4
            and snap.game_seconds
            >= (clutch_start.game_seconds if clutch_start else 2700)
        ]

        if not clutch_snaps:
            return None

        first_clutch = clutch_snaps[0]
        last_clutch = clutch_snaps[-1]

        return {
            "start_seconds": first_clutch.game_seconds,
            "start_margin": first_clutch.margin,
            "end_margin": last_clutch.margin,
            "team_pts_in_clutch": last_clutch.team_score - first_clutch.team_score,
            "opp_pts_in_clutch": last_clutch.opp_score - first_clutch.opp_score,
            "margin_change": last_clutch.margin - first_clutch.margin,
            "clutch_fgm": last_clutch.fgm - first_clutch.fgm,
            "clutch_fga": last_clutch.fga - first_clutch.fga,
            "clutch_tov": last_clutch.tov - first_clutch.tov,
            "quarter": last_clutch.quarter,
        }

    @classmethod
    def _get_lineup_at_time(
        cls, events: List[GameEvent], game_seconds: int
    ) -> List[str]:
        """
        Determine which players were on court at a specific time.

        Processes SUB_IN and SUB_OUT events up to the target time to
        determine the active lineup.

        Args:
            events: List of GameEvent objects ordered by game_seconds.
            game_seconds: Target game time in seconds.

        Returns:
            List of player names on court at the specified time.
        """
        lineup: List[str] = []

        for event in events:
            if event.game_seconds is None or event.game_seconds > game_seconds:
                break

            event_type = event.event_type or ""
            player_name = event.player_name

            if event_type == "SUB_IN":
                if player_name and player_name not in lineup:
                    lineup.append(player_name)

            elif event_type == "SUB_OUT":
                if player_name in lineup:
                    lineup.remove(player_name)

        return lineup
