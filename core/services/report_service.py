"""
Report Service Layer
Encapsulates all data preparation for PDF reports and advanced analytics.
"""

import ast
import json
import statistics
from collections import defaultdict
from datetime import datetime
from sqlalchemy import desc, func
from weasyprint import HTML

from core.models import (
    Game,
    GameEvent,
    Lineup,
    LineupSegment,
    Play,
    PlayerLineupStats,
    PlayerStat,
    Possession,
    ShotEvent,
    ShotZone,
    SystemSetting,
    db,
)
from core.services.analytics_service import AnalyticsService
from core.services.evolution_report_service import EvolutionReportService
from core.services.schema4_evolution_report_service import (
    Schema4EvolutionReportService,
)
from core.charts import (
    generate_shot_chart,
    generate_team_shot_chart,
    generate_player_charts,
    generate_team_scoring_trend,
)
from core.play_analytics import (
    get_summary_play_stats,
    get_summary_play_player_stats,
    get_summary_player_play_stats,
    get_untracked_percentages,
    get_summary_player_top_plays_by_points,
)
from core.utils import (
    calculate_efg_percent,
    calculate_ortg,
    calculate_possessions,
    parse_minutes,
    safe_percentage,
)
from core.advanced_game_report import TeamBox, PlayerBox, build_advanced_game_report
from core.advanced_pdf_reports import (
    AdvancedPDFReports,
    generate_visual_game_report_bytes,
    generate_lineup_report_bytes,
    generate_player_scouting_card_bytes,
    generate_season_trend_report_bytes,
    generate_clutch_report_bytes,
)
from core.advanced_analytics import (
    classify_shot_zone,
    ClutchPerformance,
    LineupAnalytics,
    parse_time_to_seconds,
)

from flask import render_template, current_app

# Constants for lineup filtering
MIN_TOP_LINEUP_MINUTES = 10
MIN_TOP_LINEUP_SECONDS = MIN_TOP_LINEUP_MINUTES * 60


def _safe_ppp(points, possessions):
    return round(points / possessions, 3) if possessions else 0.0


def _seconds_to_minutes(seconds):
    return round((seconds or 0) / 60, 1)


def _meets_top_lineup_minutes(item):
    return (item.get("total_seconds") or 0) >= MIN_TOP_LINEUP_SECONDS


def _get_player_reb_conceded_summary(player_name, game_ids, session):
    lineup_total, tracked_games = (
        session.query(
            func.sum(PlayerLineupStats.reb_conceded),
            func.count(func.distinct(LineupSegment.game_id)),
        )
        .join(LineupSegment, PlayerLineupStats.lineup_segment_id == LineupSegment.id)
        .filter(PlayerLineupStats.player_name == player_name)
        .filter(LineupSegment.game_id.in_(game_ids))
        .one()
    )
    return {
        "total": int(lineup_total or 0),
        "tracked_games": int(tracked_games or 0),
    }


def _get_team_reb_conceded_summary(game_ids, session):
    lineup_total, tracked_games = (
        session.query(
            func.sum(LineupSegment.reb_conceded),
            func.count(func.distinct(LineupSegment.game_id)),
        )
        .filter(LineupSegment.game_id.in_(game_ids))
        .one()
    )
    return {
        "total": int(lineup_total or 0),
        "tracked_games": int(tracked_games or 0),
    }


def _normalize_zone(zone, x_loc=None, y_loc=None, shot_type=None):
    if zone:
        return zone
    if x_loc is None or y_loc is None:
        return "Unknown"
    return classify_shot_zone(x_loc, y_loc, shot_type or "2pt") or "Unknown"


def _team_event_points(event):
    if event.event_type in {"SHOT_2PT", "SHOT_3PT"} and event.shot_attempt == "made":
        return 3 if event.event_type == "SHOT_3PT" else 2
    if event.event_type == "FT_MADE":
        return 1
    return 0


def _player_event_points(event):
    if event.event_type in {"SHOT_2PT", "SHOT_3PT"} and event.shot_attempt == "made":
        return 3 if event.event_type == "SHOT_3PT" else 2
    if event.event_type == "FT_MADE":
        return 1
    return _parse_detail_points(event.detail)


def _opponent_event_points(event):
    if event.event_type == "OPP_SCORE":
        return _parse_detail_points(event.detail) or 2
    return 0


def _serialize_lineup_summary(item):
    fga = item["fga"]
    tpa = item["tpa"]
    fta = item["fta"]
    possessions = item["possessions"]
    games_played = len(item["games"])
    return {
        "name": item["name"],
        "players": item["players"],
        "teammates": item.get("teammates", []),
        "minutes": _seconds_to_minutes(item["total_seconds"]),
        "possessions": possessions,
        "points_scored": item["points_scored"],
        "points_allowed": item["points_allowed"],
        "ortg": round(calculate_ortg(item["points_scored"], possessions), 1)
        if possessions
        else 0.0,
        "drtg": round(calculate_ortg(item["points_allowed"], possessions), 1)
        if possessions
        else 0.0,
        "net_rating": round(
            ((item["points_scored"] - item["points_allowed"]) / possessions) * 100, 1
        )
        if possessions
        else 0.0,
        "segment_count": item["segment_count"],
        "games_played": games_played,
        "is_starting": item["is_starting"],
        "fgm": item["fgm"],
        "fga": fga,
        "fg_pct": safe_percentage(item["fgm"], fga),
        "tpm": item["tpm"],
        "tpa": tpa,
        "tp_pct": safe_percentage(item["tpm"], tpa),
        "ftm": item["ftm"],
        "fta": fta,
        "ft_pct": safe_percentage(item["ftm"], fta),
        "oreb": item["oreb"],
        "dreb": item["dreb"],
        "reb": item["oreb"] + item["dreb"],
        "ast": item["ast"],
        "stl": item["stl"],
        "blk": item["blk"],
        "tov": item["tov"],
        "reb_conceded": item["reb_conceded"],
    }


def _build_zone_summary(shots):
    if not shots:
        return {"available": False, "rows": [], "expected_available": False}

    expected_values = {z.zone_name: z.expected_value for z in ShotZone.query.all()}
    zone_map = defaultdict(lambda: {"attempts": 0, "makes": 0, "points": 0})

    for shot in shots:
        zone = _normalize_zone(shot.zone, shot.x_loc, shot.y_loc, shot.shot_type)
        zone_row = zone_map[zone]
        zone_row["attempts"] += 1
        zone_row["points"] += shot.points or 0
        if shot.result == "made":
            zone_row["makes"] += 1

    rows = []
    for zone, values in sorted(
        zone_map.items(), key=lambda item: item[1]["attempts"], reverse=True
    ):
        attempts = values["attempts"]
        makes = values["makes"]
        actual_pps = round(values["points"] / attempts, 2) if attempts else 0.0
        expected_value = expected_values.get(zone)
        rows.append(
            {
                "zone": zone,
                "attempts": attempts,
                "makes": makes,
                "fg_pct": safe_percentage(makes, attempts),
                "points": values["points"],
                "actual_pps": actual_pps,
                "expected_value": round(expected_value, 2)
                if expected_value is not None
                else None,
                "value_delta": round(actual_pps - expected_value, 2)
                if expected_value is not None
                else None,
            }
        )

    return {
        "available": True,
        "rows": rows,
        "expected_available": any(row["expected_value"] is not None for row in rows),
    }


