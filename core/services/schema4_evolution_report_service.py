"""Schema 4 evolution report builder.

Uses persisted schema-4 timeline fields as the primary source of truth.
"""

from __future__ import annotations

import ast
import json
from typing import Any, Dict, List, Optional, Tuple

from core.evolution_report import EvolutionReport, PlayerSnapshot, TeamSnapshot
from core.models import Game, GameEvent, PlayerStat
from core.services.evolution_report_service import EvolutionReportService


class Schema4EvolutionReportService:
    """Build evolution reports for schema 4 games."""

    @classmethod
    def build_report(cls, game_id: int) -> EvolutionReport:
        game = Game.query.get(game_id)
        if game is None:
            raise ValueError(f"Game with id {game_id} not found")

        events = cls._fetch_events(game_id)
        player_stats = PlayerStat.query.filter_by(game_id=game_id).all()
        team_snapshots, player_snapshots = cls._build_timeline(
            game=game,
            events=events,
            player_stats=player_stats,
        )

        quarter_summaries = EvolutionReportService._calculate_quarter_summaries(
            team_snapshots
        )
        scoring_runs = EvolutionReportService._detect_scoring_runs(team_snapshots)
        max_lead, max_deficit, lead_changes = EvolutionReportService._calculate_key_moments(
            team_snapshots
        )
        clutch_time = EvolutionReportService._calculate_clutch_time(team_snapshots)
        result = "W" if game.team_score > game.opponent_score else "L"

        return EvolutionReport(
            game_id=game.id,
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
    def _fetch_events(cls, game_id: int) -> List[GameEvent]:
        events = GameEvent.query.filter_by(game_id=game_id).all()
        return sorted(events, key=cls._event_sort_key)

    @classmethod
    def _event_sort_key(cls, event: GameEvent) -> Tuple[int, int, int]:
        game_seconds = cls._resolved_game_seconds(event)
        timestamp = event.timestamp or 0
        event_id = event.id or 0
        return (game_seconds, timestamp, event_id)

    @classmethod
    def _build_timeline(
        cls,
        game: Game,
        events: List[GameEvent],
        player_stats: List[PlayerStat],
    ) -> Tuple[List[TeamSnapshot], Dict[str, List[PlayerSnapshot]]]:
        if not events:
            return [], {}

        team_snapshots: List[TeamSnapshot] = []
        player_snapshots: Dict[str, List[PlayerSnapshot]] = {}
        team_totals = cls._empty_team_totals()
        player_totals: Dict[str, Dict[str, int]] = {}
        known_players = {
            stat.player_name for stat in player_stats if getattr(stat, "player_name", None)
        }
        current_lineup = cls._initial_lineup(events)
        team_score = 0
        opp_score = 0
        previous_quarter: Optional[int] = None

        def ensure_player(player_name: Optional[str]) -> None:
            if not player_name:
                return
            known_players.add(player_name)
            if player_name not in player_totals:
                player_totals[player_name] = cls._empty_player_totals()

        def save_snapshot(game_seconds: int, quarter: int, time_remaining: str) -> None:
            snapshot = TeamSnapshot(
                game_seconds=max(0, game_seconds),
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
            if team_snapshots and cls._same_snapshot(team_snapshots[-1], snapshot):
                team_snapshots[-1] = snapshot
            else:
                team_snapshots.append(snapshot)

            for player_name in sorted(known_players):
                totals = player_totals.get(player_name, cls._empty_player_totals())
                player_snapshot = PlayerSnapshot(
                    player_name=player_name,
                    game_seconds=max(0, game_seconds),
                    quarter=quarter,
                    time_remaining=time_remaining,
                    pts=totals["pts"],
                    fgm=totals["fgm"],
                    fga=totals["fga"],
                    tpm=totals["tpm"],
                    tpa=totals["tpa"],
                    ftm=totals["ftm"],
                    fta=totals["fta"],
                    oreb=totals["oreb"],
                    dreb=totals["dreb"],
                    ast=totals["ast"],
                    stl=totals["stl"],
                    blk=totals["blk"],
                    tov=totals["tov"],
                    pf=totals["pf"],
                    plus_minus=totals["plus_minus"],
                )
                player_snapshots.setdefault(player_name, []).append(player_snapshot)

        opening_quarter = cls._resolved_quarter(events[0])
        save_snapshot((opening_quarter - 1) * 600, opening_quarter, "10:00")

        for event in events:
            event_quarter = cls._resolved_quarter(event)
            event_seconds = cls._resolved_game_seconds(event)
            event_time_remaining = cls._resolved_time_remaining(event, event_quarter, event_seconds)

            if previous_quarter is not None and event_quarter != previous_quarter:
                save_snapshot(previous_quarter * 600, previous_quarter, "0:00")
                save_snapshot((event_quarter - 1) * 600, event_quarter, "10:00")

            ensure_player(event.player_name)
            cls._apply_event_to_totals(event, team_totals, player_totals)

            if event.event_type == "SUB_OUT" and event.player_name in current_lineup:
                current_lineup.remove(event.player_name)
            elif event.event_type == "SUB_IN" and event.player_name:
                if event.player_name not in current_lineup:
                    current_lineup.append(event.player_name)
            elif event.lineup_segment and event.lineup_segment.players:
                current_lineup = list(event.lineup_segment.players)

            team_score += cls._team_points_delta(event)
            opp_score += cls._opp_points_delta(event)

            if event.score_margin is not None:
                opp_score = max(0, team_score - event.score_margin)

            save_snapshot(event_seconds, event_quarter, event_time_remaining)
            previous_quarter = event_quarter

        final_quarter = max(previous_quarter or 1, cls._resolved_quarter(events[-1]))
        final_seconds = max(
            cls._resolved_game_seconds(events[-1]),
            final_quarter * 600,
        )
        team_score = game.team_score
        opp_score = game.opponent_score
        save_snapshot(final_seconds, final_quarter, "0:00")

        player_snapshots = {
            player_name: snapshots
            for player_name, snapshots in player_snapshots.items()
            if snapshots
        }
        return team_snapshots, player_snapshots

    @staticmethod
    def _empty_team_totals() -> Dict[str, int]:
        return {
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

    @staticmethod
    def _empty_player_totals() -> Dict[str, int]:
        return {
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

    @classmethod
    def _apply_event_to_totals(
        cls,
        event: GameEvent,
        team_totals: Dict[str, int],
        player_totals: Dict[str, Dict[str, int]],
    ) -> None:
        player_name = event.player_name
        if player_name and player_name not in player_totals:
            player_totals[player_name] = cls._empty_player_totals()
        player = player_totals.get(player_name)

        if event.event_type == "SHOT_2PT":
            team_totals["fga"] += 1
            if player is not None:
                player["fga"] += 1
            if event.shot_attempt == "made":
                team_totals["fgm"] += 1
                if player is not None:
                    player["fgm"] += 1
                    player["pts"] += 2

        elif event.event_type == "SHOT_3PT":
            team_totals["fga"] += 1
            team_totals["tpa"] += 1
            if player is not None:
                player["fga"] += 1
                player["tpa"] += 1
            if event.shot_attempt == "made":
                team_totals["fgm"] += 1
                team_totals["tpm"] += 1
                if player is not None:
                    player["fgm"] += 1
                    player["tpm"] += 1
                    player["pts"] += 3

        elif event.event_type == "FT":
            detail = cls._parse_detail(event.detail)
            ftm = cls._safe_int(detail.get("ftm")) or 0
            fta = cls._safe_int(detail.get("fta")) or 0
            team_totals["ftm"] += ftm
            team_totals["fta"] += fta
            if player is not None:
                player["ftm"] += ftm
                player["fta"] += fta
                player["pts"] += ftm

        elif event.event_type == "FT_MADE":
            team_totals["ftm"] += 1
            team_totals["fta"] += 1
            if player is not None:
                player["ftm"] += 1
                player["fta"] += 1
                player["pts"] += 1

        elif event.event_type == "FT_MISS":
            team_totals["fta"] += 1
            if player is not None:
                player["fta"] += 1

        elif event.event_type in ("TURNOVER",):
            team_totals["tov"] += 1
            if player is not None:
                player["tov"] += 1

        elif event.event_type in ("AST",):
            team_totals["ast"] += 1
            if player is not None:
                player["ast"] += 1

        elif event.event_type in ("STL", "STEAL"):
            team_totals["stl"] += 1
            if player is not None:
                player["stl"] += 1

        elif event.event_type in ("BLK", "BLOCK"):
            team_totals["blk"] += 1
            if player is not None:
                player["blk"] += 1

        elif event.event_type in ("OREB", "REBOUND_OFFENSIVE"):
            team_totals["orb"] += 1
            if player is not None:
                player["oreb"] += 1

        elif event.event_type in ("DREB", "REBOUND_DEFENSIVE"):
            team_totals["drb"] += 1
            if player is not None:
                player["dreb"] += 1

        elif event.event_type in ("FOUL", "FOUL_PERSONAL"):
            if player is not None:
                player["pf"] += 1

    @classmethod
    def _initial_lineup(cls, events: List[GameEvent]) -> List[str]:
        for event in events:
            if event.lineup_segment and event.lineup_segment.players:
                return list(event.lineup_segment.players)
        return []

    @staticmethod
    def _same_snapshot(left: TeamSnapshot, right: TeamSnapshot) -> bool:
        return (
            left.game_seconds == right.game_seconds
            and left.quarter == right.quarter
            and left.team_score == right.team_score
            and left.opp_score == right.opp_score
            and left.fgm == right.fgm
            and left.fga == right.fga
            and left.tpm == right.tpm
            and left.tpa == right.tpa
            and left.ftm == right.ftm
            and left.fta == right.fta
            and left.orb == right.orb
            and left.drb == right.drb
            and left.ast == right.ast
            and left.stl == right.stl
            and left.blk == right.blk
            and left.tov == right.tov
            and left.lineup == right.lineup
        )

    @classmethod
    def _resolved_quarter(cls, event: GameEvent) -> int:
        if event.quarter:
            return event.quarter
        if event.game_seconds is not None:
            return max(1, (event.game_seconds // 600) + 1)
        return 1

    @classmethod
    def _resolved_game_seconds(cls, event: GameEvent) -> int:
        if event.game_seconds is not None:
            return event.game_seconds
        quarter = cls._resolved_quarter(event)
        remaining = cls._parse_time_remaining(event.time_remaining)
        if remaining is None:
            return max(0, (quarter - 1) * 600)
        return ((quarter - 1) * 600) + max(0, 600 - remaining)

    @classmethod
    def _resolved_time_remaining(
        cls, event: GameEvent, quarter: int, game_seconds: int
    ) -> str:
        if event.time_remaining:
            return event.time_remaining
        quarter_elapsed = max(0, game_seconds - ((quarter - 1) * 600))
        remaining = max(0, 600 - quarter_elapsed)
        return f"{remaining // 60}:{remaining % 60:02d}"

    @staticmethod
    def _team_points_delta(event: GameEvent) -> int:
        if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
            return 2
        if event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
            return 3
        if event.event_type == "FT_MADE":
            return 1
        if event.event_type == "FT":
            detail = Schema4EvolutionReportService._parse_detail(event.detail)
            return Schema4EvolutionReportService._safe_int(detail.get("ftm")) or 0
        return 0

    @staticmethod
    def _opp_points_delta(event: GameEvent) -> int:
        if event.event_type != "OPP_SCORE":
            return 0
        detail = Schema4EvolutionReportService._parse_detail(event.detail)
        return Schema4EvolutionReportService._safe_int(detail.get("points")) or 0

    @staticmethod
    def _parse_detail(detail: Any) -> Dict[str, Any]:
        if detail is None:
            return {}
        if isinstance(detail, dict):
            return detail
        if isinstance(detail, str):
            try:
                parsed = json.loads(detail)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                pass
            try:
                parsed = ast.literal_eval(detail)
                return parsed if isinstance(parsed, dict) else {}
            except (ValueError, SyntaxError):
                return {}
        return {}

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

    @staticmethod
    def _parse_time_remaining(time_remaining: Optional[str]) -> Optional[int]:
        if not time_remaining or ":" not in str(time_remaining):
            return None
        minutes_str, seconds_str = str(time_remaining).split(":", 1)
        try:
            return (int(minutes_str) * 60) + int(seconds_str)
        except (TypeError, ValueError):
            return None
