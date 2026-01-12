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
from flask import Blueprint, jsonify, render_template, request, send_file, after_this_request, url_for
from flask_login import login_required
from sqlalchemy import desc, func

# Standard WeasyPrint import - monkeypatch removed
from weasyprint import HTML

from core.models import Game, PlayerStat, db
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
    
    # Render HTML template
    html = render_template(
        "game_summary_pdf.html",
        game=game,
        stats=stats_with_metrics,
        top_performers=top_performers,
        alerts=alerts,
        team_aggregates=team_aggregates,
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
    - Page 1: Summary & Season Totals
    - Page 2: Per-Game & Per-100 Stats  
    - Page 3: Shooting Breakdown
    - Page 4: Advanced Metrics with Team Rankings
    - Page 5-6: Performance Charts with 3-Game MA
    - Page 7+: Game-by-Game Log
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

                # Render HTML
                html = render_template(
                    "player_report_pdf.html",
                    player_name=player_name,
                    game_type=game_type,
                    generated_date=generated_date,
                    team_avg=team_avg,
                    team_rankings=team_rankings,
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


def _calculate_player_metrics(stats, game_map, games_played):
    """Calculate comprehensive player metrics for the report"""
    # Averages
    avg_stats = get_player_stats_averages(stats)

    # Per 100 Possessions
    total_poss = 0
    total_minutes = 0
    for s in stats:
        poss = calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
        total_poss += poss
        total_minutes += parse_minutes(s.minutes)
    
    per_100_stats = {
        'points': normalize_per_100_possessions(avg_stats['points'], total_poss/games_played) if total_poss else 0,
        'reb': normalize_per_100_possessions(avg_stats['reb'], total_poss/games_played) if total_poss else 0,
        'ast': normalize_per_100_possessions(avg_stats['ast'], total_poss/games_played) if total_poss else 0,
        'stl': normalize_per_100_possessions(avg_stats['stl'], total_poss/games_played) if total_poss else 0,
        'blk': normalize_per_100_possessions(avg_stats['blk'], total_poss/games_played) if total_poss else 0,
    }

    # Shooting Breakdown
    shooting_data = {
        'fg': {'made': avg_stats['fgm'], 'att': avg_stats['fga'], 'pct': avg_stats['fg_percent']},
        'three_pt': {'made': avg_stats['tpm'], 'att': avg_stats['tpa'], 'pct': avg_stats['tp_percent']},
        'ft': {'made': avg_stats['ftm'], 'att': avg_stats['fta'], 'pct': avg_stats['ft_percent']},
    }
    
    # 2PT Calculations
    two_pt_made = avg_stats['fgm'] - avg_stats['tpm']
    two_pt_att = avg_stats['fga'] - avg_stats['tpa']
    shooting_data['two_pt'] = {
        'made': round(two_pt_made, 1),
        'att': round(two_pt_att, 1),
        'pct': safe_percentage(two_pt_made, two_pt_att)
    }

    # Advanced Metrics
    total_pts = avg_stats['points'] * games_played
    total_fga = avg_stats['fga'] * games_played
    total_fta = avg_stats['fta'] * games_played
    total_fgm = avg_stats['fgm'] * games_played
    total_tpm = avg_stats['tpm'] * games_played
    
    advanced_stats = {
        'ts_pct': calculate_ts_percent(total_pts, total_fga, total_fta),
        'efg_pct': calculate_efg_percent(total_fgm, total_tpm, total_fga),
        'ortg': calculate_ortg(total_pts, total_poss),
        'ast_tov': avg_stats['ast'] / avg_stats['tov'] if avg_stats['tov'] > 0 else avg_stats['ast'],
        'usg_pct': 0, # Requires team context, calculated separately
        'pie': 0 # Requires extensive team context
    }

    # Game Logs
    game_logs = []
    for s in stats:
        game = game_map.get(s.game_id)
        if not game: continue
        
        poss = calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
        ortg = calculate_ortg(s.points, poss)
        gmsc = s.points + 0.4*s.fgm - 0.7*s.fga - 0.4*(s.fta-s.ftm) + 0.7*s.oreb + 0.3*s.dreb + s.stl + 0.7*s.ast + 0.7*s.blk - 0.4*s.pf - s.tov

        game_logs.append({
            'date': game.date,
            'opponent': game.opponent,
            'result': game.result,
            'minutes': s.minutes,
            'pts': s.points,
            'reb': s.reb,
            'ast': s.ast,
            'stl': s.stl,
            'blk': s.blk,
            'tov': s.tov,
            'pf': s.pf,
            'fgm': s.fgm, 'fga': s.fga, 'fg_pct': round(s.fg_percent * 100, 1),
            'tpm': s.tpm, 'tpa': s.tpa, 'tp_percent': round(s.tp_percent * 100, 1),
            'ftm': s.ftm, 'fta': s.fta, 'ft_percent': round(s.ft_percent * 100, 1),
            'ortg': round(ortg, 1),
            'gmsc': round(gmsc, 1)
        })

    return {
        'avg_stats': avg_stats,
        'per_100': per_100_stats,
        'shooting': shooting_data,
        'advanced': advanced_stats,
        'games_played': games_played,
        'game_logs': game_logs
    }


def _generate_player_charts(stats, game_map, player_name):
    """Generate charts for player report"""
    if not stats:
        return {'chart_scoring': '', 'chart_shooting': ''}
        
    dates = []
    points = []
    ortgs = []
    
    for s in stats:
        game = game_map.get(s.game_id)
        if game:
            dates.append(game.date)
            points.append(s.points)
            poss = calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
            ortgs.append(calculate_ortg(s.points, poss))
            
    # Scoring Chart
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.bar(dates, points, color='#007bff', alpha=0.6, label='Points')
    ax1.set_ylabel('Points', color='#007bff')
    
    # Add trend line (MA 3)
    if len(points) >= 3:
        ma3 = [sum(points[i-2:i+1])/3 if i >= 2 else points[i] for i in range(len(points))]
        ax1.plot(dates, ma3, color='#0056b3', linestyle='--', linewidth=2, label='3-Game MA')
        
    ax1.tick_params(axis='x', rotation=45)
    plt.title(f"{player_name} - Scoring Trend")
    plt.tight_layout()
    
    img_io = BytesIO()
    plt.savefig(img_io, format='png', dpi=100)
    img_io.seek(0)
    chart_scoring = base64.b64encode(img_io.read()).decode()
    plt.close()

    return {'chart_scoring': chart_scoring}


def _calculate_game_stats(stats):
    """Enrich player stats with calculated metrics for PDF"""
    for s in stats:
        # Possessions
        poss = calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
        
        # Calculate Efficiency explicitly and assign to attribute
        s.eff = calculate_efficiency(
            s.points, s.reb, s.ast, s.stl, s.blk,
            s.fgm, s.fga, s.ftm, s.fta, s.tov
        )

        # Advanced metrics
        s.ortg = calculate_ortg(s.points, poss) if poss > 0 else 0
        s.ppp = calculate_ppp(s.points, poss) if poss > 0 else 0
        s.ts_pct = calculate_ts_percent(s.points, s.fga, s.fta)
        s.efg_pct = calculate_efg_percent(s.fgm, s.tpm, s.fga)
        s.ast_tov_ratio = (s.ast / s.tov) if s.tov > 0 else s.ast
        s.usg_pct = (poss / (parse_minutes(s.minutes) / 40)) if parse_minutes(s.minutes) > 0 else 0
        
        # Game Score (GmSc) - Hollinger Formula
        # GmSc = PTS + 0.4 * FGM - 0.7 * FGA - 0.4 * (FTA - FTM) + 0.7 * ORB + 0.3 * DRB + STL + 0.7 * AST + 0.7 * BLK - 0.4 * PF - TOV
        s.game_score = (
            s.points + 
            0.4 * s.fgm - 
            0.7 * s.fga - 
            0.4 * (s.fta - s.ftm) + 
            0.7 * s.oreb + 
            0.3 * s.dreb + 
            s.stl + 
            0.7 * s.ast + 
            0.7 * s.blk - 
            0.4 * s.pf - 
            s.tov
        )
        
        # 2PT breakdown
        two_pt = calculate_two_point_stats(s.fgm, s.fga, s.tpm, s.tpa)
        s.two_pt_made = two_pt["two_pt_made"]
        s.two_pt_att = two_pt["two_pt_att"]
        s.two_pt_pct = two_pt["two_pt_pct"]
    
    return stats

def _get_game_top_performers(stats):
    """Top 3 performers by efficiency"""
    # Filter out players with None stats to be safe
    valid_stats = [s for s in stats if hasattr(s, 'eff') and s.eff is not None]
    
    sorted_by_eff = sorted(valid_stats, key=lambda x: x.eff, reverse=True)
    sorted_by_pts = sorted(stats, key=lambda x: x.points, reverse=True)
    sorted_by_reb = sorted(stats, key=lambda x: x.reb, reverse=True)
    
    return {
        'efficiency': sorted_by_eff[0] if sorted_by_eff else None,
        'points': sorted_by_pts[0] if sorted_by_pts else None,
        'rebounds': sorted_by_reb[0] if sorted_by_reb else None,
    }

def _get_game_alerts(stats):
    """Extract fouls and low efficiency alerts"""
    return {
        'foul_trouble': [s for s in stats if s.pf >= 4],
        'inefficient': [s for s in stats if s.fga > 5 and hasattr(s, 'ppp') and s.ppp < 0.8],
    }

def _get_team_aggregates(stats):
    """Team-level shooting and efficiency"""
    total_fgm = sum(s.fgm for s in stats)
    total_fga = sum(s.fga for s in stats)
    total_tpm = sum(s.tpm for s in stats)
    total_tpa = sum(s.tpa for s in stats)
    total_ftm = sum(s.ftm for s in stats)
    total_fta = sum(s.fta for s in stats)
    total_pts = sum(s.points for s in stats)
    
    # 2PT Calculations
    total_2pm = total_fgm - total_tpm
    total_2pa = total_fga - total_tpa
    
    return {
        'fg_pct': (total_fgm / total_fga * 100) if total_fga > 0 else 0,
        'tp_pct': (total_tpm / total_tpa * 100) if total_tpa > 0 else 0,
        'ft_pct': (total_ftm / total_fta * 100) if total_fta > 0 else 0,
        'two_pt_pct': (total_2pm / total_2pa * 100) if total_2pa > 0 else 0,
        'ts_pct': calculate_ts_percent(total_pts, total_fga, total_fta),
    }


def _calculate_team_averages(game_ids):
    """
    Calculate team-wide averages across all players for comparison
    Returns averages for key metrics based on actual game data
    """
    # Get aggregate stats across all players
    team_stats = (
        db.session.query(
            func.avg(PlayerStat.points).label('avg_ppg'),
            func.avg(PlayerStat.reb).label('avg_rpg'),
            func.avg(PlayerStat.ast).label('avg_apg'),
            func.sum(PlayerStat.points).label('total_pts'),
            func.sum(PlayerStat.fga).label('total_fga'),
            func.sum(PlayerStat.fta).label('total_fta'),
            func.sum(PlayerStat.fgm).label('total_fgm'),
            func.sum(PlayerStat.tpm).label('total_tpm'),
            func.sum(PlayerStat.ast).label('total_ast'),
            func.sum(PlayerStat.tov).label('total_tov'),
            func.sum(PlayerStat.fga).label('sum_fga'),
            func.sum(PlayerStat.fta).label('sum_fta'),
            func.sum(PlayerStat.oreb).label('sum_oreb'),
            func.count(PlayerStat.id).label('player_games')
        )
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .first()
    )
    
    if not team_stats or not team_stats.player_games:
        # Return default values if no data
        return {
            'ppg': 0,
            'rpg': 0,
            'apg': 0,
            'ts_pct': 0,
            'efg_pct': 0,
            'ast_tov': 0,
            'ortg': 0
        }
    
    # Calculate team shooting percentages
    ts_pct = calculate_ts_percent(
        team_stats.total_pts,
        team_stats.total_fga,
        team_stats.total_fta
    )
    
    efg_pct = calculate_efg_percent(
        team_stats.total_fgm,
        team_stats.total_tpm,
        team_stats.total_fga
    )
    
    # AST/TOV ratio
    ast_tov = (team_stats.total_ast / team_stats.total_tov) if team_stats.total_tov > 0 else team_stats.total_ast
    
    # Calculate total possessions for ORTG
    total_possessions = 0
    all_stats = (
        PlayerStat.query
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .all()
    )
    
    for s in all_stats:
        total_possessions += calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
    
    ortg = calculate_ortg(team_stats.total_pts, total_possessions)
    
    return {
        'ppg': round(team_stats.avg_ppg or 0, 1),
        'rpg': round(team_stats.avg_rpg or 0, 1),
        'apg': round(team_stats.avg_apg or 0, 1),
        'ts_pct': round(ts_pct, 1),
        'efg_pct': round(efg_pct, 1),
        'ast_tov': round(ast_tov, 2),
        'ortg': round(ortg, 1)
    }


def _calculate_team_rankings(player_name, game_ids, report_data):
    """
    Calculate player's rank and percentile within the team for key metrics
    Returns rankings, percentiles, and distribution data
    """
    # Get all players' aggregate stats
    all_players_stats = (
        db.session.query(
            PlayerStat.player_name,
            func.avg(PlayerStat.points).label('ppg'),
            func.avg(PlayerStat.reb).label('rpg'),
            func.avg(PlayerStat.ast).label('apg'),
            func.sum(PlayerStat.points).label('total_pts'),
            func.sum(PlayerStat.fga).label('total_fga'),
            func.sum(PlayerStat.fta).label('total_fta'),
            func.sum(PlayerStat.fgm).label('total_fgm'),
            func.sum(PlayerStat.tpm).label('total_tpm'),
            func.sum(PlayerStat.ast).label('total_ast'),
            func.sum(PlayerStat.tov).label('total_tov'),
            func.count(PlayerStat.id).label('games')
        )
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .group_by(PlayerStat.player_name)
        .all()
    )
    
    if not all_players_stats:
        return {}
    
    # Calculate metrics for all players including THIS player's actual value
    players_data = []
    current_player_values = {}
    
    for player in all_players_stats:
        ts_pct = calculate_ts_percent(player.total_pts, player.total_fga, player.total_fta)
        efg_pct = calculate_efg_percent(player.total_fgm, player.total_tpm, player.total_fga)
        ast_tov = (player.total_ast / player.total_tov) if player.total_tov > 0 else player.total_ast
        
        # Calculate ORTG
        player_stats_list = (
            PlayerStat.query
            .filter(PlayerStat.player_name == player.player_name)
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .all()
        )
        
        total_poss = sum(calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in player_stats_list)
        ortg = calculate_ortg(player.total_pts, total_poss)
        
        player_metrics = {
            'name': player.player_name,
            'ppg': round(player.ppg, 1),
            'rpg': round(player.rpg, 1),
            'apg': round(player.apg, 1),
            'ts_pct': round(ts_pct, 1),
            'efg_pct': round(efg_pct, 1),
            'ast_tov': round(ast_tov, 2),
            'ortg': round(ortg, 1)
        }
        
        players_data.append(player_metrics)
        
        # Store current player's values
        if player.player_name == player_name:
            current_player_values = player_metrics
    
    # Calculate rankings and percentiles
    rankings = {}
    num_players = len(players_data)
    
    for metric in ['ppg', 'rpg', 'apg', 'ts_pct', 'efg_pct', 'ast_tov', 'ortg']:
        # Sort players by metric (descending)
        sorted_players = sorted(players_data, key=lambda x: x[metric], reverse=True)
        
        # Find player's rank
        rank = None
        for i, p in enumerate(sorted_players, 1):
            if p['name'] == player_name:
                rank = i
                break
        
        # Calculate percentile (higher percentile = better performance)
        percentile = ((num_players - rank + 1) / num_players * 100) if rank else 0
        
        # Get distribution for chart (all values sorted)
        distribution = sorted([p[metric] for p in players_data])
        
        # Get the ACTUAL player value from their calculated stats
        player_value = current_player_values.get(metric, 0)
        
        # Determine if player is leader
        is_leader = (rank == 1) if rank else False
        leader_name = sorted_players[0]['name'] if sorted_players else ""
        
        rankings[metric] = {
            'rank': rank,
            'total': num_players,
            'percentile': round(percentile, 0),
            'is_leader': is_leader,
            'leader_name': leader_name,
            'distribution': distribution,
            'player_value': player_value  # Add this for template to use
        }
    
    return rankings


def _calculate_enhanced_team_metrics(games, game_ids):
    """
    Calculate comprehensive team-level metrics with charts and analysis
    """
    total_games = len(games)
    wins = sum(1 for g in games if g.result == "W")
    losses = total_games - wins
    win_pct = (wins / total_games * 100) if total_games > 0 else 0
    
    total_team_score = sum(g.team_score for g in games)
    total_opp_score = sum(g.opponent_score for g in games)
    ppg = total_team_score / total_games if total_games > 0 else 0
    opp_ppg = total_opp_score / total_games if total_games > 0 else 0
    
    # Generate scoring trend chart
    chart_trend = _generate_team_scoring_chart(games)
    
    # Get top contributors
    top_contributors = _get_top_contributors(game_ids)
    
    # Opponent analysis
    opponent_stats = _analyze_opponents(games)
    
    # Home/Away splits - REMOVED since location field doesn't exist
    home_away_splits = {
        'home': None,
        'away': None,
        'neutral': None
    }
    
    return {
        "total_games": total_games,
        "wins": wins,
        "losses": losses,
        "win_pct": round(win_pct, 1),
        "ppg": round(ppg, 1),
        "opp_ppg": round(opp_ppg, 1),
        "games": games,
        "chart_trend": chart_trend,
        "top_contributors": top_contributors,
        "opponent_stats": opponent_stats,
        "home_away_splits": home_away_splits,
    }


def _generate_team_scoring_chart(games):
    """Generate team scoring trend chart"""
    if not games:
        return ""
    
    dates = [g.date for g in games]
    team_scores = [g.team_score for g in games]
    opp_scores = [g.opponent_score for g in games]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # Plot lines
    ax.plot(range(len(dates)), team_scores, marker='o', label='Team Score', 
            color='#28a745', linewidth=2)
    ax.plot(range(len(dates)), opp_scores, marker='s', label='Opponent Score', 
            color='#dc3545', linewidth=2, linestyle='--')
    
    # Add horizontal average lines
    avg_team = sum(team_scores) / len(team_scores)
    avg_opp = sum(opp_scores) / len(opp_scores)
    ax.axhline(y=avg_team, color='#28a745', linestyle=':', alpha=0.5, label=f'Avg Team: {avg_team:.1f}')
    ax.axhline(y=avg_opp, color='#dc3545', linestyle=':', alpha=0.5, label=f'Avg Opp: {avg_opp:.1f}')
    
    ax.set_xlabel('Game Number', fontsize=10)
    ax.set_ylabel('Points', fontsize=10)
    ax.set_title('Team Scoring Trends', fontsize=12, fontweight='bold')
    ax.legend(fontsize=8, loc='best')
    ax.grid(True, alpha=0.3)
    
    # Set x-axis
    ax.set_xticks(range(0, len(dates), max(1, len(dates) // 10)))
    ax.set_xticklabels(range(1, len(dates) + 1, max(1, len(dates) // 10)))
    
    plt.tight_layout()
    
    # Convert to base64
    img_io = BytesIO()
    plt.savefig(img_io, format='png', dpi=100, bbox_inches='tight')
    img_io.seek(0)
    img_base64 = base64.b64encode(img_io.read()).decode()
    plt.close(fig)
    
    return img_base64


def _get_top_contributors(game_ids):
    """
    Find top contributors for key stats across all games
    """
    stats_map = {
        'Points': func.sum(PlayerStat.points),
        'Rebounds': func.sum(PlayerStat.reb),
        'Assists': func.sum(PlayerStat.ast),
        'Steals': func.sum(PlayerStat.stl),
        'Blocks': func.sum(PlayerStat.blk)
    }
    
    contributors = {}
    
    for category, stat_func in stats_map.items():
        top = (
            db.session.query(
                PlayerStat.player_name,
                stat_func.label('total')
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .group_by(PlayerStat.player_name)
            .order_by(desc('total'))
            .first()
        )
        
        if top:
            contributors[category] = {
                'name': top.player_name,
                'value': int(top.total)
            }
            
    return contributors

def _analyze_opponents(games):
    """
    Analyze performance against different opponents
    """
    opp_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'pf': 0, 'pa': 0, 'games': 0})
    
    for g in games:
        opp = g.opponent
        opp_stats[opp]['games'] += 1
        opp_stats[opp]['pf'] += g.team_score
        opp_stats[opp]['pa'] += g.opponent_score
        
        if g.result == 'W':
            opp_stats[opp]['wins'] += 1
        else:
            opp_stats[opp]['losses'] += 1
            
    results = []
    for opp, stats in opp_stats.items():
        stats['diff'] = stats['pf'] - stats['pa']
        stats['opponent'] = opp
        results.append(stats)
        
    # Sort by point differential
    return sorted(results, key=lambda x: x['diff'], reverse=True)