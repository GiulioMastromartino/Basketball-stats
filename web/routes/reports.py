import ast
import zipfile
from collections import defaultdict
from io import BytesIO
from datetime import datetime
from sqlalchemy import func
from flask import Blueprint, jsonify, render_template, request, send_file
from flask_login import login_required
from weasyprint import HTML

from core.models import Game, PlayerStat, ShotEvent, GameEvent, SystemSetting, db
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
from core.utils import calculate_efg_percent, calculate_ortg, calculate_possessions, safe_percentage
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
)

reports_bp = Blueprint("reports", __name__)

VALID_GAME_TYPES = {"ALL", "Season", "Friendly"}
MAX_PLAYERS_IN_ZIP = 50


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
    import json
    from core.models import GameEvent
    from core.advanced_game_report import TeamBox

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
    game = Game.query.get(game_id)
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
    segment_poss = db.session.query(func.sum(LineupSegment.possessions)).filter_by(game_id=game_id).scalar() or 0
    if segment_poss > 0:
        team_poss = float(segment_poss)
    elif team_poss <= 0:
        team_poss = 1.0  # Avoid division by zero

    team_aggregates["ortg"] = calculate_ortg(game.team_score, team_poss)
    team_aggregates["drtg"] = calculate_ortg(game.opponent_score, team_poss)
    team_aggregates["eff"] = sum(s.eff for s in stats_with_metrics)
    team_aggregates["efg_pct"] = calculate_efg_percent(
        team_stats["fgm"], team_stats["tpm"], team_stats["fga"]
    )

    try:
        top_lineups_off = LineupAnalytics.get_game_lineup_rankings(
            game_id, top_n=3, rank_by="offensive",
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss
        )
        top_lineups_def = LineupAnalytics.get_game_lineup_rankings(
            game_id, top_n=3, rank_by="defensive",
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss
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
            rank_by="offensive"
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
            rank_by="defensive"
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
            rank_by="offensive"
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
            rank_by="defensive"
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


@reports_bp.route("/games/<int:game_id>/summary.pdf")
@login_required
def game_summary_pdf(game_id):
    """Generate full game summary PDF"""
    filename, pdf_bytes = generate_game_pdf_bytes(game_id)

    if not pdf_bytes:
        return jsonify({"error": "No stats for this game or game not found"}), 404

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/games/<int:game_id>/advanced_summary.pdf")
@login_required
def advanced_game_summary_pdf(game_id):
    """Generate advanced game summary PDF using new backend module"""
    game = Game.query.get_or_404(game_id)
    stats = PlayerStat.query.filter_by(game_id=game_id).all()

    if not stats:
        return jsonify({"error": "No stats for this game"}), 404

    team_name = SystemSetting.get_value("team_name", "LX")

    team_box = TeamBox(
        pts=sum(s.points for s in stats),
        fgm=sum(s.fgm for s in stats),
        fga=sum(s.fga for s in stats),
        tpm=sum(s.tpm for s in stats),
        tpa=sum(s.tpa for s in stats),
        ftm=sum(s.ftm for s in stats),
        fta=sum(s.fta for s in stats),
        orb=sum(s.oreb for s in stats),
        drb=sum(s.dreb for s in stats),
        trb=sum(s.oreb + s.dreb for s in stats),
        ast=sum(s.ast for s in stats),
        stl=sum(s.stl for s in stats),
        blk=sum(s.blk for s in stats),
        tov=sum(s.tov for s in stats),
    )

    team_poss = team_box.fga + 0.44 * team_box.fta - team_box.orb + team_box.tov
    opp_pts = game.opponent_score

    opp_box = _get_opponent_box_score_from_events(game_id)

    if opp_box is None:
        opp_score_events = GameEvent.query.filter_by(
            game_id=game_id, event_type="OPP_SCORE"
        ).all()

        if opp_score_events:
            opp_fga = 0
            opp_fgm = 0
            opp_tpm = 0
            opp_tpa = 0
            opp_ftm = 0
            opp_fta = 0
            opp_orb = 0
            opp_drb = team_box.orb
            opp_trb = opp_orb + opp_drb
            opp_ast = 0
            opp_stl = team_box.tov
            opp_blk = 0
            opp_tov = 0

            opp_box = TeamBox(
                pts=opp_pts,
                fgm=opp_fgm,
                fga=opp_fga,
                tpm=opp_tpm,
                tpa=opp_tpa,
                ftm=opp_ftm,
                fta=opp_fta,
                orb=opp_orb,
                drb=opp_drb,
                trb=opp_trb,
                ast=opp_ast,
                stl=opp_stl,
                blk=opp_blk,
                tov=opp_tov,
            )
        else:
            opp_fga_est = int(team_poss * 0.6)
            opp_fta_est = int(opp_fga_est * 0.25)

            opp_box = TeamBox(
                pts=opp_pts,
                fgm=0,
                fga=opp_fga_est,
                tpm=0,
                tpa=0,
                ftm=0,
                fta=opp_fta_est,
                orb=0,
                drb=team_box.orb,
                trb=team_box.orb,
                ast=0,
                stl=0,
                blk=0,
                tov=int(team_poss * 0.15),
            )

    opp_poss = calculate_possessions(opp_box.fga, opp_box.fta, opp_box.orb, opp_box.tov)
    pace = (team_poss + opp_poss) / 2 if (team_poss + opp_poss) > 0 else team_poss

    players = [
        PlayerBox(
            name=s.player_name,
            minutes=float(s.minutes.split(":")[0])
            if isinstance(s.minutes, str) and ":" in s.minutes
            else float(s.minutes or 0),
            pts=s.points,
            fgm=s.fgm,
            fga=s.fga,
            tpm=s.tpm,
            tpa=s.tpa,
            ftm=s.ftm,
            fta=s.fta,
            orb=s.oreb,
            drb=s.dreb,
            trb=s.oreb + s.dreb,
            ast=s.ast,
            stl=s.stl,
            blk=s.blk,
            tov=s.tov,
        )
        for s in stats
    ]

    shot_events = ShotEvent.query.filter_by(game_id=game_id).all()
    team_shots = [
        {"x": s.x_loc, "y": s.y_loc, "made": s.result == "made"}
        for s in shot_events
        if s.x_loc is not None and s.y_loc is not None
    ]

    zone_stats = defaultdict(lambda: {"makes": 0, "attempts": 0, "points": 0})
    for s in shot_events:
        if s.x_loc is not None and s.y_loc is not None:
            zone = classify_shot_zone(s.x_loc, s.y_loc, s.shot_type or "2pt")
            zone_stats[zone]["attempts"] += 1
            zone_stats[zone]["points"] += s.points or 0
            if s.result == "made":
                zone_stats[zone]["makes"] += 1

    events = (
        GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.timestamp).all()
    )

    quarterly_stats = _build_quarterly_stats(events, game)

    clutch_stats = ClutchPerformance.get_clutch_stats(game_id)

    game_meta = {
        "date": game.date,
        "location": "",
        "competition": game.game_type or "",
        "team_name": team_name,
        "opp_name": game.opponent,
        "team_points": team_box.pts,
        "opp_points": opp_pts,
        "generated_at": datetime.now().strftime("%B %d, %Y"),
    }

    team_minutes_total = 200.0

    report = build_advanced_game_report(
        game=game_meta,
        team_box=team_box,
        opp_box=opp_box,
        players=players,
        team_minutes_total=team_minutes_total,
        team_shots=team_shots,
        opp_shots=[],
    )

    html = render_template(
        "game_summary_advanced_pdf.html",
        game=game_meta,
        report=report,
        zone_stats=dict(zone_stats),
        quarterly_stats=quarterly_stats,
        clutch_stats=clutch_stats,
    )

    return _render_pdf(html, f"advanced_report_{game.opponent}_{game.date}.pdf")


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

    for event in events:
        if event.event_type == "OPP_SCORE":
            quarter = _build_quarter_map(events).get(event.id, event.quarter or 1)
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


