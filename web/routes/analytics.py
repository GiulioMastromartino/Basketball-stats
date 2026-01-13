import matplotlib

matplotlib.use("Agg")  # Non-GUI backend
import base64
import statistics
from io import BytesIO
import zipfile
import tempfile
import os
import atexit
import shutil
from datetime import datetime
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from flask import Blueprint, jsonify, render_template, request, send_file, after_this_request, url_for
from flask_login import login_required
from sqlalchemy import desc, func

# Standard WeasyPrint import - monkeypatch removed
from weasyprint import HTML

from core.models import Game, PlayerStat, ShotEvent, db
from core.play_analytics import (
    get_play_stats,
    get_play_player_stats,
    get_player_play_stats,
    get_untracked_percentages,
)
from core.utils import (
    FT_ATTEMPT_WEIGHT,
    THREE_POINT_WEIGHT,
    calculate_efficiency,
    calculate_efg_percent,
    calculate_ortg,
    calculate_per_100_minutes,
    calculate_possessions,
    calculate_ppp,
    calculate_ts_percent,
    calculate_two_point_stats,
    parse_minutes,
    safe_percentage,
    get_player_stats_averages,
    normalize_per_100_possessions
)

analytics_bp = Blueprint("analytics", __name__)

# Constants
MIN_FGA_PER_GAME = 4.0
MIN_3PA_PER_GAME = 1.0
MIN_FTA_PER_GAME = 1.0
VALID_GAME_TYPES = {"ALL", "Season", "Friendly"}

# Track temp directories for cleanup
_temp_dirs = []

def cleanup_temp_dirs():
    """Clean up any remaining temp directories on exit"""
    for temp_dir in _temp_dirs:
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass

atexit.register(cleanup_temp_dirs)


@analytics_bp.route("/analytics")
@login_required
def dashboard():
    """Analytics dashboard page"""
    players = (
        db.session.query(PlayerStat.player_name)
        .distinct()
        .order_by(PlayerStat.player_name)
        .all()
    )
    player_names = [p[0] for p in players]
    return render_template("analytics.html", players=player_names)


