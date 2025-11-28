from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import desc, func

from core.models import Game, PlayerStat, db

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/analytics")
@login_required
def dashboard():
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
    """
    API for Team Overview with Weighted Top Performers
    1. Team Scoring Trend
    2. Top Performers (dynamic stat & duration, weighted for %)
    """
    game_type = request.args.get("game_type", "ALL")
    limit_trend = int(request.args.get("limit_trend", 0))
    top_stat = request.args.get("top_stat", "efficiency")
    top_limit = int(request.args.get("top_limit", 3))

    # --- 1. TEAM TREND DATA ---
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

    # --- 2. SMART TOP PERFORMERS ---
    games_for_top = games[-top_limit:] if top_limit > 0 else games
    game_ids = [g.id for g in games_for_top]
    num_games = len(game_ids) if game_ids else 1

    # Define thresholds (Min attempts per game)
    MIN_FGA_PER_GAME = 4.0
    MIN_3PA_PER_GAME = 1.0
    MIN_FTA_PER_GAME = 1.0

    if not game_ids:
        return jsonify(
            {
                "trend": {"labels": [], "team_score": [], "opp_score": []},
                "metrics": {"win_pct": 0, "ppg": 0},
                "top_chart": {"labels": [], "data": [], "label": ""},
            }
        )

    # Handle Percentage Stats (Aggregation + Thresholds)
    if top_stat in ["fg_pct", "3p_pct", "ft_pct", "ts_pct", "efg_pct"]:
        if top_stat == "fg_pct":
            # Formula: Sum(FGM) / Sum(FGA)
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
            # TS% = Points / (2 * (FGA + 0.44 * FTA))
            numerator = func.sum(PlayerStat.points) * 100
            denominator = 2 * (
                func.sum(PlayerStat.fga) + (0.44 * func.sum(PlayerStat.fta))
            )
            threshold = (
                MIN_FGA_PER_GAME * num_games
            )  # Use FGA threshold as proxy for scoring attempts

        elif top_stat == "efg_pct":
            # eFG% = (FGM + 0.5 * 3PM) / FGA
            numerator = (
                func.sum(PlayerStat.fgm) + 0.5 * func.sum(PlayerStat.tpm)
            ) * 100
            denominator = func.sum(PlayerStat.fga)
            threshold = MIN_FGA_PER_GAME * num_games

        # Execute Weighted Query
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
        # Handle Counting Stats (Averages)
        # Same as before, but ensures we only count games played (minutes > 0)

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
                "label": f"Top {top_stat.replace('_', ' ').upper()} (Weighted)",
            },
        }
    )


@analytics_bp.route("/api/analytics/multi_compare")
@login_required
def multi_compare():
    """API for Multi-Player Comparison (All Stats)"""
    selected_players = request.args.getlist("players")
    selected_stats = request.args.getlist("stats")
    include_ma = request.args.get("ma") == "true"
    game_type = request.args.get("game_type", "ALL")

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
            valid_values = []  # For MA calculation (skips DNPs)

            for date in all_dates:
                p_stat = stat_map.get(date)

                # If player didn't play, we append NULL (None) so the chart line breaks
                # instead of dipping to 0 which ruins averages visually.
                if not p_stat:
                    values.append(None)
                    continue

                val = 0
                # --- METRIC LOGIC ---
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
                    val = p_stat.fg_percent
                elif metric == "3p_pct":
                    val = p_stat.tp_percent
                elif metric == "ft_pct":
                    val = p_stat.ft_percent

                # --- ADVANCED STATS ---
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
                elif metric == "ts_pct":  # True Shooting %
                    denom = 2 * (p_stat.fga + (0.44 * p_stat.fta))
                    val = (p_stat.points * 100) / denom if denom > 0 else 0
                elif metric == "efg_pct":  # Effective FG%
                    val = (
                        ((p_stat.fgm + 0.5 * p_stat.tpm) / p_stat.fga * 100)
                        if p_stat.fga > 0
                        else 0
                    )
                elif metric == "ast_tov":  # AST/TOV Ratio
                    val = p_stat.ast / p_stat.tov if p_stat.tov > 0 else p_stat.ast
                elif metric == "minutes":
                    try:
                        m, s = map(int, p_stat.minutes.split(":"))
                        val = m + (s / 60)
                    except:
                        val = 0

                values.append(val)
                valid_values.append(val)

            datasets.append(
                {
                    "label": f"{player} ({metric.upper()})",
                    "data": values,
                    "tension": 0.2,
                    "fill": False,
                    "spanGaps": True,  # Connect lines over missed games if desired, or False to break
                }
            )

            if include_ma:
                # Calculate MA only on VALID games played
                # Then map back to the timeline
                ma_values_map = {}

                # Compute rolling avg on valid list
                if len(valid_values) > 0:
                    series_vals = []
                    current_valid_idx = 0

                    # Create a parallel list of MAs
                    valid_mas = []
                    window_size = 3
                    for i in range(len(valid_values)):
                        if i < window_size - 1:
                            valid_mas.append(None)
                        else:
                            window = valid_values[i - (window_size - 1) : i + 1]
                            valid_mas.append(sum(window) / window_size)

                    # Re-inject into full timeline
                    full_ma_values = []
                    v_idx = 0
                    for v in values:
                        if v is None:
                            full_ma_values.append(None)
                        else:
                            full_ma_values.append(valid_mas[v_idx])
                            v_idx += 1
                else:
                    full_ma_values = [None] * len(values)

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
