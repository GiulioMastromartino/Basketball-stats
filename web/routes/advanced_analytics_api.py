"""
Advanced Analytics API Routes
Provides endpoints for advanced basketball statistics and visualizations.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func, desc
from sqlalchemy.exc import OperationalError

from core.models import (
    db,
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    Play,
    Lineup,
    LineupSegment,
    Possession,
    ShotZone,
)
from core.advanced_analytics import (
    AdvancedPlayerStats,
    ClutchPerformance,
    LineupAnalytics,
    PossessionReconstructor,
    AnalyticsEngine,
    ShotChartAnalytics,
    classify_shot_zone,
    get_expected_value,
)

advanced_api_bp = Blueprint("advanced_api", __name__, url_prefix="/api/advanced")


def safe_query(func, fallback_result, error_message="Database table not found"):
    """
    Safely execute a query, returning fallback_result if table doesn't exist.
    """
    try:
        return func()
    except OperationalError as e:
        if "no such table" in str(e):
            print(f"[Advanced Analytics] Warning: {error_message} - {e}")
            return fallback_result
        raise
    except Exception as e:
        print(f"[Advanced Analytics] Error: {e}")
        return fallback_result


# =============================================================================
# PLAYER ADVANCED STATISTICS
# =============================================================================


@advanced_api_bp.route("/player/<player_name>/advanced")
@login_required
def get_player_advanced_stats(player_name):
    """Get advanced statistics for a player."""
    game_type = request.args.get("game_type", "ALL")

    stats = AnalyticsEngine.get_player_season_stats(player_name, game_type)

    if not stats:
        return jsonify({"error": "No data found for player"}), 404

    # Get shot quality metrics
    shots = ShotEvent.query.filter(ShotEvent.player_name == player_name).all()
    shot_data = [
        {
            "points": s.points or 0,
            "x_loc": s.x_loc,
            "y_loc": s.y_loc,
            "shot_type": s.shot_type,
        }
        for s in shots
    ]

    shot_quality = AdvancedPlayerStats.calculate_shot_quality_score(shot_data)

    return jsonify(
        {
            "player_name": player_name,
            "season_stats": stats,
            "shot_quality": shot_quality,
        }
    )


@advanced_api_bp.route("/player/<player_name>/usage")
@login_required
def get_player_usage(player_name):
    """Calculate true usage rate for a player."""
    game_type = request.args.get("game_type", "ALL")

    # Get player stats
    query = db.session.query(
        func.sum(PlayerStat.fga).label("fga"),
        func.sum(PlayerStat.fta).label("fta"),
        func.sum(PlayerStat.tov).label("tov"),
        func.sum(PlayerStat.minutes).label("minutes"),
        func.count(PlayerStat.id).label("games"),
    ).filter(PlayerStat.player_name == player_name)

    if game_type == "Season":
        query = query.join(Game).filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.join(Game).filter(Game.game_type == "Friendly")

    player_result = query.first()

    if not player_result or player_result.games == 0:
        return jsonify({"error": "No data found"}), 404

    # Get team totals
    team_query = db.session.query(
        func.sum(PlayerStat.fga).label("fga"),
        func.sum(PlayerStat.fta).label("fta"),
        func.sum(PlayerStat.tov).label("tov"),
    )

    if game_type == "Season":
        team_query = team_query.join(Game).filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        team_query = team_query.join(Game).filter(Game.game_type == "Friendly")

    team_result = team_query.first()

    # Calculate usage rate
    from core.utils import parse_minutes

    # Handle minutes parsing safely
    minutes = 0
    if player_result.minutes:
        if isinstance(player_result.minutes, str):
            minutes_str_list = player_result.minutes.split(",")
            minutes = sum(parse_minutes(m) for m in minutes_str_list)
        elif isinstance(player_result.minutes, (int, float)):
            # If already aggregated as number (e.g. from sum() in query)
            minutes = float(player_result.minutes)
    else:
        # Fallback estimation
        minutes = player_result.games * 25

    usage = AdvancedPlayerStats.calculate_true_usage_rate(
        fga=player_result.fga or 0,
        fta=player_result.fta or 0,
        tov=player_result.tov or 0,
        team_fga=team_result.fga or 0,
        team_fta=team_result.fta or 0,
        team_tov=team_result.tov or 0,
        minutes=minutes,
        team_minutes=player_result.games * 200,  # 5 players * 40 min
    )

    return jsonify(
        {
            "player_name": player_name,
            "usage_rate": usage,
            "player_possessions": (player_result.fga or 0)
            + 0.44 * (player_result.fta or 0)
            + (player_result.tov or 0),
            "games": player_result.games,
        }
    )


@advanced_api_bp.route("/player/<player_name>/pps")
@login_required
def get_player_pps(player_name):
    """Get Points Per Shot for a player."""
    game_type = request.args.get("game_type", "ALL")

    query = db.session.query(
        func.sum(PlayerStat.points).label("points"),
        func.sum(PlayerStat.fga).label("fga"),
    ).filter(PlayerStat.player_name == player_name)

    if game_type == "Season":
        query = query.join(Game).filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.join(Game).filter(Game.game_type == "Friendly")

    result = query.first()

    if not result or not result.fga:
        return jsonify({"error": "No shot attempts found"}), 404

    pps = AdvancedPlayerStats.calculate_points_per_shot(
        points=result.points or 0, fga=result.fga
    )

    return jsonify(
        {
            "player_name": player_name,
            "points_per_shot": pps,
            "total_points": result.points,
            "total_fga": result.fga,
        }
    )


# =============================================================================
# CLUTCH PERFORMANCE
# =============================================================================


@advanced_api_bp.route("/clutch/<int:game_id>")
@login_required
def get_game_clutch_stats(game_id):
    """Get clutch time statistics for a game."""
    player_name = request.args.get("player")

    clutch_stats = ClutchPerformance.get_clutch_stats(game_id, player_name)

    return jsonify(
        {"game_id": game_id, "player_filter": player_name, "clutch_stats": clutch_stats}
    )


@advanced_api_bp.route("/clutch/season")
@login_required
def get_season_clutch_stats():
    """Get season-wide clutch performance for all players."""
    game_type = request.args.get("game_type", "Season")

    # Get all games
    query = Game.query
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")

    games = query.all()
    game_ids = [g.id for g in games]

    # Aggregate clutch stats per player
    player_clutch = {}

    for game_id in game_ids:
        # Get all players who played in this game
        events = GameEvent.query.filter(
            GameEvent.game_id == game_id, GameEvent.score_margin.isnot(None)
        ).all()

        for event in events:
            if not event.player_name:
                continue

            if event.player_name not in player_clutch:
                player_clutch[event.player_name] = {
                    "clutch_plays": 0,
                    "clutch_points": 0,
                    "clutch_fga": 0,
                    "clutch_fgm": 0,
                }

            # Check if clutch situation
            from core.advanced_analytics import parse_time_to_seconds

            time_secs = parse_time_to_seconds(event.time_remaining or "5:00")

            if ClutchPerformance.is_clutch_situation(
                event.score_margin or 0, time_secs
            ):
                player_clutch[event.player_name]["clutch_plays"] += 1

                if event.event_type in ["SHOT_2PT", "SHOT_3PT"]:
                    player_clutch[event.player_name]["clutch_fga"] += 1
                    if event.shot_attempt == "made":
                        player_clutch[event.player_name]["clutch_fgm"] += 1
                        pts = 2 if event.event_type == "SHOT_2PT" else 3
                        player_clutch[event.player_name]["clutch_points"] += pts

    # Calculate percentages
    results = []
    for player, stats in player_clutch.items():
        if stats["clutch_plays"] > 0:
            results.append(
                {
                    "player": player,
                    **stats,
                    "clutch_fg_pct": round(
                        stats["clutch_fgm"] / stats["clutch_fga"] * 100, 1
                    )
                    if stats["clutch_fga"] > 0
                    else 0,
                }
            )

    return jsonify(
        {
            "game_type": game_type,
            "players": sorted(results, key=lambda x: x["clutch_points"], reverse=True),
        }
    )


# =============================================================================
# LINEUP ANALYTICS
# =============================================================================


@advanced_api_bp.route("/lineup/on-off/<player_name>")
@login_required
def get_on_off_splits(player_name):
    """Get on/off court splits for a player."""
    game_type = request.args.get("game_type", "ALL")

    # Get game IDs
    query = Game.query
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    def get_splits():
        return LineupAnalytics.calculate_on_off_splits(player_name, game_ids)

    splits = safe_query(
        get_splits,
        fallback_result={
            "player": player_name,
            "on_court": {
                "points_scored": 0,
                "points_allowed": 0,
                "possessions": 0,
                "rating": {"ortg": 0, "drtg": 0, "net": 0},
            },
            "off_court": {
                "points_scored": 0,
                "points_allowed": 0,
                "possessions": 0,
                "rating": {"ortg": 0, "drtg": 0, "net": 0},
            },
            "net_differential": 0,
            "error": "Lineup data not available. Run migrations to enable lineup analytics.",
        },
        error_message="lineup_segments table missing",
    )

    return jsonify(splits)


@advanced_api_bp.route("/lineup/duos")
@login_required
def get_duo_compatibility():
    """Get duo compatibility matrix."""
    game_type = request.args.get("game_type", "ALL")

    query = Game.query
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    duos = safe_query(
        lambda: LineupAnalytics.calculate_duo_compatibility(game_ids),
        fallback_result=[],
        error_message="lineup_segments table missing",
    )

    return jsonify(
        {
            "game_type": game_type,
            "duos": duos[:50],  # Top 50 duos
        }
    )


@advanced_api_bp.route("/lineup/trios")
@login_required
def get_trio_compatibility():
    """Get trio compatibility data."""
    game_type = request.args.get("game_type", "ALL")

    query = Game.query
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    trios = safe_query(
        lambda: LineupAnalytics.calculate_trio_compatibility(game_ids),
        fallback_result=[],
        error_message="lineup_segments table missing",
    )

    return jsonify(
        {
            "game_type": game_type,
            "trios": trios[:30],  # Top 30 trios
        }
    )


@advanced_api_bp.route("/lineup/rankings")
@login_required
def get_lineup_rankings():
    """Get 5-man lineup efficiency rankings."""
    game_type = request.args.get("game_type", "ALL")
    min_possessions = request.args.get("min_possessions", 5, type=int)

    query = Game.query
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")

    games = query.all()
    game_ids = [g.id for g in games]

    rankings = safe_query(
        lambda: LineupAnalytics.get_lineup_efficiency_rankings(
            game_ids, min_possessions
        ),
        fallback_result=[],
        error_message="lineup_segments table missing",
    )

    return jsonify(
        {
            "game_type": game_type,
            "min_possessions": min_possessions,
            "rankings": rankings[:20],  # Top 20 lineups
        }
    )


@advanced_api_bp.route("/rotation/<int:game_id>")
@login_required
def get_rotation_analysis(game_id):
    """Get rotation analysis for a game."""
    rotation = safe_query(
        lambda: LineupAnalytics.get_rotation_analysis(game_id),
        fallback_result={"game_id": game_id, "player_stints": {}, "rotation_data": []},
        error_message="game_events or lineup data missing",
    )

    return jsonify(rotation)


@advanced_api_bp.route("/lineup/game/<int:game_id>/rankings")
@login_required
def get_game_lineup_rankings(game_id):
    """Get top N 5-player lineups for a specific game, ranked by minutes played.

    Returns the top 4 lineups (by default) that played the most together in a game,
    with their offensive/defensive ratings and net rating.

    Query params:
        top_n: Number of top lineups to return (default: 4)
    """
    top_n = request.args.get("top_n", 4, type=int)

    # Verify game exists
    game = Game.query.get_or_404(game_id)

    rankings = safe_query(
        lambda: LineupAnalytics.get_game_lineup_rankings(game_id, top_n),
        fallback_result=[],
        error_message="lineup_segments table missing",
    )

    return jsonify(
        {
            "game_id": game_id,
            "opponent": game.opponent,
            "date": game.date,
            "team_score": game.team_score,
            "opponent_score": game.opponent_score,
            "result": game.result,
            "top_n": top_n,
            "rankings": rankings,
        }
    )


# =============================================================================
# SHOT CHARTS
# =============================================================================


@advanced_api_bp.route("/shots/chart")
@login_required
def get_shot_chart():
    """Get shot chart data with optional filters."""
    game_id = request.args.get("game_id", type=int)
    player_name = request.args.get("player")
    play_id = request.args.get("play_id", type=int)
    game_type = request.args.get("game_type", "ALL")

    game_ids = None
    if game_id:
        game_ids = [game_id]
    elif game_type != "ALL":
        query = Game.query
        if game_type == "Season":
            query = query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            query = query.filter(Game.game_type == "Friendly")
        games = query.all()
        game_ids = [g.id for g in games]

    shots = ShotChartAnalytics.get_shot_chart_data(
        game_id=game_id, player_name=player_name, play_id=play_id, game_ids=game_ids
    )

    return jsonify({"total_shots": len(shots), "shots": shots})


@advanced_api_bp.route("/shots/heatmap")
@login_required
def get_shot_heatmap():
    """Get shot heatmap data by zone."""
    player_name = request.args.get("player")
    game_type = request.args.get("game_type", "ALL")

    game_ids = None
    if game_type != "ALL":
        query = Game.query
        if game_type == "Season":
            query = query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            query = query.filter(Game.game_type == "Friendly")
        games = query.all()
        game_ids = [g.id for g in games]

    heatmap = ShotChartAnalytics.get_heatmap_data(game_ids, player_name)

    return jsonify({"player": player_name, "game_type": game_type, "heatmap": heatmap})


@advanced_api_bp.route("/shots/hexbin")
@login_required
def get_hexbin_data():
    """Get hexbin data for shot chart visualization."""
    player_name = request.args.get("player")
    game_type = request.args.get("game_type", "ALL")
    hex_size = request.args.get("hex_size", 50, type=int)

    game_ids = None
    if game_type != "ALL":
        query = Game.query
        if game_type == "Season":
            query = query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            query = query.filter(Game.game_type == "Friendly")
        games = query.all()
        game_ids = [g.id for g in games]

    hexbin = ShotChartAnalytics.get_hexbin_data(game_ids, player_name, hex_size)

    return jsonify({"player": player_name, "hex_size": hex_size, "hexbins": hexbin})


@advanced_api_bp.route("/shots/by-play/<int:play_id>")
@login_required
def get_shots_by_play(play_id):
    """Get all shots for a specific play type."""
    shots = ShotChartAnalytics.get_shot_chart_data(play_id=play_id)

    # Aggregate stats
    total = len(shots)
    makes = sum(1 for s in shots if s["result"] == "made")
    points = sum(s["points"] or 0 for s in shots)

    return jsonify(
        {
            "play_id": play_id,
            "total_shots": total,
            "makes": makes,
            "fg_pct": round(makes / total * 100, 1) if total > 0 else 0,
            "total_points": points,
            "shots": shots,
        }
    )


# =============================================================================
# PLAY RANKINGS
# =============================================================================


@advanced_api_bp.route("/plays/rankings")
@login_required
def get_play_rankings():
    """Get play effectiveness rankings (optimized single query)."""
    game_type = request.args.get("game_type", "ALL")

    game_ids = None
    if game_type != "ALL":
        query = Game.query
        if game_type == "Season":
            query = query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            query = query.filter(Game.game_type == "Friendly")
        games = query.all()
        game_ids = [g.id for g in games]

    rankings = AnalyticsEngine.get_team_plays_rankings(game_ids)

    return jsonify({"game_type": game_type, "rankings": rankings})


# =============================================================================
# FOUR FACTORS
# =============================================================================


@advanced_api_bp.route("/four-factors")
@login_required
def get_four_factors():
    """Get Dean Oliver's Four Factors."""
    game_id = request.args.get("game_id", type=int)
    game_type = request.args.get("game_type", "ALL")

    game_ids = None
    if game_id:
        game_ids = [game_id]
    elif game_type != "ALL":
        query = Game.query
        if game_type == "Season":
            query = query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            query = query.filter(Game.game_type == "Friendly")
        games = query.all()
        game_ids = [g.id for g in games]

    factors = AnalyticsEngine.get_four_factors(game_id=game_id, game_ids=game_ids)

    return jsonify(
        {"game_id": game_id, "game_type": game_type, "four_factors": factors}
    )