def _build_play_summary(game_ids, player_name=None):
    shot_query = ShotEvent.query.join(Play, ShotEvent.play_id == Play.id).filter(
        ShotEvent.game_id.in_(game_ids),
        ShotEvent.play_id.isnot(None),
    )
    event_query = GameEvent.query.join(Play, GameEvent.play_id == Play.id).filter(
        GameEvent.game_id.in_(game_ids),
        GameEvent.play_id.isnot(None),
        GameEvent.event_type.in_(("SHOT_2PT", "SHOT_3PT", "TURNOVER")),
    )
    possession_query = Possession.query.join(
        Play, Possession.play_id == Play.id
    ).filter(
        Possession.game_id.in_(game_ids),
        Possession.play_id.isnot(None),
    )

    if player_name:
        shot_query = shot_query.filter(ShotEvent.player_name == player_name)
        event_query = event_query.filter(GameEvent.player_name == player_name)
        possession_rows = []
    else:
        possession_rows = possession_query.all()

    shot_rows = shot_query.all()
    event_rows = event_query.all()

    play_map = {}
    for shot in shot_rows:
        play = shot.play
        record = play_map.setdefault(
            play.id,
            {
                "play_name": play.name,
                "play_type": play.play_type,
                "attempts": 0,
                "makes": 0,
                "points": 0,
                "actions": 0,
                "possessions": 0,
                "turnovers": 0,
            },
        )
        record["attempts"] += 1
        record["actions"] += 1
        record["points"] += shot.points or 0
        if shot.result == "made":
            record["makes"] += 1

    for event in event_rows:
        play = event.play
        if play is None:
            continue
        record = play_map.setdefault(
            play.id,
            {
                "play_name": play.name,
                "play_type": play.play_type,
                "attempts": 0,
                "makes": 0,
                "points": 0,
                "actions": 0,
                "possessions": 0,
                "turnovers": 0,
            },
        )
        record["actions"] += 1
        if event.event_type == "TURNOVER":
            record["turnovers"] += 1

    for possession in possession_rows:
        play = possession.play
        if play is None:
            continue
        record = play_map.setdefault(
            play.id,
            {
                "play_name": play.name,
                "play_type": play.play_type,
                "attempts": 0,
                "makes": 0,
                "points": 0,
                "actions": 0,
                "possessions": 0,
                "turnovers": 0,
            },
        )
        record["possessions"] += 1
        if not player_name:
            record["points"] += possession.points or 0

    rows = []
    for record in play_map.values():
        denominator = record["possessions"] or (
            record["attempts"] + record["turnovers"]
        )
        rows.append(
            {
                **record,
                "fg_pct": safe_percentage(record["makes"], record["attempts"]),
                "ppp": _safe_ppp(record["points"], denominator),
            }
        )

    rows.sort(
        key=lambda row: (row["points"], row["attempts"], row["actions"]), reverse=True
    )
    efficient = [
        row
        for row in rows
        if (row["possessions"] or (row["attempts"] + row["turnovers"])) >= 2
    ]
    efficient.sort(key=lambda row: row["ppp"], reverse=True)

    return {
        "available": bool(rows),
        "top_volume": rows[:5],
        "top_efficiency": efficient[:5],
    }


def _build_player_box_detail(stats, games_played):
    session = db.session
    game_ids = [s.game_id for s in stats]
    player_name = stats[0].player_name if stats else None
    stat_reb_conceded = sum(s.reb_conceded or 0 for s in stats)
    lineup_reb_conceded = (
        _get_player_reb_conceded_summary(player_name, game_ids, session)
        if player_name and game_ids
        else {"total": 0, "tracked_games": 0}
    )
    reb_conceded_total = lineup_reb_conceded["total"] or stat_reb_conceded
    reb_conceded_games = lineup_reb_conceded["tracked_games"]
    if reb_conceded_games == 0 and stat_reb_conceded:
        reb_conceded_games = games_played

    pm_stats = [
        s
        for s in stats
        if AnalyticsService.supports_plus_minus(getattr(s, "game", None))
    ]
    total_plus_minus = sum((s.plus_minus or 0) for s in pm_stats)
    pm_games = len(pm_stats)
    return {
        "available": bool(stats),
        "totals": {
            "oreb": sum(s.oreb or 0 for s in stats),
            "dreb": sum(s.dreb or 0 for s in stats),
            "reb": sum(s.reb or 0 for s in stats),
            "pf": sum(s.pf or 0 for s in stats),
            "plus_minus": total_plus_minus if pm_stats else None,
            "reb_conceded": reb_conceded_total,
        },
        "per_game": {
            "oreb": round(sum(s.oreb or 0 for s in stats) / games_played, 1)
            if games_played
            else 0.0,
            "dreb": round(sum(s.dreb or 0 for s in stats) / games_played, 1)
            if games_played
            else 0.0,
            "reb": round(sum(s.reb or 0 for s in stats) / games_played, 1)
            if games_played
            else 0.0,
            "pf": round(sum(s.pf or 0 for s in stats) / games_played, 1)
            if games_played
            else 0.0,
            "plus_minus": round(total_plus_minus / len(pm_stats), 1)
            if pm_stats
            else None,
            "reb_conceded": round(reb_conceded_total / reb_conceded_games, 1)
            if reb_conceded_games
            else 0.0,
        },
        "tracked_plus_minus_games": pm_games,
        "has_live_plus_minus": bool(pm_stats),
        "tracked_reb_conceded_games": reb_conceded_games,
        "has_reb_conceded": bool(reb_conceded_games),
    }