@analytics_bp.route("/api/analytics/team_overview")
@login_required
def get_team_overview():
    """API for Team Overview with Weighted Top Performers"""
    # Validate inputs
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    try:
        limit_trend = int(request.args.get("limit_trend", 0))
        if limit_trend < 0:
            limit_trend = 0
    except ValueError:
        limit_trend = 0

    top_stat = request.args.get("top_stat", "efficiency")

    try:
        top_limit = int(request.args.get("top_limit", 3))
        if top_limit < 0:
            top_limit = 3
    except ValueError:
        top_limit = 3

    # Build game query
    query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    trend_games = games[-limit_trend:] if limit_trend > 0 else games
    wins = sum(1 for g in games if g.result == "W")
    total = len(games)
    ppg = round(sum(g.team_score for g in games) / total, 1) if total > 0 else 0

    # Get top performers
    games_for_top = games[-top_limit:] if top_limit > 0 else games
    game_ids = [g.id for g in games_for_top]
    num_games = len(game_ids) if game_ids else 1

    if not game_ids:
        return jsonify(
            {
                "trend": {"labels": [], "team_score": [], "opp_score": []},
                "metrics": {"win_pct": 0, "ppg": 0},
                "top_chart": {"labels": [], "data": [], "label": ""},
            }
        )

    # Handle Percentage Stats
    if top_stat in ["fg_pct", "3p_pct", "ft_pct", "ts_pct", "efg_pct"]:
        if top_stat == "fg_pct":
            numerator = func.sum(PlayerStat.fgm) * 100
            denominator = func.sum(PlayerStat.fga)
            threshold = MIN_FGA_PER_GAME * num_games
        elif top_stat == "3p_pct":
            numerator = func.sum(PlayerStat.tpm) * 100
            denominator = func.sum(PlayerStat.tpa)
            threshold = MIN_3PA_PER_GAME * num_games
        elif top_stat == "ft_pct":
            numerator = func.sum(PlayerStat.ftm) * 100
            denominator = func.sum(PlayerStat.fta)
            threshold = MIN_FTA_PER_GAME * num_games
        elif top_stat == "ts_pct":
            numerator = func.sum(PlayerStat.points) * 100
            denominator = 2 * (
                func.sum(PlayerStat.fga)
                + (FT_ATTEMPT_WEIGHT * func.sum(PlayerStat.fta))
            )
            threshold = MIN_FGA_PER_GAME * num_games
        elif top_stat == "efg_pct":
            numerator = (
                func.sum(PlayerStat.fgm) + THREE_POINT_WEIGHT * func.sum(PlayerStat.tpm)
            ) * 100
            denominator = func.sum(PlayerStat.fga)
            threshold = MIN_FGA_PER_GAME * num_games

        results = (
            db.session.query(
                PlayerStat.player_name,
                (numerator / func.nullif(denominator, 0)).label("agg_pct"),
                denominator.label("attempts"),
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .group_by(PlayerStat.player_name)
            .having(denominator >= threshold)
            .order_by(desc("agg_pct"))
            .limit(5)
            .all()
        )

        top_labels = [r[0] for r in results]
        top_values = [round(r[1] or 0, 1) for r in results]

    else:
        # Handle Counting Stats
        if top_stat == "efficiency":
            stat_expr = (
                PlayerStat.points
                + PlayerStat.reb
                + PlayerStat.ast
                + PlayerStat.stl
                + PlayerStat.blk
            ) - (
                (PlayerStat.fga - PlayerStat.fgm)
                + (PlayerStat.fta - PlayerStat.ftm)
                + PlayerStat.tov
            )
        elif top_stat == "points":
            stat_expr = PlayerStat.points
        elif top_stat == "rebounds":
            stat_expr = PlayerStat.reb
        elif top_stat == "assists":
            stat_expr = PlayerStat.ast
        elif top_stat == "steals":
            stat_expr = PlayerStat.stl
        elif top_stat == "blocks":
            stat_expr = PlayerStat.blk
        elif top_stat == "turnovers":
            stat_expr = PlayerStat.tov
        else:
            stat_expr = PlayerStat.points

        results = (
            db.session.query(
                PlayerStat.player_name, func.avg(stat_expr).label("avg_val")
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .group_by(PlayerStat.player_name)
            .order_by(desc(func.avg(stat_expr)))
            .limit(5)
            .all()
        )

        top_labels = [r[0] for r in results]
        top_values = [round(r[1] or 0, 1) for r in results]

    return jsonify(
        {
            "trend": {
                "labels": [g.date for g in trend_games],
                "team_score": [g.team_score for g in trend_games],
                "opp_score": [g.opponent_score for g in trend_games],
            },
            "metrics": {
                "win_pct": round(wins / total * 100, 1) if total > 0 else 0,
                "ppg": ppg,
            },
            "top_chart": {
                "labels": top_labels,
                "data": top_values,
                "label": f"Top {top_stat.replace('_', ' ').upper()}",
            },
        }
    )


@analytics_bp.route("/api/analytics/multi_compare")
@login_required
def multi_compare():
    """API for Multi-Player Comparison"""
    selected_players = request.args.getlist("players")
    selected_stats = request.args.getlist("stats")
    include_ma = request.args.get("ma") == "true"

    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    if not selected_players:
        return jsonify({"error": "No players", "datasets": []})

    query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")
    filtered_games = query.all()
    all_dates = [g.date for g in filtered_games]

    datasets = []

    for player in selected_players:
        stat_query = (
            db.session.query(PlayerStat, Game)
            .join(Game)
            .filter(PlayerStat.player_name == player)
            .filter(PlayerStat.minutes != "00:00")
            .order_by(Game.sort_date.asc())
        )

        if game_type == "Season":
            stat_query = stat_query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            stat_query = stat_query.filter(Game.game_type == "Friendly")

        stats = stat_query.all()
        stat_map = {s[1].date: s[0] for s in stats}

        for metric in selected_stats:
            values = []
            valid_values = []

            for date in all_dates:
                p_stat = stat_map.get(date)

                if not p_stat:
                    values.append(None)
                    continue

                val = 0

                # Basic stats
                if metric == "points":
                    val = p_stat.points
                elif metric == "rebounds":
                    val = p_stat.reb
                elif metric == "assists":
                    val = p_stat.ast
                elif metric == "steals":
                    val = p_stat.stl
                elif metric == "blocks":
                    val = p_stat.blk
                elif metric == "turnovers":
                    val = p_stat.tov
                elif metric == "fouls":
                    val = p_stat.pf
                elif metric == "fg_pct":
                    val = p_stat.fg_percent * 100
                elif metric == "3p_pct":
                    val = p_stat.tp_percent * 100
                elif metric == "ft_pct":
                    val = p_stat.ft_percent * 100

                # Advanced stats
                elif metric == "efficiency":
                    val = (
                        p_stat.points
                        + p_stat.reb
                        + p_stat.ast
                        + p_stat.stl
                        + p_stat.blk
                    ) - (
                        (p_stat.fga - p_stat.fgm)
                        + (p_stat.fta - p_stat.ftm)
                        + p_stat.tov
                    )
                elif metric == "ortg":
                    poss = calculate_possessions(
                        p_stat.fga, p_stat.fta, p_stat.oreb, p_stat.tov
                    )
                    val = calculate_ortg(p_stat.points, poss)
                elif metric == "ppp":
                    poss = calculate_possessions(
                        p_stat.fga, p_stat.fta, p_stat.oreb, p_stat.tov
                    )
                    val = calculate_ppp(p_stat.points, poss)
                elif metric == "ts_pct":
                    denom = 2 * (p_stat.fga + (FT_ATTEMPT_WEIGHT * p_stat.fta))
                    val = (p_stat.points * 100) / denom if denom > 0 else 0
                elif metric == "efg_pct":
                    val = (
                        (
                            (p_stat.fgm + THREE_POINT_WEIGHT * p_stat.tpm)
                            / p_stat.fga
                            * 100
                        )
                        if p_stat.fga > 0
                        else 0
                    )
                elif metric == "ast_tov":
                    val = p_stat.ast / p_stat.tov if p_stat.tov > 0 else p_stat.ast
                elif metric == "minutes":
                    val = parse_minutes(p_stat.minutes)
                elif metric == "usg_pct":
                    poss = calculate_possessions(
                        p_stat.fga, p_stat.fta, p_stat.oreb, p_stat.tov
                    )
                    val = poss

                # Rebounding
                elif metric == "oreb":
                    val = p_stat.oreb
                elif metric == "dreb":
                    val = p_stat.dreb
                elif metric == "oreb_pct":
                    val = (p_stat.oreb / p_stat.reb * 100) if p_stat.reb > 0 else 0

                # Shooting breakdown
                elif metric == "2pt_pct":
                    two_pt_att = p_stat.fga - p_stat.tpa
                    two_pt_made = p_stat.fgm - p_stat.tpm
                    val = (two_pt_made / two_pt_att * 100) if two_pt_att > 0 else 0
                elif metric == "fta_pct":
                    val = (p_stat.fta / p_stat.fga * 100) if p_stat.fga > 0 else 0

                values.append(val)
                valid_values.append(val)

            datasets.append(
                {
                    "label": f"{player} ({metric.upper()})",
                    "data": values,
                    "tension": 0.2,
                    "fill": False,
                    "spanGaps": True,
                }
            )

            # Moving average
            if include_ma and len(valid_values) > 0:
                full_ma_values = []
                valid_mas = []
                window_size = 3

                for i in range(len(valid_values)):
                    if i < window_size - 1:
                        valid_mas.append(None)
                    else:
                        window = valid_values[i - (window_size - 1) : i + 1]
                        valid_mas.append(sum(window) / window_size)

                v_idx = 0
                for v in values:
                    if v is None:
                        full_ma_values.append(None)
                    else:
                        full_ma_values.append(valid_mas[v_idx])
                        v_idx += 1

                datasets.append(
                    {
                        "label": f"{player} (3-Game MA)",
                        "data": full_ma_values,
                        "borderDash": [5, 5],
                        "pointRadius": 0,
                        "spanGaps": True,
                    }
                )

    return jsonify({"labels": all_dates, "datasets": datasets})


@analytics_bp.route("/api/analytics/player_progression")
@login_required
def player_progression():
    """API for individual player progression charts"""
    player_name = request.args.get("player")
    game_type = request.args.get("game_type", "ALL")

    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    if not player_name:
        return jsonify({"error": "No player specified"})

    # Get games
    query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    # Get player stats
    stats = (
        db.session.query(PlayerStat, Game)
        .join(Game)
        .filter(PlayerStat.player_name == player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .order_by(Game.sort_date.asc())
        .all()
    )

    if not stats:
        return jsonify({"error": "No data"})

    # Calculate progression data
    dates = []
    ppg_data = []
    ortg_data = []
    ts_pct_data = []
    fg_pct_data = []

    ppg_values = []

    for stat, game in stats:
        dates.append(game.date)
        ppg_values.append(stat.points)
        ppg_data.append(stat.points)

        poss = calculate_possessions(stat.fga, stat.fta, stat.oreb, stat.tov)
        ortg_data.append(calculate_ortg(stat.points, poss))

        denom_ts = 2 * (stat.fga + FT_ATTEMPT_WEIGHT * stat.fta)
        ts_pct_data.append((stat.points / denom_ts * 100) if denom_ts > 0 else 0)

        fg_pct_data.append(stat.fg_percent * 100)

    # Calculate season averages
    season_avg_ppg = statistics.mean(ppg_values) if ppg_values else 0

    return jsonify(
        {
            "dates": dates,
            "ppg": ppg_data,
            "ortg": ortg_data,
            "ts_pct": ts_pct_data,
            "fg_pct": fg_pct_data,
            "season_avg_ppg": round(season_avg_ppg, 1),
        }
    )


@analytics_bp.route("/api/analytics/consistency_leaderboard")
@login_required
def consistency_leaderboard():
    """API for consistency rankings"""
    game_type = request.args.get("game_type", "ALL")

    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    # Get games
    query = Game.query.order_by(Game.sort_date.desc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    if not game_ids:
        return jsonify({"consistent": [], "volatile": []})

    # Get all players
    players = (
        db.session.query(PlayerStat.player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .distinct()
        .all()
    )

    consistency_data = []

    for (player_name,) in players:
        stats = (
            PlayerStat.query.filter(PlayerStat.player_name == player_name)
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .all()
        )

        if len(stats) < 3:  # Need minimum games for consistency
            continue

        ppg_values = [s.points for s in stats]

        if ppg_values:
            std_dev = statistics.stdev(ppg_values) if len(ppg_values) > 1 else 0
            mean_ppg = statistics.mean(ppg_values)
            cv = (std_dev / mean_ppg) if mean_ppg > 0 else 0

            consistency_data.append(
                {
                    "player": player_name,
                    "cv": round(cv, 3),
                    "ppg": round(mean_ppg, 1),
                    "games": len(stats),
                }
            )

    # Sort
    consistency_data.sort(key=lambda x: x["cv"])

    consistent = consistency_data[:5]
    volatile = sorted(consistency_data, key=lambda x: x["cv"], reverse=True)[:5]

    return jsonify({"consistent": consistent, "volatile": volatile})


@analytics_bp.route("/api/analytics/shooting_breakdown")
@login_required
def shooting_breakdown():
    """API for team shooting breakdown per game"""
    game_id = request.args.get("game_id", type=int)

    if not game_id:
        return jsonify({"error": "No game specified"})

    stats = PlayerStat.query.filter_by(game_id=game_id).all()

    if not stats:
        return jsonify({"error": "No data"})

    # Aggregate team shooting
    total_fgm = sum(s.fgm for s in stats)
    total_fga = sum(s.fga for s in stats)
    total_tpm = sum(s.tpm for s in stats)
    total_tpa = sum(s.tpa for s in stats)
    total_ftm = sum(s.ftm for s in stats)
    total_fta = sum(s.fta for s in stats)
    total_pts = sum(s.points for s in stats)

    # Calculate percentages
    fg_pct = (total_fgm / total_fga * 100) if total_fga > 0 else 0
    tp_pct = (total_tpm / total_tpa * 100) if total_tpa > 0 else 0
    ft_pct = (total_ftm / total_fta * 100) if total_fta > 0 else 0

    # 2PT breakdown
    two_pt_att = total_fga - total_tpa
    two_pt_made = total_fgm - total_tpm
    two_pt_pct = (two_pt_made / two_pt_att * 100) if two_pt_att > 0 else 0

    # TS%
    denom_ts = 2 * (total_fga + FT_ATTEMPT_WEIGHT * total_fta)
    ts_pct = (total_pts / denom_ts * 100) if denom_ts > 0 else 0

    # eFG%
    efg_pct = (
        ((total_fgm + THREE_POINT_WEIGHT * total_tpm) / total_fga * 100)
        if total_fga > 0
        else 0
    )

    return jsonify(
        {
            "fg": {"made": total_fgm, "att": total_fga, "pct": round(fg_pct, 1)},
            "two_pt": {
                "made": two_pt_made,
                "att": two_pt_att,
                "pct": round(two_pt_pct, 1),
            },
            "three_pt": {"made": total_tpm, "att": total_tpa, "pct": round(tp_pct, 1)},
            "ft": {"made": total_ftm, "att": total_fta, "pct": round(ft_pct, 1)},
            "ts_pct": round(ts_pct, 1),
            "efg_pct": round(efg_pct, 1),
        }
    )


@analytics_bp.route("/api/analytics/role_analysis")
@login_required
def role_analysis():
    """API for role-based player classification"""
    game_type = request.args.get("game_type", "ALL")

    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    # Get games
    query = Game.query.order_by(Game.sort_date.desc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    if not game_ids:
        return jsonify({"players": []})

    # Get all players
    players = (
        db.session.query(PlayerStat.player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .distinct()
        .all()
    )

    player_roles = []

    for (player_name,) in players:
        stats = (
            PlayerStat.query.filter(PlayerStat.player_name == player_name)
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .all()
        )

        if not stats:
            continue

        # Calculate averages
        total_poss = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in stats
        )
        total_pts = sum(s.points for s in stats)
        avg_poss = total_poss / len(stats)

        ortg = calculate_ortg(total_pts, total_poss)

        # Classify role
        if avg_poss > 6 and ortg > 150:
            role = "Primary Scorer"
        elif avg_poss <= 6 and ortg > 150:
            role = "Efficient Role"
        elif avg_poss > 6 and ortg <= 150:
            role = "Volume Scorer"
        else:
            role = "Reserve"

        player_roles.append(
            {
                "player": player_name,
                "usg": round(avg_poss, 1),
                "ortg": round(ortg, 0),
                "role": role,
                "ppg": round(total_pts / len(stats), 1),
            }
        )

    return jsonify({"players": player_roles})


@analytics_bp.route("/games/<int:game_id>/summary.pdf")
@login_required
def game_summary_pdf(game_id):
    """Generate full game summary PDF with box score, stats, and analysis"""
    game = Game.query.get_or_404(game_id)
    stats = PlayerStat.query.filter_by(game_id=game_id).all()
    
    if not stats:
        return jsonify({"error": "No stats for this game"}), 404
    
    # Enrich stats with calculated metrics
    stats_with_metrics = _calculate_game_stats(stats)
    
    # Generate top performers & alerts
    top_performers = _get_game_top_performers(stats_with_metrics)
    alerts = _get_game_alerts(stats_with_metrics)
    
    # Team aggregates
    team_aggregates = _get_team_aggregates(stats_with_metrics)

    # --- Shot chart + plays (offense) ---
    shot_events = ShotEvent.query.filter_by(game_id=game_id).all()
    shot_chart = _generate_team_shot_chart([game_id]) if shot_events else ""

    plays_data = get_play_stats(game_id, play_type="Offense")
    plays_players_data = get_play_player_stats(game_id, play_type="Offense")
    players_plays_data = get_player_play_stats(game_id, play_type="Offense")
    untracked = get_untracked_percentages(game_id) or {}
    
    # Render HTML template
    html = render_template(
        "game_summary_pdf.html",
        game=game,
        stats=stats_with_metrics,
        top_performers=top_performers,
        alerts=alerts,
        team_aggregates=team_aggregates,
        shot_chart=shot_chart,
        plays_data=plays_data,
        plays_players_data=plays_players_data,
        players_plays_data=players_plays_data,
        untracked=untracked,
        generated_date=datetime.now().strftime("%B %d, %Y")
    )
    
    # Convert to PDF
    html_doc = HTML(string=html)
    pdf_bytes = html_doc.write_pdf()
    
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)
    
    filename = f"game_{game.opponent}_{game.date}.pdf"
    return send_file(pdf_io, mimetype="application/pdf", 
                     as_attachment=True, download_name=filename)


@analytics_bp.route("/team/report.pdf")
@login_required
def team_report_pdf():
    """
    Generate enhanced team-level PDF report
    """
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    # Build game query
    game_query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        game_query = game_query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        game_query = game_query.filter(Game.game_type == "Friendly")

    games = game_query.all()
    if not games:
        return jsonify({"error": "No games for selected filter"}), 404

    game_ids = [g.id for g in games]

    # Calculate enhanced team statistics
    team_data = _calculate_enhanced_team_metrics(games, game_ids)

    # Get current date
    generated_date = datetime.now().strftime("%B %d, %Y")

    # Render HTML
    html = render_template(
        "team_report_pdf.html",
        game_type=game_type,
        generated_date=generated_date,
        **team_data,
    )

    # Convert to PDF
    html_doc = HTML(string=html)
    pdf_bytes = html_doc.write_pdf()
    
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    filename = f"Team_Report_{game_type}.pdf"
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@analytics_bp.route("/player/<player_name>/report.pdf")
@login_required
def player_report_pdf(player_name):
    """
    Generate a multi-page PDF report with:
    - Page 1: Summary & Season Totals with +/
    - Page 2: Per-Game & Per-100 Stats  
    - Page 3: Shooting Breakdown with Shot Chart
    - Page 4: Advanced Metrics with Team Rankings
    - Page 5-6: Performance Charts with 3-Game MA
    - Page 7+: Game-by-Game Log with +/
    
    NOTE: Plus/Minus from CSV-imported games is EXCLUDED from calculations
    """
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    # Build game query
    game_query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        game_query = game_query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        game_query = game_query.filter(Game.game_type == "Friendly")

    games = game_query.all()
    if not games:
        return jsonify({"error": "No games for selected filter"}), 404

    game_ids = [g.id for g in games]

    # Get player stats
    stats = (
        PlayerStat.query.filter(PlayerStat.player_name == player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .all()
    )

    if not stats:
        return jsonify({"error": "No stats for this player"}), 404

    # Sort stats by game date
    game_map = {g.id: g for g in games}
    stats_with_dates = [(s, game_map.get(s.game_id)) for s in stats]
    stats_with_dates.sort(key=lambda x: x[1].sort_date if x[1] else "")
    stats = [s[0] for s in stats_with_dates]

    # Calculate all metrics
    report_data = _calculate_player_metrics(stats, game_map, games_played=len(stats))

    # Calculate team averages and rankings
    team_avg = _calculate_team_averages(game_ids)
    team_rankings = _calculate_team_rankings(player_name, game_ids, report_data)

    # Generate charts
    charts = _generate_player_charts(stats, game_map, player_name)
    
    # Generate shot chart
    shot_chart = _generate_shot_chart(player_name, game_ids)

    # Get current date
    generated_date = datetime.now().strftime("%B %d, %Y")

    # Render HTML
    html = render_template(
        "player_report_pdf.html",
        player_name=player_name,
        game_type=game_type,
        generated_date=generated_date,
        team_avg=team_avg,
        team_rankings=team_rankings,
        shot_chart=shot_chart,
        **report_data,
        **charts,
    )

    # Convert to PDF
    html_doc = HTML(string=html)
    pdf_bytes = html_doc.write_pdf()
    
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    filename = f"{player_name.replace(' ', '_')}_report_{game_type}.pdf"
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@analytics_bp.route("/reports/download-all")
@login_required
def download_all_reports():
    """
    Generate a ZIP file containing PDF reports for all players.
    FIXED: In-memory approach to prevent hanging
    """
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    # Get all unique players
    players = (
        db.session.query(PlayerStat.player_name)
        .distinct()
        .order_by(PlayerStat.player_name)
        .all()
    )

    if not players:
        return jsonify({"error": "No players found"}), 404

    player_names = [p[0] for p in players]

    # Build game query
    game_query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        game_query = game_query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        game_query = game_query.filter(Game.game_type == "Friendly")

    games = game_query.all()
    if not games:
        return jsonify({"error": "No games for selected filter"}), 404

    game_ids = [g.id for g in games]
    game_map = {g.id: g for g in games}

    # Calculate team averages once
    team_avg = _calculate_team_averages(game_ids)

    # Get current date
    generated_date = datetime.now().strftime("%B %d, %Y")

    # Create ZIP in memory
    zip_buffer = BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for player_name in player_names:
                # Get player stats
                stats = (
                    PlayerStat.query.filter(PlayerStat.player_name == player_name)
                    .filter(PlayerStat.game_id.in_(game_ids))
                    .filter(PlayerStat.minutes != "00:00")
                    .filter(PlayerStat.minutes != "0")
                    .all()
                )

                if not stats:
                    continue  # Skip players with no stats

                # Sort stats by game date
                stats_with_dates = [(s, game_map.get(s.game_id)) for s in stats]
                stats_with_dates.sort(key=lambda x: x[1].sort_date if x[1] else "")
                stats = [s[0] for s in stats_with_dates]

                # Calculate metrics
                report_data = _calculate_player_metrics(stats, game_map, games_played=len(stats))

                # Calculate team rankings
                team_rankings = _calculate_team_rankings(player_name, game_ids, report_data)

                # Generate charts
                charts = _generate_player_charts(stats, game_map, player_name)
                
                # Generate shot chart
                shot_chart = _generate_shot_chart(player_name, game_ids)

                # Render HTML
                html = render_template(
                    "player_report_pdf.html",
                    player_name=player_name,
                    game_type=game_type,
                    generated_date=generated_date,
                    team_avg=team_avg,
                    team_rankings=team_rankings,
                    shot_chart=shot_chart,
                    **report_data,
                    **charts,
                )

                # Convert to PDF
                html_doc = HTML(string=html)
                pdf_data = html_doc.write_pdf()

                # Add to ZIP
                filename = f"{player_name.replace(' ', '_')}_report_{game_type}.pdf"
                zipf.writestr(filename, pdf_data)

        # Seek to beginning for reading
        zip_buffer.seek(0)

        # Send the ZIP file
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"all_player_reports_{game_type}.zip",
        )
    except Exception as e:
        # If anything fails, return error
        return jsonify({"error": f"Failed to generate reports: {str(e)}"}), 500


# NOTE: Remaining helper functions unchanged (omitted here for brevity in this commit payload).
# The repository file contains the full implementations.