# =============================================================================
# POSSESSION RECONSTRUCTION
# =============================================================================


@advanced_api_bp.route("/possessions/reconstruct/<int:game_id>", methods=["POST"])
@login_required
def reconstruct_game_possessions(game_id):
    """Reconstruct and save possessions for a game."""
    count = PossessionReconstructor.save_possessions(game_id)

    return jsonify(
        {
            "game_id": game_id,
            "possessions_created": count,
            "message": f"Successfully reconstructed {count} possessions",
        }
    )


@advanced_api_bp.route("/possessions/<int:game_id>")
@login_required
def get_game_possessions(game_id):
    """Get possession data for a game."""
    possessions = (
        Possession.query.filter_by(game_id=game_id).order_by(Possession.id).all()
    )

    return jsonify(
        {
            "game_id": game_id,
            "total_possessions": len(possessions),
            "possessions": [
                {
                    "id": p.id,
                    "team_possession": p.team_possession,
                    "quarter": p.quarter,
                    "points": p.points,
                    "play_id": p.play_id,
                }
                for p in possessions
            ],
        }
    )


# =============================================================================
# SHOT ZONES
# =============================================================================


@advanced_api_bp.route("/zones")
@login_required
def get_shot_zones():
    """Get all shot zone definitions."""
    zones = ShotZone.query.all()

    return jsonify(
        {
            "zones": [
                {
                    "id": z.id,
                    "name": z.zone_name,
                    "type": z.zone_type,
                    "expected_value": z.expected_value,
                    "description": z.description,
                    "bounds": {
                        "x_min": z.x_min,
                        "x_max": z.x_max,
                        "y_min": z.y_min,
                        "y_max": z.y_max,
                    }
                    if z.x_min
                    else None,
                }
                for z in zones
            ]
        }
    )