def _build_player_lineup_context(player_name, game_ids, session):
    rows = (
        session.query(PlayerLineupStats, LineupSegment, Lineup)
        .join(LineupSegment, PlayerLineupStats.lineup_segment_id == LineupSegment.id)
        .outerjoin(Lineup, LineupSegment.lineup_id == Lineup.id)
        .filter(PlayerLineupStats.player_name == player_name)
        .filter(LineupSegment.game_id.in_(game_ids))
        .all()
    )

    if not rows:
        return {
            "available": False,
            "best_lineup": None,
            "worst_lineup": None,
            "most_used_lineups": [],
            "starting_units": [],
        }

    lineup_map = {}
    for player_stats, segment, lineup in rows:
        players = (
            list(lineup.players)
            if lineup and lineup.players
            else list(segment.players or [])
        )
        key = lineup.id if lineup else f"segment:{'|'.join(sorted(players))}"
        record = lineup_map.setdefault(
            key,
            {
                "name": lineup.display_name
                if lineup and lineup.display_name
                else " · ".join(players),
                "players": players,
                "teammates": [p for p in players if p != player_name],
                "total_seconds": 0,
                "possessions": 0,
                "points_scored": 0,
                "points_allowed": 0,
                "segment_count": 0,
                "games": set(),
                "is_starting": bool(lineup.is_starting) if lineup else False,
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
                "reb_conceded": 0,
            },
        )
        record["total_seconds"] += segment.duration_seconds or 0
        record["possessions"] += segment.possessions or 0
        record["points_scored"] += segment.points_scored or 0
        record["points_allowed"] += segment.points_allowed or 0
        record["segment_count"] += 1
        record["games"].add(segment.game_id)
        record["is_starting"] = (
            record["is_starting"] or bool(lineup.is_starting)
            if lineup
            else record["is_starting"]
        )
        for field in (
            "fgm",
            "fga",
            "tpm",
            "tpa",
            "ftm",
            "fta",
            "oreb",
            "dreb",
            "ast",
            "stl",
            "blk",
            "tov",
            "reb_conceded",
        ):
            record[field] += getattr(player_stats, field) or 0

    summary_records = list(lineup_map.values())
    summaries = [_serialize_lineup_summary(item) for item in summary_records]
    qualified_summaries = [
        _serialize_lineup_summary(item)
        for item in summary_records
        if _meets_top_lineup_minutes(item)
    ]
    best = (
        max(
            qualified_summaries,
            key=lambda item: (item["net_rating"], item["possessions"]),
        )
        if qualified_summaries
        else None
    )
    worst = (
        min(
            qualified_summaries,
            key=lambda item: (item["net_rating"], -item["possessions"]),
        )
        if qualified_summaries
        else None
    )
    most_used = sorted(summaries, key=lambda item: item["minutes"], reverse=True)[:3]
    starting = [item for item in most_used + summaries if item["is_starting"]]

    return {
        "available": True,
        "top_lineups_available": bool(qualified_summaries),
        "best_lineup": best,
        "worst_lineup": worst,
        "most_used_lineups": most_used,
        "starting_units": starting[:3],
    }


def _build_possession_summary(game_ids, events, team_stats):
    possessions = Possession.query.filter(Possession.game_id.in_(game_ids)).all()
    quarter_rows = []
    if possessions:
        quarter_map = defaultdict(
            lambda: {
                "team_possessions": 0,
                "opp_possessions": 0,
                "team_points": 0,
                "opp_points": 0,
            }
        )
        for possession in possessions:
            quarter = possession.quarter or 1
            bucket = quarter_map[quarter]
            if possession.team_possession:
                bucket["team_possessions"] += 1
                bucket["team_points"] += possession.points or 0
            else:
                bucket["opp_possessions"] += 1
                bucket["opp_points"] += possession.points or 0

        for quarter in sorted(quarter_map):
            bucket = quarter_map[quarter]
            quarter_rows.append(
                {
                    "quarter": quarter,
                    "team_possessions": bucket["team_possessions"],
                    "opp_possessions": bucket["opp_possessions"],
                    "team_points": bucket["team_points"],
                    "opp_points": bucket["opp_points"],
                    "team_ppp": _safe_ppp(
                        bucket["team_points"], bucket["team_possessions"]
                    ),
                    "opp_ppp": _safe_ppp(
                        bucket["opp_points"], bucket["opp_possessions"]
                    ),
                }
            )

        total_team_possessions = sum(row["team_possessions"] for row in quarter_rows)
        total_opp_possessions = sum(row["opp_possessions"] for row in quarter_rows)
        total_team_points = sum(row["team_points"] for row in quarter_rows)
        total_opp_points = sum(row["opp_points"] for row in quarter_rows)
        source = "tracked"
    else:
        total_team_possessions = int(
            round(
                sum(
                    calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
                    for s in team_stats
                )
            )
        )
        total_opp_possessions = total_team_possessions
        total_team_points = sum(s.points or 0 for s in team_stats)
        total_opp_points = sum(_opponent_event_points(event) for event in events)
        source = "estimated"

    clutch = {"plays": 0, "points": 0, "fgm": 0, "fga": 0, "tov": 0}
    for event in events:
        score_margin = event.score_margin if event.score_margin is not None else None
        if score_margin is None:
            continue
        if not ClutchPerformance.is_clutch_situation(
            score_margin, parse_time_to_seconds(event.time_remaining or "5:00")
        ):
            continue
        clutch["plays"] += 1
        clutch["points"] += _team_event_points(event)
        if event.event_type in {"SHOT_2PT", "SHOT_3PT"}:
            clutch["fga"] += 1
            if event.shot_attempt == "made":
                clutch["fgm"] += 1
        if event.event_type == "TURNOVER":
            clutch["tov"] += 1

    clutch["fg_pct"] = safe_percentage(clutch["fgm"], clutch["fga"])

    return {
        "available": True,
        "source": source,
        "quarter_rows": quarter_rows,
        "total_team_possessions": total_team_possessions,
        "total_opp_possessions": total_opp_possessions,
        "team_ppp": _safe_ppp(total_team_points, total_team_possessions),
        "opp_ppp": _safe_ppp(total_opp_points, total_opp_possessions),
        "clutch": clutch,
    }


def _build_player_possession_context(player_name, game_ids, stats):
    events = (
        GameEvent.query.filter(GameEvent.game_id.in_(game_ids))
        .order_by(GameEvent.game_id.asc(), GameEvent.timestamp.asc())
        .all()
    )
    summary = _build_possession_summary(game_ids, events, stats)
    player_events = [event for event in events if event.player_name == player_name]
    clutch = {"plays": 0, "points": 0, "fgm": 0, "fga": 0, "tov": 0}
    for event in player_events:
        score_margin = event.score_margin if event.score_margin is not None else None
        if score_margin is None:
            continue
        if not ClutchPerformance.is_clutch_situation(
            score_margin, parse_time_to_seconds(event.time_remaining or "5:00")
        ):
            continue
        clutch["plays"] += 1
        clutch["points"] += _player_event_points(event)
        if event.event_type in {"SHOT_2PT", "SHOT_3PT"}:
            clutch["fga"] += 1
            if event.shot_attempt == "made":
                clutch["fgm"] += 1
        if event.event_type == "TURNOVER":
            clutch["tov"] += 1
    clutch["fg_pct"] = safe_percentage(clutch["fgm"], clutch["fga"])
    summary["clutch"] = clutch
    return summary


