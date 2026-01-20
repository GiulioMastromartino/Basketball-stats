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

from core.models import Game, PlayerStat, ShotEvent, db, Play
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
    
    # Enrich stats with SHOT DATA (for inline SVG charts) and PLAY CHIPS
    for s in stats_with_metrics:
        # Get shots for this player in this game
        player_shots = ShotEvent.query.filter_by(game_id=game_id, player_name=s.player_name).all()
        s.shots = [{
            'x': shot.x_loc, 
            'y': shot.y_loc, 
            'result': shot.result
        } for shot in player_shots if shot.x_loc is not None and shot.y_loc is not None]
        
        # Set flag if valid shots exist for SVG rendering
        s.shot_chart_svg = len(s.shots) > 0
        
        # Calculate play chips (pts by play type)
        # Using a direct query to aggregate points by play type
        play_stats = db.session.query(
            Play.name,
            func.sum(ShotEvent.points).label('pts')
        ).join(ShotEvent, Play.id == ShotEvent.play_id)\
         .filter(ShotEvent.game_id == game_id, ShotEvent.player_name == s.player_name)\
         .group_by(Play.name).all()
        
        # Also get points from shots without a play
        unassigned_pts = db.session.query(func.sum(ShotEvent.points)).filter(
            ShotEvent.game_id == game_id, 
            ShotEvent.player_name == s.player_name,
            ShotEvent.play_id.is_(None)
        ).scalar() or 0
        
        # Format chips
        chips = []
        for p_name, pts in play_stats:
            if pts and pts > 0:
                chips.append({'label': p_name, 'pts': int(pts)})
        
        if unassigned_pts > 0:
            chips.append({'label': 'Unassigned', 'pts': int(unassigned_pts)})
            
        # Sort by points descending and take top 3 + merge rest
        chips.sort(key=lambda x: x['pts'], reverse=True)
        
        final_chips = chips[:3]
        remainder = sum(c['pts'] for c in chips[3:])
        if remainder > 0:
            final_chips.append({'label': 'Other', 'pts': remainder})
            
        s.play_chips = final_chips

    
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
        generated_date=datetime.now().strftime("%B %d, %Y"),
    )
    
    # Convert to PDF
    html_doc = HTML(string=html)
    pdf_bytes = html_doc.write_pdf()
    
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)
    
    filename = f"game_{game.opponent}_{game.date}.pdf"
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@analytics_bp.route("/team/report.pdf")
@login_required
def team_report_pdf():
    """Generate enhanced team-level PDF report"""
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
    """Generate a multi-page PDF report for player"""
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
    """Generate a ZIP file containing PDF reports for all players."""
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


# ============================================================
# HELPER FUNCTIONS
# ============================================================

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

def draw_court(ax=None, color='black', lw=2, outer_lines=False):
    \"\"\"Draws a basketball court on a matplotlib axis.\"\"\"
    if ax is None:
        ax = plt.gca()

    # Hoop
    hoop = patches.Circle((0, 0), radius=7.5, linewidth=lw, color=color, fill=False)

    # Backboard
    backboard = patches.Rectangle((-30, -7.5), 60, -1, linewidth=lw, color=color)

    # The paint
    # Outer box
    outer_box = patches.Rectangle((-80, -47.5), 160, 190, linewidth=lw, color=color, fill=False)
    # Inner box
    inner_box = patches.Rectangle((-60, -47.5), 120, 190, linewidth=lw, color=color, fill=False)

    # Free Throw Top Arc
    top_free_throw = patches.Arc((0, 142.5), 120, 120, theta1=0, theta2=180, linewidth=lw, color=color, fill=False)
    # Free Throw Bottom Arc
    bottom_free_throw = patches.Arc((0, 142.5), 120, 120, theta1=180, theta2=0, linewidth=lw, color=color, linestyle='dashed')

    # Restricted Zone
    restricted = patches.Arc((0, 0), 80, 80, theta1=0, theta2=180, linewidth=lw, color=color)

    # Three Point Line
    # Side lines
    corner_three_a = patches.Rectangle((-220, -47.5), 0, 140, linewidth=lw, color=color)
    corner_three_b = patches.Rectangle((220, -47.5), 0, 140, linewidth=lw, color=color)
    # 3pt Arc
    three_arc = patches.Arc((0, 0), 475, 475, theta1=22, theta2=158, linewidth=lw, color=color)

    # Center Court
    center_outer_arc = patches.Arc((0, 422.5), 120, 120, theta1=180, theta2=0, linewidth=lw, color=color)
    center_inner_arc = patches.Arc((0, 422.5), 40, 40, theta1=180, theta2=0, linewidth=lw, color=color)

    # List of court elements
    court_elements = [hoop, backboard, outer_box, inner_box, top_free_throw,
                      bottom_free_throw, restricted, corner_three_a,
                      corner_three_b, three_arc, center_outer_arc, center_inner_arc]

    if outer_lines:
        # Draw the outer boundary lines of the court
        outer_lines = patches.Rectangle((-250, -47.5), 500, 470, linewidth=lw,
                                        color=color, fill=False)
        court_elements.append(outer_lines)

    # Add patches to the axis
    for element in court_elements:
        ax.add_patch(element)

    return ax