@reports_bp.route("/team/report.pdf")
@login_required
def team_report_pdf():
    """Generate enhanced team-level PDF report"""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)

    if not games:
        return jsonify({"error": "No games for selected filter"}), 404

    team_data = AnalyticsService.calculate_enhanced_team_metrics(
        games, game_ids, db.session
    )

    team_data["chart_trend"] = generate_team_scoring_trend(games)
    team_data["chart_shooting"] = generate_team_shot_chart(game_ids, db.session)

    html = render_template(
        "team_report_pdf.html",
        game_type=game_type,
        generated_date=datetime.now().strftime("%B %d, %Y"),
        **team_data,
    )

    return _render_pdf(html, f"Team_Report_{game_type}.pdf")


@reports_bp.route("/player/<player_name>/report.pdf")
@login_required
def player_report_pdf(player_name):
    """Generate multi-page PDF report for a player"""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)

    if not games:
        return jsonify({"error": "No games"}), 404

    try:
        context = _generate_player_report_data(player_name, games, game_ids, game_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    html = render_template("player_report_pdf.html", **context)
    return _render_pdf(html, f"{player_name.replace(' ', '_')}_report_{game_type}.pdf")


@reports_bp.route("/download-all", strict_slashes=False)
# @login_required
def download_all_reports():
    """Generate ZIP with all player reports sequentially to stay under 500MB RAM"""
    import time
    import gc
    import psutil
    import os

    current_app.logger.info("Starting memory-optimized bulk player report download...")
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)

    if not games:
        return jsonify({"error": "No games"}), 404

    players = (
        db.session.query(PlayerStat.player_name)
        .distinct()
        .order_by(PlayerStat.player_name)
        .limit(MAX_PLAYERS_IN_ZIP)
        .all()
    )
    player_names = [p[0] for p in players]
    
    team_avg = AnalyticsService.calculate_team_averages(game_ids, db.session)
    zip_buffer = BytesIO()

    process = psutil.Process(os.getpid())
    
    def get_mem():
        return process.memory_info().rss / 1024 / 1024

    results = []
    current_app.logger.info(f"Processing {len(player_names)} players sequentially. Initial Mem: {get_mem():.1f}MB")

    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            success_count = 0
            
            for i, player_name in enumerate(player_names):
                player_start_time = time.time()
                try:
                    # Clear memory before starting each player
                    gc.collect()
                    
                    context = _generate_player_report_data(
                        player_name,
                        games,
                        game_ids,
                        game_type,
                        team_avg_override=team_avg
                    )
                    html = render_template("player_report_pdf.html", **context)
                    
                    pdf_doc = HTML(string=html)
                    pdf_data = pdf_doc.write_pdf()
                    
                    if pdf_data:
                        filename = f"{player_name.replace(' ', '_')}_report_{game_type}.pdf"
                        zipf.writestr(filename, pdf_data)
                        success_count += 1
                    
                    duration = time.time() - player_start_time
                    current_app.logger.info(
                        f"[{i+1}/{len(player_names)}] {player_name}: {duration:.2f}s | Mem: {get_mem():.1f}MB"
                    )
                    
                    # Force cleanup after each report
                    del context
                    del html
                    del pdf_doc
                    del pdf_data
                    
                except Exception as e:
                    current_app.logger.error(f"Failed report for {player_name}: {e}")
                    continue

            if success_count == 0:
                return jsonify({"error": "Failed to generate any reports"}), 500

        zip_buffer.seek(0)
        current_app.logger.info(f"Bulk download complete. Final Mem: {get_mem():.1f}MB")
        
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"all_player_reports_{game_type}.zip",
        )
    except Exception as e:
        current_app.logger.error(f"Bulk download critical failure: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _get_game_type():
    game_type = request.args.get("game_type", "ALL")
    return game_type if game_type in VALID_GAME_TYPES else "ALL"


def _get_games(game_type):
    query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")
    games = query.all()
    return games, [g.id for g in games]


def _render_pdf(html, filename):
    html_doc = HTML(string=html)
    pdf_bytes = html_doc.write_pdf()
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


def _generate_player_report_data(
    player_name, games, game_ids, game_type, team_avg_override=None, db_session=None
):
    """Internal helper to gather all data for a player report"""
    session = db_session or db.session
    stats = (
        session.query(PlayerStat).filter(PlayerStat.player_name == player_name)
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

    return {
        "player_name": player_name,
        "game_type": game_type,
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        "team_avg": team_avg,
        "team_rankings": team_rankings,
        "shot_chart": shot_chart,
        **report_data,
        **charts,
    }


@reports_bp.route("/games/<int:game_id>/visual.pdf")
@login_required
def visual_game_report_pdf(game_id):
    """Generate visual game report with score worm, quarterly flow, four factors."""
    filename, pdf_bytes = generate_visual_game_report_bytes(game_id)

    if not pdf_bytes:
        return jsonify({"error": "Could not generate visual report"}), 404

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/lineup/report.pdf")
@login_required
def lineup_report_pdf():
    """Generate lineup analysis report with top lineups, duo matrix."""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)

    filename, pdf_bytes = generate_lineup_report_bytes(
        game_ids=game_ids if game_type != "ALL" else None, min_possessions=5
    )

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/player/<player_name>/scouting.pdf")
@login_required
def player_scouting_card_pdf(player_name):
    """Generate player scouting card with shot chart and hot zones."""
    game_type = request.args.get("game_type", "ALL")

    filename, pdf_bytes = generate_player_scouting_card_bytes(player_name, game_type)

    if not pdf_bytes:
        return jsonify({"error": "No data for player"}), 404

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/season/trends.pdf")
@login_required
def season_trend_report_pdf():
    """Generate season trend report with rolling averages."""
    game_type = request.args.get("game_type", "Season")
    player_name = request.args.get("player", None)

    filename, pdf_bytes = generate_season_trend_report_bytes(player_name, game_type)

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/clutch/report.pdf")
@login_required
def clutch_report_pdf():
    """Generate clutch time performance report."""
    game_type = request.args.get("game_type", "Season")

    filename, pdf_bytes = generate_clutch_report_bytes(game_type)

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/live/halftime-pdf", methods=["POST"])
@login_required
def live_halftime_pdf():
    """
    Generate half-time summary PDF from live game data.

    Accepts JSON payload with current game state and generates a PDF
    without requiring the game to be saved to the database.

    Expected payload:
    {
        "opponent": "Team Name",
        "date": "2024-01-15",
        "team_score": 45,
        "opp_score": 42,
        "player_stats": {
            "Player1": {points, fgm, fga, tpm, tpa, ftm, fta, oreb, dreb, ast, stl, blk, tov, pf, minutes, plus_minus},
            ...
        },
        "game_events": [...],  # For Q1/Q2 filtering
        "schema_version": 4
    }
    """
    from flask import request
    from weasyprint import HTML
    from io import BytesIO
    from flask import send_file
    from datetime import datetime

    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    opponent = data.get("opponent", "Unknown")
    date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    team_score = data.get("team_score", 0)
    opp_score = data.get("opp_score", 0)
    player_stats_raw = data.get("player_stats", {})
    game_events = data.get("game_events", [])
    schema_version = data.get("schema_version", 1)

    def format_seconds_to_minutes(total_seconds):
        total_seconds = int(total_seconds or 0)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    stats = []
    for player_name, p_data in player_stats_raw.items():
        fgm = p_data.get("fgm", 0)
        fga = p_data.get("fga", 0)
        tpm = p_data.get("tpm", 0)
        tpa = p_data.get("tpa", 0)
        ftm = p_data.get("ftm", 0)
        fta = p_data.get("fta", 0)
        oreb = p_data.get("oreb", 0)
        dreb = p_data.get("dreb", 0)
        points = p_data.get("points", 0)
        ast = p_data.get("ast", 0)
        stl = p_data.get("stl", 0)
        blk = p_data.get("blk", 0)
        tov = p_data.get("tov", 0)
        pf = p_data.get("pf", 0)
        minutes = p_data.get("minutes", "00:00")
        plus_minus = p_data.get("plus_minus", 0)
        quarter_minutes = p_data.get("quarter_minutes", {}) or {}
        q1_minutes_seconds = quarter_minutes.get("1", quarter_minutes.get(1, 0))
        q2_minutes_seconds = quarter_minutes.get("2", quarter_minutes.get(2, 0))

        two_pt_made = max(0, fgm - tpm)
        two_pt_att = max(0, fga - tpa)

        fg_pct = (fgm / fga * 100) if fga > 0 else 0
        tp_pct = (tpm / tpa * 100) if tpa > 0 else 0
        ft_pct = (ftm / fta * 100) if fta > 0 else 0
        two_pt_pct = (two_pt_made / two_pt_att * 100) if two_pt_att > 0 else 0
        efg_pct = ((fgm + 0.5 * tpm) / fga * 100) if fga > 0 else 0

        eff = (
            points + (oreb + dreb) + ast + stl + blk - ((fga - fgm) + (fta - ftm) + tov)
        )

        stats.append(
            {
                "player_name": player_name,
                "minutes": minutes,
                "q1_minutes": format_seconds_to_minutes(q1_minutes_seconds),
                "q2_minutes": format_seconds_to_minutes(q2_minutes_seconds),
                "points": points,
                "reb": oreb + dreb,
                "oreb": oreb,
                "dreb": dreb,
                "ast": ast,
                "stl": stl,
                "blk": blk,
                "tov": tov,
                "pf": pf,
                "fgm": fgm,
                "fga": fga,
                "fg_percent": fg_pct,
                "tpm": tpm,
                "tpa": tpa,
                "tp_percent": tp_pct,
                "ftm": ftm,
                "fta": fta,
                "ft_percent": ft_pct,
                "two_pt_made": two_pt_made,
                "two_pt_att": two_pt_att,
                "two_pt_pct": two_pt_pct,
                "efg_pct": efg_pct,
                "plus_minus": plus_minus,
                "eff": eff,
            }
        )

    stats.sort(key=lambda x: x["points"], reverse=True)

    top_performers = {}
    if stats:
        top_performers["points"] = max(stats, key=lambda x: x["points"])
        top_performers["efficiency"] = max(stats, key=lambda x: x["eff"])
        top_performers["rebounds"] = max(stats, key=lambda x: x["reb"])

    total_fgm = sum(s["fgm"] for s in stats)
    total_fga = sum(s["fga"] for s in stats)
    total_tpm = sum(s["tpm"] for s in stats)
    total_tpa = sum(s["tpa"] for s in stats)
    total_ftm = sum(s["ftm"] for s in stats)
    total_fta = sum(s["fta"] for s in stats)
    total_two_pt_made = sum(s["two_pt_made"] for s in stats)
    total_two_pt_att = sum(s["two_pt_att"] for s in stats)

    team_aggregates = {
        "fg_pct": (total_fgm / total_fga * 100) if total_fga > 0 else 0,
        "tp_pct": (total_tpm / total_tpa * 100) if total_tpa > 0 else 0,
        "ft_pct": (total_ftm / total_fta * 100) if total_fta > 0 else 0,
        "two_pt_pct": (total_two_pt_made / total_two_pt_att * 100)
        if total_two_pt_att > 0
        else 0,
    }

    quarterly_stats = {
        "1": {"pts": 0, "fgm": 0, "fga": 0, "tov": 0, "pf": 0},
        "2": {"pts": 0, "fgm": 0, "fga": 0, "tov": 0, "pf": 0},
    }

    for event in game_events:
        quarter = str(event.get("quarter", 1))
        if quarter not in ["1", "2"]:
            continue

        event_type = event.get("type", "")
        detail = event.get("detail", {})

        # Parse detail if it's a string
        if isinstance(detail, str):
            try:
                import ast

                detail = ast.literal_eval(detail) if detail else {}
            except:
                detail = {}

        if not isinstance(detail, dict):
            detail = {}

        # Handle shot events
        if event_type == "SHOT_2PT":
            quarterly_stats[quarter]["fga"] += 1
            shot_result = event.get("shot_attempt", "")
            if shot_result == "made":
                quarterly_stats[quarter]["fgm"] += 1
                quarterly_stats[quarter]["pts"] += 2

        elif event_type == "SHOT_3PT":
            quarterly_stats[quarter]["fga"] += 1
            shot_result = event.get("shot_attempt", "")
            if shot_result == "made":
                quarterly_stats[quarter]["fgm"] += 1
                quarterly_stats[quarter]["pts"] += 3

        elif event_type == "FT":
            # Free throws - points from detail
            ftm = detail.get("ftm", 0)
            quarterly_stats[quarter]["pts"] += ftm

        elif event_type == "TURNOVER":
            quarterly_stats[quarter]["tov"] += 1

        # Track personal fouls from detail or dedicated event
        pf_inc = detail.get("pf", 0)
        if pf_inc:
            quarterly_stats[quarter]["pf"] += pf_inc

        # Also check for FOUL event type
        if event_type == "FOUL":
            quarterly_stats[quarter]["pf"] += 1

    html = render_template(
        "halftime_summary_pdf.html",
        opponent=opponent,
        date=date,
        team_score=team_score,
        opp_score=opp_score,
        stats=stats,
        top_performers=top_performers,
        team_aggregates=team_aggregates,
        quarterly_stats=quarterly_stats,
        generated_date=datetime.now().strftime("%B %d, %Y at %H:%M"),
        schema_version=schema_version,
        is_live=True,
    )

    pdf_doc = HTML(string=html)
    pdf_bytes = pdf_doc.write_pdf()

    filename = f"halftime_{opponent}_{date}.pdf"
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/games/<int:game_id>/evolution.pdf")
@login_required
def game_evolution_pdf(game_id: int):
    """Generate game evolution PDF showing stats over time.

    This report includes:
    - Score progression (score worm)
    - Team efficiency metrics over time
    - Player stat evolution
    - Scoring runs and lead changes
    - Quarter-by-quarter breakdown
    - Clutch time analysis (if applicable)

    Args:
        game_id: The game ID to generate the report for

    Returns:
        PDF file download
    """
    try:
        game = Game.query.get(game_id)
        if game is None:
            raise ValueError(f"Game with id {game_id} not found")

        if (game.schema_version or 0) >= 4:
            report = Schema4EvolutionReportService.build_report(game_id)
        else:
            report = EvolutionReportService.build_report(game_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    html = render_template(
        "game_evolution_pdf.html",
        report=report,
        generated_date=datetime.now().strftime("%B %d, %Y at %H:%M"),
    )

    return _render_pdf(html, f"evolution_{report.opponent}_{report.date}.pdf")