def _build_player_shot_play_context(player_name, game_ids):
    shots = (
        ShotEvent.query.filter(ShotEvent.game_id.in_(game_ids))
        .filter(ShotEvent.player_name == player_name)
        .all()
    )
    return {
        "zone_summary": _build_zone_summary(shots),
        "play_summary": _build_play_summary(game_ids, player_name=player_name),
    }


def _build_team_box_detail(game_ids, games):
    stats = PlayerStat.query.filter(PlayerStat.game_id.in_(game_ids)).all()
    total_games = len(games)
    stat_reb_conceded = sum(s.reb_conceded or 0 for s in stats)
    lineup_reb_conceded = _get_team_reb_conceded_summary(game_ids, db.session)
    reb_conceded_total = lineup_reb_conceded["total"] or stat_reb_conceded
    reb_conceded_games = lineup_reb_conceded["tracked_games"]
    if reb_conceded_games == 0 and stat_reb_conceded:
        reb_conceded_games = total_games
    totals = {
        "oreb": sum(s.oreb or 0 for s in stats),
        "dreb": sum(s.dreb or 0 for s in stats),
        "reb": sum(s.reb or 0 for s in stats),
        "pf": sum(s.pf or 0 for s in stats),
        "reb_conceded": reb_conceded_total,
    }
    per_game = {
        "oreb": round(totals["oreb"] / total_games, 1) if total_games else 0.0,
        "dreb": round(totals["dreb"] / total_games, 1) if total_games else 0.0,
        "reb": round(totals["reb"] / total_games, 1) if total_games else 0.0,
        "pf": round(totals["pf"] / total_games, 1) if total_games else 0.0,
        "reb_conceded": round(reb_conceded_total / reb_conceded_games, 1)
        if reb_conceded_games
        else 0.0,
    }
    live_games = [game for game in games if AnalyticsService.supports_plus_minus(game)]
    live_ids = [game.id for game in live_games]
    total_plus_minus = 0
    if live_ids:
        total_plus_minus = (
            db.session.query(func.sum(PlayerStat.plus_minus))
            .filter(PlayerStat.game_id.in_(live_ids))
            .scalar()
            or 0
        )
    return {
        "available": bool(stats),
        "totals": totals,
        "per_game": per_game,
        "live_plus_minus_total": total_plus_minus if live_ids else None,
        "tracked_plus_minus_games": len(live_ids),
        "tracked_reb_conceded_games": reb_conceded_games,
        "plus_minus_leaders": AnalyticsService.calculate_plus_minus_leaders(
            games, db.session
        ),
    }


def _build_team_lineup_summary(game_ids, session):
    segment_rows = (
        session.query(LineupSegment, Lineup)
        .outerjoin(Lineup, LineupSegment.lineup_id == Lineup.id)
        .filter(LineupSegment.game_id.in_(game_ids))
        .all()
    )
    if not segment_rows:
        return {
            "available": False,
            "top_offensive": [],
            "top_defensive": [],
            "most_used": [],
            "starting_units": [],
        }

    lineup_map = {}
    for segment, lineup in segment_rows:
        players = (
            list(lineup.players)
            if lineup and lineup.players
            else list(segment.players or [])
        )
        key = lineup.id if lineup else f"segment:{'|'.join(sorted(players))}"
        record = lineup_map.setdefault(
            key,
            {
                "name": lineup.display_name
                if lineup and lineup.display_name
                else " · ".join(players),
                "players": players,
                "total_seconds": 0,
                "possessions": 0,
                "points_scored": 0,
                "points_allowed": 0,
                "segment_count": 0,
                "games": set(),
                "is_starting": bool(lineup.is_starting) if lineup else False,
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
                "reb_conceded": 0,
            },
        )
        record["total_seconds"] += segment.duration_seconds or 0
        record["possessions"] += segment.possessions or 0
        record["points_scored"] += segment.points_scored or 0
        record["points_allowed"] += segment.points_allowed or 0
        record["segment_count"] += 1
        record["games"].add(segment.game_id)

    player_rows = (
        session.query(PlayerLineupStats, LineupSegment)
        .join(LineupSegment, PlayerLineupStats.lineup_segment_id == LineupSegment.id)
        .filter(LineupSegment.game_id.in_(game_ids))
        .all()
    )
    for player_stats, segment in player_rows:
        players = list(segment.players or [])
        key = (
            segment.lineup_id
            if segment.lineup_id is not None
            else f"segment:{'|'.join(sorted(players))}"
        )
        if key not in lineup_map:
            continue
        record = lineup_map[key]
        for field in (
            "fgm",
            "fga",
            "tpm",
            "tpa",
            "ftm",
            "fta",
            "oreb",
            "dreb",
            "ast",
            "stl",
            "blk",
            "tov",
            "reb_conceded",
        ):
            record[field] += getattr(player_stats, field) or 0

    summary_records = [
        item
        for item in lineup_map.values()
        if item["possessions"] or item["total_seconds"]
    ]
    summaries = [_serialize_lineup_summary(item) for item in summary_records]
    qualified_summaries = [
        _serialize_lineup_summary(item)
        for item in summary_records
        if _meets_top_lineup_minutes(item)
    ]
    top_offensive = sorted(
        qualified_summaries,
        key=lambda item: (item["ortg"], item["possessions"]),
        reverse=True,
    )[:5]
    top_defensive = sorted(
        qualified_summaries, key=lambda item: (item["drtg"], -item["possessions"])
    )[:5]
    most_used = sorted(summaries, key=lambda item: item["minutes"], reverse=True)[:5]
    starting_units = [item for item in summaries if item["is_starting"]]
    starting_units = sorted(
        starting_units, key=lambda item: item["minutes"], reverse=True
    )[:5]

    return {
        "available": bool(summaries),
        "top_offensive": top_offensive,
        "top_defensive": top_defensive,
        "most_used": most_used,
        "starting_units": starting_units,
    }


def _build_team_report_context(game_type, games, game_ids):
    team_data = AnalyticsService.calculate_enhanced_team_metrics(
        games, game_ids, db.session
    )
    team_data["chart_trend"] = generate_team_scoring_trend(games)
    team_data["chart_shooting"] = generate_team_shot_chart(game_ids, db.session)

    team_stats = PlayerStat.query.filter(PlayerStat.game_id.in_(game_ids)).all()
    events = (
        GameEvent.query.filter(GameEvent.game_id.in_(game_ids))
        .order_by(GameEvent.game_id.asc(), GameEvent.timestamp.asc())
        .all()
    )
    shots = ShotEvent.query.filter(ShotEvent.game_id.in_(game_ids)).all()

    return {
        "game_type": game_type,
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        **team_data,
        "team_box_detail": _build_team_box_detail(game_ids, games),
        "lineup_summary": _build_team_lineup_summary(game_ids, db.session),
        "possession_summary": _build_possession_summary(game_ids, events, team_stats),
        "zone_summary": _build_zone_summary(shots),
        "play_summary": _build_play_summary(game_ids),
    }