@advanced_api_bp.route("/zones/classify", methods=["POST"])
@login_required
def classify_shot():
    """Classify a shot into a zone based on coordinates."""
    data = request.get_json()

    x_loc = data.get("x_loc")
    y_loc = data.get("y_loc")
    shot_type = data.get("shot_type", "2pt")

    zone = classify_shot_zone(x_loc, y_loc, shot_type)
    expected = get_expected_value(zone)

    return jsonify(
        {
            "zone": zone,
            "expected_value": expected,
            "coordinates": {"x": x_loc, "y": y_loc},
            "shot_type": shot_type,
        }
    )


# =============================================================================
# ADVANCED GAME REPORT
# =============================================================================


@advanced_api_bp.route("/game/<int:game_id>/report")
@login_required
def get_advanced_game_report(game_id):
    """
    Get comprehensive advanced game report data.

    Returns:
        - Game metadata
        - Team box score and advanced metrics
        - Player box scores with advanced stats
        - Four factors comparison
        - Shot chart data
        - Scoring breakdown by quarter
        - Top performers
        - Clutch performance
        - Play effectiveness
    """
    from core.advanced_game_report import (
        TeamBox,
        PlayerBox,
        team_advanced,
        player_advanced,
    )

    game = Game.query.get_or_404(game_id)
    stats = PlayerStat.query.filter_by(game_id=game_id).all()
    shots = ShotEvent.query.filter_by(game_id=game_id).all()
    events = (
        GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.timestamp).all()
    )

    if not stats:
        return jsonify({"error": "No stats for this game"}), 404

    # Build team box score
    team_box = TeamBox(
        pts=sum(s.points or 0 for s in stats),
        fgm=sum(s.fgm or 0 for s in stats),
        fga=sum(s.fga or 0 for s in stats),
        tpm=sum(s.tpm or 0 for s in stats),
        tpa=sum(s.tpa or 0 for s in stats),
        ftm=sum(s.ftm or 0 for s in stats),
        fta=sum(s.fta or 0 for s in stats),
        orb=sum(s.oreb or 0 for s in stats),
        drb=sum(s.dreb or 0 for s in stats),
        trb=sum((s.oreb or 0) + (s.dreb or 0) for s in stats),
        ast=sum(s.ast or 0 for s in stats),
        stl=sum(s.stl or 0 for s in stats),
        blk=sum(s.blk or 0 for s in stats),
        tov=sum(s.tov or 0 for s in stats),
    )

    # Estimate opponent box score
    team_poss = team_box.fga + 0.44 * team_box.fta - team_box.orb + team_box.tov
    opp_fga_est = int(team_poss * 0.6) if team_poss > 0 else 0
    opp_fta_est = int(opp_fga_est * 0.25) if opp_fga_est > 0 else 0

    opp_box = TeamBox(
        pts=game.opponent_score,
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
        tov=int(team_poss * 0.15) if team_poss > 0 else 0,
    )

    # Calculate team advanced metrics
    team_adv = team_advanced(team_box, opp_box)
    opp_adv = team_advanced(opp_box, team_box)

    # Build player box scores
    players = []
    for s in stats:
        minutes = 0
        if s.minutes:
            if isinstance(s.minutes, str) and ":" in s.minutes:
                parts = s.minutes.split(":")
                minutes = (
                    float(parts[0]) + float(parts[1]) / 60
                    if len(parts) > 1
                    else float(parts[0])
                )
            else:
                try:
                    minutes = float(s.minutes)
                except (ValueError, TypeError):
                    minutes = 0

        players.append(
            PlayerBox(
                name=s.player_name,
                minutes=minutes,
                pts=s.points or 0,
                fgm=s.fgm or 0,
                fga=s.fga or 0,
                tpm=s.tpm or 0,
                tpa=s.tpa or 0,
                ftm=s.ftm or 0,
                fta=s.fta or 0,
                orb=s.oreb or 0,
                drb=s.dreb or 0,
                trb=(s.oreb or 0) + (s.dreb or 0),
                ast=s.ast or 0,
                stl=s.stl or 0,
                blk=s.blk or 0,
                tov=s.tov or 0,
            )
        )

    # Calculate player advanced metrics
    team_minutes_total = 200.0  # 40-minute game
    player_rows = [player_advanced(p, team_box, team_minutes_total) for p in players]
    player_rows.sort(key=lambda r: r["pts"], reverse=True)

    # Add basic stats to player rows
    for i, s in enumerate(sorted(stats, key=lambda x: x.points or 0, reverse=True)):
        if i < len(player_rows):
            player_rows[i]["fgm"] = s.fgm or 0
            player_rows[i]["fga"] = s.fga or 0
            player_rows[i]["tpm"] = s.tpm or 0
            player_rows[i]["tpa"] = s.tpa or 0
            player_rows[i]["ftm"] = s.ftm or 0
            player_rows[i]["fta"] = s.fta or 0
            player_rows[i]["oreb"] = s.oreb or 0
            player_rows[i]["dreb"] = s.dreb or 0
            player_rows[i]["stl"] = s.stl or 0
            player_rows[i]["blk"] = s.blk or 0
            player_rows[i]["fg_pct"] = (
                round((s.fgm / s.fga * 100), 1) if s.fga and s.fgm else 0
            )
            player_rows[i]["tp_pct"] = (
                round((s.tpm / s.tpa * 100), 1) if s.tpa and s.tpm else 0
            )
            player_rows[i]["ft_pct"] = (
                round((s.ftm / s.fta * 100), 1) if s.fta and s.ftm else 0
            )

    # Shot chart data
    shot_data = [
        {
            "x": s.x_loc,
            "y": s.y_loc,
            "result": s.result,
            "points": s.points,
            "player": s.player_name,
            "quarter": s.quarter,
            "zone": classify_shot_zone(s.x_loc, s.y_loc, s.shot_type),
        }
        for s in shots
    ]

    # Zone breakdown
    zones = {}
    for shot in shot_data:
        zone = shot["zone"]
        if zone not in zones:
            zones[zone] = {"makes": 0, "attempts": 0, "points": 0}
        zones[zone]["attempts"] += 1
        zones[zone]["points"] += shot["points"] or 0
        if shot["result"] == "made":
            zones[zone]["makes"] += 1

    for zone in zones:
        zones[zone]["fg_pct"] = (
            round(zones[zone]["makes"] / zones[zone]["attempts"] * 100, 1)
            if zones[zone]["attempts"] > 0
            else 0
        )
        zones[zone]["pps"] = (
            round(zones[zone]["points"] / zones[zone]["attempts"], 2)
            if zones[zone]["attempts"] > 0
            else 0
        )

    # Quarterly scoring breakdown
    quarters = {
        1: {"team": 0, "opp": 0},
        2: {"team": 0, "opp": 0},
        3: {"team": 0, "opp": 0},
        4: {"team": 0, "opp": 0},
    }
    for s in shots:
        q = s.quarter or 1
        if q in quarters and s.result == "made":
            quarters[q]["team"] += s.points or 0

    # Score progression from events
    score_progression = []
    cumulative_team = 0
    cumulative_opp = game.opponent_score  # Start with final opponent score

    for e in events:
        if e.event_type in ["SHOT_2PT", "SHOT_3PT", "FT"] and e.shot_attempt == "made":
            pts = (
                2
                if e.event_type == "SHOT_2PT"
                else (3 if e.event_type == "SHOT_3PT" else 1)
            )
            cumulative_team += pts
            score_progression.append(
                {
                    "timestamp": e.timestamp,
                    "quarter": e.quarter,
                    "team_score": cumulative_team,
                    "opp_score": int(
                        cumulative_opp * len(score_progression) / max(len(events), 1)
                    ),  # Estimate
                    "margin": cumulative_team
                    - int(
                        cumulative_opp * len(score_progression) / max(len(events), 1)
                    ),
                }
            )

    # Top performers
    top_performers = sorted(player_rows, key=lambda x: x["pts"], reverse=True)[:3]

    # Clutch performance (last 5 minutes, margin <= 5)
    clutch_stats = {"plays": 0, "points": 0, "fgm": 0, "fga": 0}
    for e in events:
        if e.score_margin is not None and abs(e.score_margin) <= 5:
            time_secs = 0
            if e.time_remaining:
                parts = e.time_remaining.split(":")
                if len(parts) == 2:
                    time_secs = int(parts[0]) * 60 + int(parts[1])
            if e.quarter == 4 and time_secs <= 300:  # Last 5 minutes
                clutch_stats["plays"] += 1
                if e.event_type in ["SHOT_2PT", "SHOT_3PT"]:
                    clutch_stats["fga"] += 1
                    if e.shot_attempt == "made":
                        clutch_stats["fgm"] += 1
                        pts = 2 if e.event_type == "SHOT_2PT" else 3
                        clutch_stats["points"] += pts

    return jsonify(
        {
            "game": {
                "id": game.id,
                "date": game.date,
                "opponent": game.opponent,
                "team_score": game.team_score,
                "opponent_score": game.opponent_score,
                "result": game.result,
                "type": game.game_type,
            },
            "team": team_adv,
            "opponent": opp_adv,
            "players": player_rows,
            "shots": shot_data,
            "zones": zones,
            "quarters": quarters,
            "score_progression": score_progression,
            "top_performers": top_performers,
            "clutch": clutch_stats,
            "four_factors": {
                "team": {
                    "efg_pct": team_adv.get("efg_pct", 0),
                    "tov_pct": team_adv.get("tov_pct", 0),
                    "orb_pct": team_adv.get("orb_pct", 0),
                    "ft_rate": team_adv.get("ftr", 0),
                },
                "opponent": {
                    "efg_pct": opp_adv.get("efg_pct", 0),
                    "tov_pct": opp_adv.get("tov_pct", 0),
                    "orb_pct": opp_adv.get("orb_pct", 0),
                    "ft_rate": opp_adv.get("ftr", 0),
                },
            },
        }
    )