def _generate_team_shot_chart(game_ids):
    \"\"\"Generate team shot chart for given games\"\"\"
    try:
        shots = ShotEvent.query.filter(ShotEvent.game_id.in_(game_ids)).all()
        
        if not shots:
            return \"\"

        plt.figure(figsize=(12, 11))
        draw_court(outer_lines=True)
        
        # Separate makes and misses
        made_x = [s.x_loc for s in shots if s.result == 'made' and s.x_loc is not None]
        made_y = [s.y_loc for s in shots if s.result == 'made' and s.y_loc is not None]
        missed_x = [s.x_loc for s in shots if s.result == 'missed' and s.x_loc is not None]
        missed_y = [s.y_loc for s in shots if s.result == 'missed' and s.y_loc is not None]
        
        # Plot shots
        plt.scatter(missed_x, missed_y, c='red', marker='x', s=100, linewidths=3, label='Missed')
        plt.scatter(made_x, made_y, c='green', marker='o', s=100, edgecolors='white', label='Made')
        
        plt.xlim(-250, 250)
        plt.ylim(422.5, -47.5)
        plt.axis('off')
        plt.legend(loc='lower center', ncol=2)
        
        # Save to base64
        img = BytesIO()
        plt.savefig(img, format='svg', bbox_inches='tight', transparent=True)
        img.seek(0)
        plt.close()
        
        return base64.b64encode(img.getvalue()).decode()
    except Exception as e:
        print(f\"Error generating team shot chart: {e}\")
        plt.close()
        return \"\"

def _generate_shot_chart(player_name, game_ids):
    \"\"\"Generate shot chart for a specific player\"\"\"
    try:
        shots = ShotEvent.query.filter(
            ShotEvent.player_name == player_name,
            ShotEvent.game_id.in_(game_ids)
        ).all()
        
        if not shots:
            return \"\"

        plt.figure(figsize=(12, 11))
        draw_court(outer_lines=True)
        
        made_x = [s.x_loc for s in shots if s.result == 'made' and s.x_loc is not None]
        made_y = [s.y_loc for s in shots if s.result == 'made' and s.y_loc is not None]
        missed_x = [s.x_loc for s in shots if s.result == 'missed' and s.x_loc is not None]
        missed_y = [s.y_loc for s in shots if s.result == 'missed' and s.y_loc is not None]
        
        plt.scatter(missed_x, missed_y, c='red', marker='x', s=100, linewidths=3, label='Missed')
        plt.scatter(made_x, made_y, c='green', marker='o', s=100, edgecolors='white', label='Made')
        
        plt.xlim(-250, 250)
        plt.ylim(422.5, -47.5)
        plt.axis('off')
        plt.legend(loc='lower center', ncol=2)
        
        img = BytesIO()
        plt.savefig(img, format='svg', bbox_inches='tight', transparent=True)
        img.seek(0)
        plt.close()
        
        return base64.b64encode(img.getvalue()).decode()
    except Exception as e:
        print(f\"Error generating shot chart: {e}\")
        plt.close()
        return \"\"

def _generate_player_charts(stats, game_map, player_name):
    \"\"\"Generate trend charts for player report\"\"\"
    charts = {}
    try:
        # PPG Chart
        plt.figure(figsize=(10, 4))
        dates = [game_map[s.game_id].date.strftime('%m/%d') for s in stats]
        points = [s.points for s in stats]
        
        plt.plot(dates, points, marker='o', linewidth=2, color='#208dd1')
        plt.fill_between(dates, points, alpha=0.1, color='#208dd1')
        plt.title('Points Per Game Trend')
        plt.grid(True, alpha=0.3)
        
        img = BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
        img.seek(0)
        charts['ppg_chart'] = base64.b64encode(img.getvalue()).decode()
        plt.close()
        
        # Efficiency Chart
        plt.figure(figsize=(10, 4))
        effs = [s.eff for s in stats]  # Assuming eff is pre-calculated
        plt.bar(dates, effs, color='#10b981', alpha=0.7)
        plt.title('Efficiency Rating Trend')
        plt.grid(True, axis='y', alpha=0.3)
        
        img = BytesIO()
        plt.savefig(img, format='png', bbox_inches='tight', dpi=100)
        img.seek(0)
        charts['efficiency_chart'] = base64.b64encode(img.getvalue()).decode()
        plt.close()
        
    except Exception as e:
        print(f\"Error generating player charts: {e}\")
        plt.close()
        
    return charts

def _calculate_enhanced_team_metrics(games, game_ids):
    \"\"\"Calculate aggregate stats for team report\"\"\"
    if not games:
        return {}
        
    total_games = len(games)
    wins = sum(1 for g in games if g.team_score > g.opponent_score)
    losses = total_games - wins
    
    total_pts = sum(g.team_score for g in games)
    total_opp_pts = sum(g.opponent_score for g in games)
    
    # Get all player stats for these games
    stats = PlayerStat.query.filter(PlayerStat.game_id.in_(game_ids)).all()
    
    # Aggregate shooting
    total_fgm = sum(s.fgm for s in stats)
    total_fga = sum(s.fga for s in stats)
    total_tpm = sum(s.tpm for s in stats)
    total_tpa = sum(s.tpa for s in stats)
    total_ftm = sum(s.ftm for s in stats)
    total_fta = sum(s.fta for s in stats)
    
    fg_pct = (total_fgm / total_fga * 100) if total_fga > 0 else 0
    tp_pct = (total_tpm / total_tpa * 100) if total_tpa > 0 else 0
    ft_pct = (total_ftm / total_fta * 100) if total_fta > 0 else 0
    
    # Top scorers
    player_points = defaultdict(int)
    for s in stats:
        player_points[s.player_name] += s.points
        
    top_scorers = sorted(
        [{'name': k, 'points': v, 'ppg': round(v/total_games, 1)} for k,v in player_points.items()],
        key=lambda x: x['points'], 
        reverse=True
    )[:5]
    
    return {
        'total_games': total_games,
        'wins': wins,
        'losses': losses,
        'win_pct': round(wins / total_games * 100, 1) if total_games > 0 else 0,
        'ppg': round(total_pts / total_games, 1) if total_games > 0 else 0,
        'ppg_allowed': round(total_opp_pts / total_games, 1) if total_games > 0 else 0,
        'fg_pct': round(fg_pct, 1),
        'tp_pct': round(tp_pct, 1),
        'ft_pct': round(ft_pct, 1),
        'top_scorers': top_scorers
    }

def _calculate_player_metrics(stats, game_map, games_played):
    \"\"\"Calculate aggregate player metrics for report\"\"\"
    if not stats:
        return {}
        
    total_pts = sum(s.points for s in stats)
    total_reb = sum(s.reb for s in stats)
    total_ast = sum(s.ast for s in stats)
    total_stl = sum(s.stl for s in stats)
    total_blk = sum(s.blk for s in stats)
    
    total_fgm = sum(s.fgm for s in stats)
    total_fga = sum(s.fga for s in stats)
    total_tpm = sum(s.tpm for s in stats)
    total_tpa = sum(s.tpa for s in stats)
    total_ftm = sum(s.ftm for s in stats)
    total_fta = sum(s.fta for s in stats)
    
    fg_pct = (total_fgm / total_fga * 100) if total_fga > 0 else 0
    tp_pct = (total_tpm / total_tpa * 100) if total_tpa > 0 else 0
    ft_pct = (total_ftm / total_fta * 100) if total_fta > 0 else 0
    
    # Calculate averages
    ppg = round(total_pts / games_played, 1) if games_played > 0 else 0
    rpg = round(total_reb / games_played, 1) if games_played > 0 else 0
    apg = round(total_ast / games_played, 1) if games_played > 0 else 0
    spg = round(total_stl / games_played, 1) if games_played > 0 else 0
    bpg = round(total_blk / games_played, 1) if games_played > 0 else 0
    
    # Recent games data
    recent_games = []
    # Sort stats by game date
    sorted_stats = sorted(stats, key=lambda s: game_map[s.game_id].date if s.game_id in game_map else datetime.min, reverse=True)
    
    for s in sorted_stats[:5]:
        game = game_map.get(s.game_id)
        if game:
            recent_games.append({
                'date': game.date.strftime('%m/%d'),
                'opponent': game.opponent,
                'result': 'W' if game.team_score > game.opponent_score else 'L',
                'points': s.points,
                'rebounds': s.reb,
                'assists': s.ast
            })
            
    return {
        'games_played': games_played,
        'total_points': total_pts,
        'ppg': ppg,
        'rpg': rpg,
        'apg': apg,
        'spg': spg,
        'bpg': bpg,
        'fg_pct': round(fg_pct, 1),
        'tp_pct': round(tp_pct, 1),
        'ft_pct': round(ft_pct, 1),
        'fgm': total_fgm, 'fga': total_fga,
        'tpm': total_tpm, 'tpa': total_tpa,
        'ftm': total_ftm, 'fta': total_fta,
        'recent_games': recent_games
    }

def _calculate_team_averages(game_ids):
    \"\"\"Get team average stats for comparison\"\"\"
    if not game_ids:
        return {'ppg': 0, 'rpg': 0, 'apg': 0}
        
    num_games = len(game_ids)
    
    # Total team stats
    team_pts = db.session.query(func.sum(Game.team_score)).filter(Game.id.in_(game_ids)).scalar() or 0
    
    # For rebounds/assists, we sum player stats
    team_reb = db.session.query(func.sum(PlayerStat.reb)).filter(PlayerStat.game_id.in_(game_ids)).scalar() or 0
    team_ast = db.session.query(func.sum(PlayerStat.ast)).filter(PlayerStat.game_id.in_(game_ids)).scalar() or 0
    
    return {
        'ppg': round(team_pts / num_games, 1) if num_games > 0 else 0,
        'rpg': round(team_reb / num_games, 1) if num_games > 0 else 0,
        'apg': round(team_ast / num_games, 1) if num_games > 0 else 0
    }

def _calculate_team_rankings(player_name, game_ids, player_metrics):
    \"\"\"Calculate player's rank in team\"\"\"
    if not game_ids:
        return {'ppg_rank': '-', 'eff_rank': '-'}
        
    # Get averages for all players
    stats = db.session.query(
        PlayerStat.player_name,
        func.sum(PlayerStat.points).label('total_pts'),
        func.count(PlayerStat.id).label('games')
    ).filter(
        PlayerStat.game_id.in_(game_ids),
        PlayerStat.minutes != "00:00"
    ).group_by(PlayerStat.player_name).all()
    
    # Calculate PPG for all
    player_ppg = []
    for name, pts, games in stats:
        ppg = pts / games if games > 0 else 0
        player_ppg.append((name, ppg))
        
    # Sort and find rank
    player_ppg.sort(key=lambda x: x[1], reverse=True)
    
    rank = 1
    for i, (name, _) in enumerate(player_ppg):
        if name == player_name:
            rank = i + 1
            break
            
    return {
        'ppg_rank': rank,
        'eff_rank': '-' # Placeholder as eff requires more complex calc
    }