def _parse_detail(detail):
    """Parse detail field which may be a digit string or dict-like string.

    Returns a dict with any of: points, quarter, play_id, play_name
    """
    result = {}
    if not detail:
        return result
    detail_str = str(detail).strip()

    if detail_str.isdigit():
        result["points"] = int(detail_str)
        return result

    if len(detail_str) >= 500:
        return result

    try:
        parsed = ast.literal_eval(detail_str)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, SyntaxError):
        pass

    return result


def _parse_detail_points(detail):
    """Parse points from detail field."""
    parsed = _parse_detail(detail)
    if "points" in parsed:
        return int(parsed["points"])
    return 0


def _build_quarter_map(events):
    """Build a mapping of event.id to quarter number by processing NEXT_QUARTER events."""
    quarter_map = {}
    sorted_events = sorted(events, key=lambda e: e.timestamp or 0)
    current_quarter = 1
    for event in sorted_events:
        if event.event_type == "NEXT_QUARTER":
            parsed = _parse_detail(event.detail)
            if "quarter" in parsed:
                current_quarter = int(parsed["quarter"])
            else:
                current_quarter += 1
        quarter_map[event.id] = current_quarter
    return quarter_map


def _get_shot_scoring_data(game_id):
    """Get scoring data using player_stats as authoritative source for totals.

    Uses shot_events for quarter distribution, but validates against player_stats.

    Returns:
        - total_points: sum of points from made shots + free throws
        - fgm: count of made field goals (from player_stats)
        - fga: count of all field goal attempts (from player_stats)
        - quarterly_points: dict mapping quarter -> points scored (FG + distributed FT)
        - quarterly_fgm: dict mapping quarter -> made field goals
        - quarterly_fga: dict mapping quarter -> field goal attempts
        - ft_points: total free throw points
        - fg_points: total field goal points
    """
    shot_events = ShotEvent.query.filter_by(game_id=game_id).all()
    player_stats = PlayerStat.query.filter_by(game_id=game_id).all()

    fgm = sum(ps.fgm or 0 for ps in player_stats)
    fga = sum(ps.fga or 0 for ps in player_stats)
    tpm = sum(ps.tpm or 0 for ps in player_stats)

    two_pm = fgm - tpm
    fg_points = two_pm * 2 + tpm * 3

    ft_points = sum(ps.ftm or 0 for ps in player_stats)

    total_points = fg_points + ft_points

    quarterly_fg_points = defaultdict(int)
    quarterly_fgm = defaultdict(int)
    quarterly_fga = defaultdict(int)

    for shot in shot_events:
        if shot.shot_type in ["2pt", "3pt"]:
            quarter = shot.quarter or 1
            quarterly_fga[quarter] += 1

            if shot.result == "made":
                quarterly_fg_points[quarter] += shot.points or 0
                quarterly_fgm[quarter] += 1

    shot_events_fg_total = sum(quarterly_fg_points.values())
    quarterly_points = defaultdict(int)

    if shot_events_fg_total > 0 and ft_points > 0:
        for quarter, q_fg_pts in quarterly_fg_points.items():
            ft_share = round((q_fg_pts / shot_events_fg_total) * ft_points)
            quarterly_points[quarter] = q_fg_pts + ft_share

        total_distributed = sum(quarterly_points.values())
        diff = total_points - total_distributed
        if diff != 0:
            max_q = max(quarterly_points.keys(), key=lambda q: quarterly_points[q])
            quarterly_points[max_q] += diff
    else:
        for quarter, q_fg_pts in quarterly_fg_points.items():
            quarterly_points[quarter] = q_fg_pts
        if ft_points > 0 and not quarterly_points:
            quarterly_points[1] = ft_points

    return {
        "total_points": total_points,
        "fgm": fgm,
        "fga": fga,
        "quarterly_points": dict(quarterly_points),
        "quarterly_fgm": dict(quarterly_fgm),
        "quarterly_fga": dict(quarterly_fga),
        "ft_points": ft_points,
        "fg_points": fg_points,
    }


def _get_opponent_box_score_from_events(game_id):
    """Build opponent box score from tracked OPP_SCORE and OPP_OREB events.

    Returns a TeamBox object with real opponent stats if events are tracked,
    otherwise returns None to signal that estimation should be used.
    """
    events = GameEvent.query.filter_by(game_id=game_id).all()

    opp_score_events = [e for e in events if e.event_type == "OPP_SCORE"]
    opp_oreb_events = [e for e in events if e.event_type == "OPP_OREB"]

    if not opp_score_events:
        return None

    opp_fgm = 0
    opp_fga = 0
    opp_tpm = 0
    opp_tpa = 0
    opp_ftm = 0
    opp_fta = 0
    opp_pts = 0

    for event in opp_score_events:
        try:
            detail = json.loads(event.detail) if event.detail else {}
        except (json.JSONDecodeError, TypeError):
            detail = {}

        shot_type = detail.get("shot_type", "2pt")
        result = detail.get("result", "made")
        points = detail.get("points", 0)

        if shot_type == "2pt":
            opp_fga += 1
            if result == "made":
                opp_fgm += 1
                opp_pts += points
        elif shot_type == "3pt":
            opp_fga += 1
            opp_tpa += 1
            if result == "made":
                opp_fgm += 1
                opp_tpm += 1
                opp_pts += points
        elif shot_type == "ft":
            fta = detail.get("fta", 1)
            ftm = detail.get("ftm", 0) if result == "made" else 0
            opp_fta += fta
            opp_ftm += ftm
            opp_pts += ftm

    opp_orb = len(opp_oreb_events)

    from core.models import PlayerStat

    team_stats = PlayerStat.query.filter_by(game_id=game_id).all()
    opp_drb = sum(s.oreb or 0 for s in team_stats)

    return TeamBox(
        pts=opp_pts,
        fgm=opp_fgm,
        fga=opp_fga,
        tpm=opp_tpm,
        tpa=opp_tpa,
        ftm=opp_ftm,
        fta=opp_fta,
        orb=opp_orb,
        drb=opp_drb,
        trb=opp_orb + opp_drb,
        ast=0,
        stl=0,
        blk=0,
        tov=0,
    )