# =============================================================================
# LINEUPS API
# =============================================================================


@advanced_api_bp.route("/lineups")
@login_required
def get_all_lineups():
    """Get all lineups with cached stats, sorted by total minutes played.

    Query params:
        game_type: Filter by game type (Season, Friendly, ALL)
        min_minutes: Minimum minutes played to include
        sort_by: Sort field (total_minutes, net_rating, ortg, drtg)
    """
    game_type = request.args.get("game_type", "ALL")
    min_minutes = request.args.get("min_minutes", 0, type=float)
    sort_by = request.args.get("sort_by", "total_seconds")

    query = Lineup.query

    # Filter by minimum minutes
    if min_minutes > 0:
        query = query.filter(Lineup.total_seconds >= min_minutes * 60)

    # Map sort_by names to actual columns
    sort_column_map = {
        "total_minutes": Lineup.total_seconds,
        "total_seconds": Lineup.total_seconds,
        "net_rating": Lineup.net_rating,
        "ortg": Lineup.ortg,
        "drtg": Lineup.drtg,
        "games_played": Lineup.games_played,
    }
    sort_column = sort_column_map.get(sort_by, Lineup.total_seconds)
    query = query.order_by(desc(sort_column))

    lineups = query.all()

    return jsonify(
        {
            "total": len(lineups),
            "game_type": game_type,
            "lineups": [
                {
                    "id": l.id,
                    "display_name": l.display_name,
                    "players": l.players,
                    "total_minutes": round(l.total_seconds / 60, 1),
                    "games_played": l.games_played,
                    "segment_count": l.segment_count,
                    "possessions": l.total_possessions,
                    "points_scored": l.points_scored,
                    "points_allowed": l.points_allowed,
                    "ortg": l.ortg,
                    "drtg": l.drtg,
                    "net_rating": l.net_rating,
                    "is_starting": l.is_starting,
                }
                for l in lineups
            ],
        }
    )