def generate_game_pdf_bytes(game_id):
    """
    Generates the PDF bytes for a game summary.
    Returns (filename, pdf_bytes).
    """
    game = db.session.get(Game, game_id)
    if not game:
        return None, None

    stats = PlayerStat.query.filter_by(game_id=game_id).all()
    if not stats:
        return None, None

    events = (
        GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.timestamp).all()
    )
    time_progression = _build_time_progression(events, game)

    stats_with_metrics = AnalyticsService.calculate_game_stats(stats)

    for player in stats_with_metrics:
        player.shot_chart = generate_shot_chart(
            player.player_name, [game_id], db.session
        )

    top_performers = AnalyticsService.get_game_top_performers(stats_with_metrics)
    alerts = AnalyticsService.get_game_alerts(stats_with_metrics)
    team_aggregates = AnalyticsService.get_team_aggregates(stats_with_metrics)

    # Calculate game-wide possessions and ratings
    team_stats = {
        "points": sum(s.points for s in stats),
        "reb": sum(s.reb for s in stats),
        "ast": sum(s.ast for s in stats),
        "stl": sum(s.stl for s in stats),
        "blk": sum(s.blk for s in stats),
        "tov": sum(s.tov for s in stats),
        "pf": sum(s.pf for s in stats),
        "reb_conceded": sum(s.reb_conceded or 0 for s in stats),
        "fgm": sum(s.fgm for s in stats),
        "fga": sum(s.fga for s in stats),
        "tpm": sum(s.tpm for s in stats),
        "tpa": sum(s.tpa for s in stats),
        "ftm": sum(s.ftm for s in stats),
        "fta": sum(s.fta for s in stats),
        "oreb": sum(s.oreb for s in stats),
        "dreb": sum(s.dreb for s in stats),
        "two_pt_made": sum(s.fgm for s in stats) - sum(s.tpm for s in stats),
        "two_pt_att": sum(s.fga for s in stats) - sum(s.tpa for s in stats),
    }
    team_poss = calculate_possessions(
        team_stats["fga"], team_stats["fta"], team_stats["oreb"], team_stats["tov"]
    )

    # Use true tracked possessions if available for consistency with lineup stats
    from core.models import LineupSegment

    segment_poss = (
        db.session.query(func.sum(LineupSegment.possessions))
        .filter_by(game_id=game_id)
        .scalar()
        or 0
    )
    if segment_poss > 0:
        team_poss = float(segment_poss)
    team_poss = max(team_poss, 1.0)

    team_aggregates["ortg"] = calculate_ortg(game.team_score, team_poss)
    team_aggregates["drtg"] = calculate_ortg(game.opponent_score, team_poss)
    team_aggregates["eff"] = sum(s.eff for s in stats_with_metrics)
    team_aggregates["efg_pct"] = calculate_efg_percent(
        team_stats["fgm"], team_stats["tpm"], team_stats["fga"]
    )

    try:
        top_lineups_off = LineupAnalytics.get_game_lineup_rankings(
            game_id,
            top_n=3,
            rank_by="offensive",
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
        )
        top_lineups_def = LineupAnalytics.get_game_lineup_rankings(
            game_id,
            top_n=3,
            rank_by="defensive",
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
        )
    except Exception:
        top_lineups_off = []
        top_lineups_def = []

    try:
        top_duos_off = LineupAnalytics.get_combination_net_differentials(
            combination_type="duo",
            game_ids=[game_id],
            min_possessions=10,
            top_n=3,
            require_positive=False,
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
            rank_by="offensive",
        )
        top_duos_def = LineupAnalytics.get_combination_net_differentials(
            combination_type="duo",
            game_ids=[game_id],
            min_possessions=10,
            top_n=3,
            require_positive=False,
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
            rank_by="defensive",
        )
    except Exception:
        top_duos_off = []
        top_duos_def = []

    try:
        top_trios_off = LineupAnalytics.get_combination_net_differentials(
            combination_type="trio",
            game_ids=[game_id],
            min_possessions=10,
            top_n=3,
            require_positive=False,
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
            rank_by="offensive",
        )
        top_trios_def = LineupAnalytics.get_combination_net_differentials(
            combination_type="trio",
            game_ids=[game_id],
            min_possessions=10,
            top_n=3,
            require_positive=False,
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
            rank_by="defensive",
        )
    except Exception:
        top_trios_off = []
        top_trios_def = []

    shot_events = ShotEvent.query.filter_by(game_id=game_id).first()
    shot_chart = generate_team_shot_chart([game_id], db.session) if shot_events else ""

    plays_data = get_summary_play_stats(game_id, play_type="Offense")
    plays_players_data = get_summary_play_player_stats(game_id, play_type="Offense")
    players_plays_data = get_summary_player_play_stats(game_id, play_type="Offense")
    untracked = get_untracked_percentages(game_id) or {}

    player_top_plays = get_summary_player_top_plays_by_points(game_id, limit=3)

    for player in stats_with_metrics:
        top_plays = player_top_plays.get(player.player_name, [])
        player.top_3_plays = [
            {"points": play["points"], "play_name": play["name"]} for play in top_plays
        ]

    html = render_template(
        "game_summary_pdf.html",
        game=game,
        stats=stats_with_metrics,
        top_performers=top_performers,
        alerts=alerts,
        team_stats=team_stats,
        team_aggregates=team_aggregates,
        shot_chart=shot_chart,
        plays_data=plays_data,
        plays_players_data=plays_players_data,
        players_plays_data=players_plays_data,
        untracked=untracked,
        time_progression=time_progression,
        top_lineups_off=top_lineups_off,
        top_lineups_def=top_lineups_def,
        top_duos_off=top_duos_off,
        top_duos_def=top_duos_def,
        top_trios_off=top_trios_off,
        top_trios_def=top_trios_def,
        generated_date=datetime.now().strftime("%B %d, %Y"),
    )

    pdf_doc = HTML(string=html)
    pdf_bytes = pdf_doc.write_pdf()
    filename = f"game_{game.opponent}_{game.date}.pdf"

    return filename, pdf_bytes


def generate_simple_game_pdf_bytes(game_id):
    """
    Generate a simple game stats PDF containing only game info,
    basic team stats, and player stats tables (no extra analysis).
    Returns (filename, pdf_bytes).
    """
    game = db.session.get(Game, game_id)
    if not game:
        return None, None

    stats = PlayerStat.query.filter_by(game_id=game_id).all()
    if not stats:
        return None, None

    stats_with_metrics = AnalyticsService.calculate_game_stats(stats)

    team_stats = {
        "points": sum(s.points for s in stats),
        "reb": sum(s.reb for s in stats),
        "ast": sum(s.ast for s in stats),
        "stl": sum(s.stl for s in stats),
        "blk": sum(s.blk for s in stats),
        "tov": sum(s.tov for s in stats),
        "pf": sum(s.pf for s in stats),
        "fgm": sum(s.fgm for s in stats),
        "fga": sum(s.fga for s in stats),
        "tpm": sum(s.tpm for s in stats),
        "tpa": sum(s.tpa for s in stats),
        "ftm": sum(s.ftm for s in stats),
        "fta": sum(s.fta for s in stats),
        "oreb": sum(s.oreb for s in stats),
        "dreb": sum(s.dreb for s in stats),
        "two_pt_made": sum(s.fgm for s in stats) - sum(s.tpm for s in stats),
        "two_pt_att": sum(s.fga for s in stats) - sum(s.tpa for s in stats),
    }

    team_aggregates = {
        "fg_pct": calculate_efg_percent(
            team_stats["fgm"], team_stats["tpm"], team_stats["fga"]
        ),
        "tp_pct": safe_percentage(team_stats["tpm"], team_stats["tpa"]),
        "ft_pct": safe_percentage(team_stats["ftm"], team_stats["fta"]),
        "two_pt_pct": safe_percentage(
            team_stats["two_pt_made"], team_stats["two_pt_att"]
        ),
        "reb": team_stats["reb"],
        "ast": team_stats["ast"],
    }

    html = render_template(
        "simple_game_stats_pdf.html",
        game=game,
        stats=stats_with_metrics,
        team_stats=team_aggregates,
        generated_date=datetime.now().strftime("%B %d, %Y"),
    )

    pdf_doc = HTML(string=html)
    pdf_bytes = pdf_doc.write_pdf()
    filename = f"game_simple_{game.opponent}_{game.date}.pdf"

    return filename, pdf_bytes


def generate_player_quarter_pdf_bytes(player_name: str, game_type: str = "ALL", game_id: int = None, team_id: int = None):
    """
    Generates PDF bytes for the player quarter-by-quarter detail page.
    Returns (filename, pdf_bytes) or (None, None) on failure.
    """
    try:
        context = AnalyticsService.build_player_game_detail(player_name, game_type, game_id=game_id, team_id=team_id)

        html = render_template(
            "player_game_detail.html",
            **context,
            pdf_mode=True,
            report_url="",
            back_url="",
        )

        pdf_bytes = HTML(string=html).write_pdf()

        filename = f"{player_name.replace(' ', '_')}_quarter_detail_{game_type}.pdf"
        return filename, pdf_bytes
    except Exception as e:
        current_app.logger.error(
            f"Failed to generate player quarter PDF for {player_name}: {e}"
        )
        return None, None


def _build_quarterly_stats(events, game):
    """Build quarterly scoring breakdown from GameEvent data."""
    quarterly = {
        "team": {"q1": 0, "q2": 0, "q3": 0, "q4": 0, "ot": 0},
        "opponent": {"q1": 0, "q2": 0, "q3": 0, "q4": 0, "ot": 0},
    }

    shot_data = _get_shot_scoring_data(game.id)
    for quarter, points in shot_data["quarterly_points"].items():
        quarter_key = f"q{quarter}" if quarter <= 4 else "ot"
        if quarter_key in quarterly["team"]:
            quarterly["team"][quarter_key] = points

    quarter_map = _build_quarter_map(events)
    for event in events:
        if event.event_type == "OPP_SCORE":
            quarter = quarter_map.get(event.id, event.quarter or 1)
            quarter_key = f"q{quarter}" if quarter <= 4 else "ot"
            points = _parse_detail_points(event.detail)
            if quarter_key in quarterly["opponent"]:
                quarterly["opponent"][quarter_key] += points

    return quarterly


def _parse_time_remaining(time_str):
    """Parse MM:SS format to total seconds remaining in quarter."""
    if not time_str:
        return 600
    parts = time_str.split(":")
    if len(parts) != 2:
        return 600
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
        return minutes * 60 + seconds
    except (ValueError, IndexError):
        return 600


def _event_team_points(event):
    """Return team points contributed by a single event, if any."""
    if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
        return 2
    if event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
        return 3
    if event.event_type == "FT_MADE":
        return 1
    if event.event_type == "FT":
        detail = _parse_detail(event.detail)
        if "ftm" in detail:
            return int(detail.get("ftm", 0) or 0)
        return 1 if event.shot_attempt == "made" else 0
    return 0


def _get_starting_lineup_from_events(events):
    """Extract starting lineup from first 5 SUB_IN events in Q1 (by lowest timestamp)."""
    quarter_map = _build_quarter_map(events)
    q1_sub_ins = []
    for event in events:
        quarter = quarter_map.get(event.id, event.quarter or 1)
        if event.event_type == "SUB_IN" and quarter == 1 and event.player_name:
            q1_sub_ins.append((event.timestamp or 0, event.player_name))
    q1_sub_ins.sort(key=lambda x: x[0])
    if q1_sub_ins:
        return [name for _, name in q1_sub_ins[:5]]
    sub_ins = [
        (e.timestamp or 0, e.player_name)
        for e in events
        if e.event_type == "SUB_IN" and e.player_name
    ]
    sub_ins.sort(key=lambda x: x[0])
    return [name for _, name in sub_ins[:5]]


def _get_starting_lineup_from_segments(game_id):
    """Get starting lineup from first LineupSegment of the game."""
    from core.models import LineupSegment

    segment = (
        LineupSegment.query.filter_by(game_id=game_id)
        .order_by(LineupSegment.start_timestamp.asc())
        .first()
    )
    if segment and segment.players:
        return segment.players
    return []