@advanced_api_bp.route("/lineup/<int:lineup_id>")
@login_required
def get_lineup_card(lineup_id):
    """Get detailed stats for a single lineup (card view).

    Includes per-game breakdown and segment details.
    """
    lineup = Lineup.query.get_or_404(lineup_id)

    # Get all segments for this lineup
    segments = LineupSegment.query.filter_by(lineup_id=lineup_id).all()

    # Group by game
    games_data = {}
    for segment in segments:
        game_id = segment.game_id
        if game_id not in games_data:
            game = Game.query.get(game_id)
            games_data[game_id] = {
                "game_id": game_id,
                "date": game.date if game else None,
                "opponent": game.opponent if game else "Unknown",
                "result": game.result if game else None,
                "team_score": game.team_score if game else 0,
                "opponent_score": game.opponent_score if game else 0,
                "total_seconds": 0,
                "points_scored": 0,
                "points_allowed": 0,
                "possessions": 0,
                "segments": [],
            }

        games_data[game_id]["total_seconds"] += segment.duration_seconds or 0
        games_data[game_id]["points_scored"] += segment.points_scored or 0
        games_data[game_id]["points_allowed"] += segment.points_allowed or 0
        games_data[game_id]["possessions"] += segment.possessions or 0
        games_data[game_id]["segments"].append(
            {
                "segment_id": segment.id,
                "quarter": segment.quarter,
                "duration_seconds": segment.duration_seconds,
                "points_scored": segment.points_scored,
                "points_allowed": segment.points_allowed,
            }
        )

    # Convert to list and sort by date
    games_list = sorted(
        games_data.values(), key=lambda x: x["date"] or "", reverse=True
    )

    fg_pct = round((lineup.fgm / lineup.fga) * 100, 1) if lineup.fga > 0 else 0
    tp_pct = round((lineup.tpm / lineup.tpa) * 100, 1) if lineup.tpa > 0 else 0
    ft_pct = round((lineup.ftm / lineup.fta) * 100, 1) if lineup.fta > 0 else 0

    return jsonify(
        {
            "lineup": {
                "id": lineup.id,
                "display_name": lineup.display_name,
                "players": lineup.players,
                "lineup_hash": lineup.lineup_hash,
                "is_starting": lineup.is_starting,
                "created_at": lineup.created_at.isoformat()
                if lineup.created_at
                else None,
                "last_updated": lineup.last_updated.isoformat()
                if lineup.last_updated
                else None,
            },
            "stats": {
                "total_minutes": round(lineup.total_seconds / 60, 1),
                "games_played": lineup.games_played,
                "segment_count": lineup.segment_count,
                "possessions": lineup.total_possessions,
                "points_scored": lineup.points_scored,
                "points_allowed": lineup.points_allowed,
                "ortg": lineup.ortg,
                "drtg": lineup.drtg,
                "net_rating": lineup.net_rating,
                "ppg": round(lineup.points_scored / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
                "opp_ppg": round(lineup.points_allowed / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
                "fgm": lineup.fgm,
                "fga": lineup.fga,
                "fg_pct": fg_pct,
                "tpm": lineup.tpm,
                "tpa": lineup.tpa,
                "tp_pct": tp_pct,
                "ftm": lineup.ftm,
                "fta": lineup.fta,
                "ft_pct": ft_pct,
                "oreb": lineup.oreb,
                "dreb": lineup.dreb,
                "reb": lineup.oreb + lineup.dreb,
                "ast": lineup.ast,
                "stl": lineup.stl,
                "blk": lineup.blk,
                "tov": lineup.tov,
                "rpg": round((lineup.oreb + lineup.dreb) / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
                "apg": round(lineup.ast / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
                "spg": round(lineup.stl / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
                "bpg": round(lineup.blk / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
                "topg": round(lineup.tov / lineup.games_played, 1)
                if lineup.games_played > 0
                else 0,
            },
            "games": games_list,
            "opponent_shots": get_opponent_shots_for_lineup(lineup_id),
        }
    )


def get_opponent_shots_for_lineup(lineup_id):
    """Get opponent shot locations for all segments in a lineup."""
    from core.models import GameEvent
    
    segments = LineupSegment.query.filter_by(lineup_id=lineup_id).all()
    if not segments:
        return []
    
    shots = []
    for segment in segments:
        # Get OPP_SCORE events during this segment with shot locations
        segment_shots = GameEvent.query.filter(
            GameEvent.game_id == segment.game_id,
            GameEvent.event_type == "OPP_SCORE",
            GameEvent.timestamp >= segment.start_timestamp,
            GameEvent.timestamp <= (segment.end_timestamp or 9999999999999)
        ).all()
        
        for shot in segment_shots:
            x = shot.x_loc if hasattr(shot, 'x_loc') else None
            y = shot.y_loc if hasattr(shot, 'y_loc') else None
            # Parse detail to get result
            import json
            detail = json.loads(shot.detail) if shot.detail else {}
            result = detail.get('result', 'made')
            
            if x is not None and y is not None:
                shots.append({
                    "x": x,
                    "y": y,
                    "result": result,
                    "quarter": shot.quarter,
                    "game_id": segment.game_id,
                })
    
    return shots


@advanced_api_bp.route("/lineup/<int:lineup_id>", methods=["PUT"])
@login_required
def update_lineup_name(lineup_id):
    """Update the display name of a lineup.

    Request body:
        display_name: New display name for the lineup
    """
    data = request.get_json()
    if not data or "display_name" not in data:
        return jsonify({"error": "display_name required"}), 400

    lineup = Lineup.query.get_or_404(lineup_id)
    lineup.display_name = data["display_name"]
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "lineup": {
                "id": lineup.id,
                "display_name": lineup.display_name,
            },
        }
    )


@advanced_api_bp.route("/lineup/by-players", methods=["POST"])
@login_required
def get_lineup_by_players():
    """Get lineup stats by player combination.

    Request body:
        players: List of 5 player names

    Returns:
        Lineup stats if found, or 404 if lineup doesn't exist.
    """
    import hashlib
    from core.services.lineup_service import generate_lineup_hash

    data = request.get_json()
    if not data or "players" not in data:
        return jsonify({"error": "players list required"}), 400

    players = data["players"]
    if len(players) != 5:
        return jsonify({"error": "Exactly 5 players required"}), 400

    lineup_hash = generate_lineup_hash(players)
    lineup = Lineup.query.filter_by(lineup_hash=lineup_hash).first()

    if not lineup:
        return jsonify(
            {
                "found": False,
                "lineup_hash": lineup_hash,
                "players": sorted(players),
            }
        ), 404

    # Return the same format as get_lineup_card
    return jsonify(
        {
            "found": True,
            "lineup_id": lineup.id,
            "redirect": f"/api/advanced/lineup/{lineup.id}",
        }
    )