def _build_time_progression(events, game):
    """Build time progression data structure for game summary.

    Uses score_margin from OPP_SCORE events to reconstruct accurate score timeline.
    Falls back to proportional distribution if score_margin is unavailable.
    """
    quarter_map = _build_quarter_map(events)
    shot_data = _get_shot_scoring_data(game.id)

    score_progression = []
    quarterly_stats = defaultdict(
        lambda: {"pts": 0, "tov": 0, "pf": 0, "fgm": 0, "fga": 0}
    )
    for q, pts in shot_data["quarterly_points"].items():
        quarterly_stats[q]["pts"] = pts
    for q, fgm in shot_data["quarterly_fgm"].items():
        quarterly_stats[q]["fgm"] = fgm
    for q, fga in shot_data["quarterly_fga"].items():
        quarterly_stats[q]["fga"] = fga

    runs = []

    opp_score = 0
    team_score = 0
    current_run = {
        "team": None,
        "points": 0,
        "start_q": None,
        "end_q": None,
        "start_time": None,
        "start_lineup": [],
    }
    lead_changes = 0
    max_lead = {"team": 0, "opp": 0, "lineup_team": [], "lineup_opp": []}
    prev_margin = 0
    prev_lead_holder = None

    on_court = set()
    lineup_snapshots = {
        "start": [],
        "runs": [],
        "max_lead": [],
        "max_deficit": [],
        "clutch": [],
    }

    starting_lineup = _get_starting_lineup_from_events(events)
    if not starting_lineup:
        starting_lineup = _get_starting_lineup_from_segments(game.id)
    lineup_snapshots["start"] = starting_lineup
    for player in starting_lineup:
        on_court.add(player)

    final_team_score = game.team_score or 0
    final_opp_score = game.opponent_score or 0

    opp_score_events = []
    for event in events:
        if event.event_type == "OPP_SCORE":
            opp_score_events.append(event)

    total_opp_points = sum(_parse_detail_points(e.detail) for e in opp_score_events)

    opp_score = 0
    team_score = 0

    sorted_events = sorted(events, key=lambda e: e.game_seconds or e.timestamp or 0)

    for event in sorted_events:
        quarter = quarter_map.get(event.id, event.quarter or 1)
        time_str = event.time_remaining or "10:00"
        total_seconds = _parse_time_remaining(time_str)
        points_scored = 0
        scoring_team = None

        if event.event_type == "SUB_IN":
            if event.player_name:
                on_court.add(event.player_name)
        elif event.event_type == "SUB_OUT":
            if event.player_name and event.player_name in on_court:
                on_court.discard(event.player_name)

        if event.event_type == "OPP_SCORE":
            detail = _parse_detail(event.detail)
            points_scored = detail.get("points", _parse_detail_points(event.detail))

            opp_score += points_scored
            scoring_team = "opp"

            if event.score_margin is not None:
                margin = event.score_margin
                team_score = opp_score + margin
            else:
                margin = team_score - opp_score

        team_points = _event_team_points(event)
        if team_points > 0:
            team_score += team_points
            points_scored = team_points
            scoring_team = "team"

        if event.event_type == "TURNOVER":
            quarterly_stats[quarter]["tov"] += 1
        if event.event_type in ("FOUL", "FOUL_PERSONAL"):
            quarterly_stats[quarter]["pf"] += 1

        if scoring_team:
            margin = team_score - opp_score

            score_progression.append(
                {
                    "timestamp": event.timestamp,
                    "game_seconds": event.game_seconds,
                    "time_remaining": time_str,
                    "quarter": quarter,
                    "team_score": team_score,
                    "opp_score": opp_score,
                    "margin": margin,
                    "lineup": list(on_court),
                }
            )

            if margin > max_lead["team"]:
                max_lead["team"] = margin
                max_lead["lineup_team"] = list(on_court)
            if -margin > max_lead["opp"]:
                max_lead["opp"] = -margin
                max_lead["lineup_opp"] = list(on_court)

            if quarter == 4 and total_seconds <= 120 and abs(margin) <= 5:
                lineup_snapshots["clutch"] = list(on_court)
            elif quarter > 4 and abs(margin) <= 5:
                lineup_snapshots["clutch"] = list(on_court)

            current_lead_holder = (
                "team" if margin > 0 else ("opp" if margin < 0 else None)
            )
            if prev_lead_holder is not None and current_lead_holder is not None:
                if prev_lead_holder != current_lead_holder:
                    lead_changes += 1
            prev_lead_holder = current_lead_holder

            if current_run["team"] == scoring_team:
                current_run["points"] += points_scored
                current_run["end_q"] = quarter
            else:
                if current_run["points"] >= 5:
                    runs.append(
                        {
                            "type": current_run["team"],
                            "points": current_run["points"],
                            "start_q": current_run["start_q"],
                            "end_q": current_run["end_q"] or current_run["start_q"],
                            "start_time": current_run["start_time"],
                            "lineup": current_run["start_lineup"],
                        }
                    )
                    lineup_snapshots["runs"].append(
                        {
                            "run_index": len(runs) - 1,
                            "players": current_run["start_lineup"],
                        }
                    )
                current_run = {
                    "team": scoring_team,
                    "points": points_scored,
                    "start_q": quarter,
                    "end_q": quarter,
                    "start_time": time_str,
                    "start_lineup": list(on_court),
                }

            prev_margin = margin

    if current_run["points"] >= 5:
        runs.append(
            {
                "type": current_run["team"],
                "points": current_run["points"],
                "start_q": current_run["start_q"],
                "end_q": current_run["end_q"] or current_run["start_q"],
                "start_time": current_run["start_time"],
                "lineup": current_run["start_lineup"],
            }
        )
        lineup_snapshots["runs"].append(
            {
                "run_index": len(runs) - 1,
                "players": current_run["start_lineup"],
            }
        )

    lineup_snapshots["max_lead"] = max_lead["lineup_team"]
    lineup_snapshots["max_deficit"] = max_lead["lineup_opp"]

    return {
        "score_progression": score_progression,
        "quarterly_stats": dict(quarterly_stats),
        "runs": runs,
        "lead_changes": lead_changes,
        "max_lead": max_lead,
        "lineup_snapshots": lineup_snapshots,
        "starting_lineup": starting_lineup,
    }


def _generate_player_report_data(
    player_name, games, game_ids, game_type, team_avg_override=None, db_session=None
):
    """Internal helper to gather all data for a player report"""
    session = db_session or db.session
    stats = (
        session.query(PlayerStat)
        .filter(PlayerStat.player_name == player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .all()
    )

    if not stats:
        raise ValueError("No stats for player")

    game_map = {g.id: g for g in games}
    stats_with_dates = [(s, game_map.get(s.game_id)) for s in stats]
    stats_with_dates.sort(key=lambda x: x[1].sort_date if x[1] else "")
    stats = [s[0] for s in stats_with_dates]

    report_data = AnalyticsService.calculate_player_metrics(stats, game_map, len(stats))

    team_avg = team_avg_override or AnalyticsService.calculate_team_averages(
        game_ids, session
    )
    team_rankings = AnalyticsService.calculate_team_rankings(
        player_name, game_ids, report_data, session
    )

    charts = generate_player_charts(stats, game_map, player_name, db_session=session)
    shot_chart = generate_shot_chart(player_name, game_ids, session)
    box_detail = _build_player_box_detail(stats, len(stats))
    lineup_context = _build_player_lineup_context(player_name, game_ids, session)
    possession_context = _build_player_possession_context(player_name, game_ids, stats)
    shot_play_context = _build_player_shot_play_context(player_name, game_ids)

    return {
        "player_name": player_name,
        "game_type": game_type,
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        "team_avg": team_avg,
        "team_rankings": team_rankings,
        "shot_chart": shot_chart,
        "box_detail": box_detail,
        "lineup_context": lineup_context,
        "possession_context": possession_context,
        "shot_play_context": shot_play_context,
        **report_data,
        **charts,
    }
