"""
Advanced Analytics API Routes
Provides endpoints for advanced basketball statistics and visualizations.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func, desc

from core.models import (
    db, Game, PlayerStat, ShotEvent, GameEvent, Play,
    LineupSegment, Possession, ShotZone
)
from core.advanced_analytics import (
    AdvancedPlayerStats, ClutchPerformance, LineupAnalytics,
    PossessionReconstructor, AnalyticsEngine, ShotChartAnalytics,
    classify_shot_zone, get_expected_value
)

advanced_api_bp = Blueprint("advanced_api", __name__, url_prefix="/api/advanced")


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
            'points': s.points or 0,
            'x_loc': s.x_loc,
            'y_loc': s.y_loc,
            'shot_type': s.shot_type
        }
        for s in shots
    ]
    
    shot_quality = AdvancedPlayerStats.calculate_shot_quality_score(shot_data)
    
    return jsonify({
        "player_name": player_name,
        "season_stats": stats,
        "shot_quality": shot_quality
    })


@advanced_api_bp.route("/player/<player_name>/usage")
@login_required
def get_player_usage(player_name):
    """Calculate true usage rate for a player."""
    game_type = request.args.get("game_type", "ALL")
    
    # Get player stats
    query = db.session.query(
        func.sum(PlayerStat.fga).label('fga'),
        func.sum(PlayerStat.fta).label('fta'),
        func.sum(PlayerStat.tov).label('tov'),
        func.sum(PlayerStat.minutes).label('minutes'),
        func.count(PlayerStat.id).label('games')
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
        func.sum(PlayerStat.fga).label('fga'),
        func.sum(PlayerStat.fta).label('fta'),
        func.sum(PlayerStat.tov).label('tov')
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
        team_minutes=player_result.games * 200  # 5 players * 40 min
    )
    
    return jsonify({
        "player_name": player_name,
        "usage_rate": usage,
        "player_possessions": (player_result.fga or 0) + 0.44 * (player_result.fta or 0) + (player_result.tov or 0),
        "games": player_result.games
    })


@advanced_api_bp.route("/player/<player_name>/pps")
@login_required
def get_player_pps(player_name):
    """Get Points Per Shot for a player."""
    game_type = request.args.get("game_type", "ALL")
    
    query = db.session.query(
        func.sum(PlayerStat.points).label('points'),
        func.sum(PlayerStat.fga).label('fga')
    ).filter(PlayerStat.player_name == player_name)
    
    if game_type == "Season":
        query = query.join(Game).filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.join(Game).filter(Game.game_type == "Friendly")
    
    result = query.first()
    
    if not result or not result.fga:
        return jsonify({"error": "No shot attempts found"}), 404
    
    pps = AdvancedPlayerStats.calculate_points_per_shot(
        points=result.points or 0,
        fga=result.fga
    )
    
    return jsonify({
        "player_name": player_name,
        "points_per_shot": pps,
        "total_points": result.points,
        "total_fga": result.fga
    })


# =============================================================================
# CLUTCH PERFORMANCE
# =============================================================================

@advanced_api_bp.route("/clutch/<int:game_id>")
@login_required
def get_game_clutch_stats(game_id):
    """Get clutch time statistics for a game."""
    player_name = request.args.get("player")
    
    clutch_stats = ClutchPerformance.get_clutch_stats(game_id, player_name)
    
    return jsonify({
        "game_id": game_id,
        "player_filter": player_name,
        "clutch_stats": clutch_stats
    })


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
            GameEvent.game_id == game_id,
            GameEvent.score_margin.isnot(None)
        ).all()
        
        for event in events:
            if not event.player_name:
                continue
            
            if event.player_name not in player_clutch:
                player_clutch[event.player_name] = {
                    'clutch_plays': 0,
                    'clutch_points': 0,
                    'clutch_fga': 0,
                    'clutch_fgm': 0
                }
            
            # Check if clutch situation
            from core.advanced_analytics import parse_time_to_seconds
            time_secs = parse_time_to_seconds(event.time_remaining or "5:00")
            
            if ClutchPerformance.is_clutch_situation(event.score_margin or 0, time_secs):
                player_clutch[event.player_name]['clutch_plays'] += 1
                
                if event.event_type in ['SHOT_2PT', 'SHOT_3PT']:
                    player_clutch[event.player_name]['clutch_fga'] += 1
                    if event.shot_attempt == 'made':
                        player_clutch[event.player_name]['clutch_fgm'] += 1
                        pts = 2 if event.event_type == 'SHOT_2PT' else 3
                        player_clutch[event.player_name]['clutch_points'] += pts
    
    # Calculate percentages
    results = []
    for player, stats in player_clutch.items():
        if stats['clutch_plays'] > 0:
            results.append({
                'player': player,
                **stats,
                'clutch_fg_pct': round(stats['clutch_fgm'] / stats['clutch_fga'] * 100, 1) if stats['clutch_fga'] > 0 else 0
            })
    
    return jsonify({
        "game_type": game_type,
        "players": sorted(results, key=lambda x: x['clutch_points'], reverse=True)
    })


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
    
    splits = LineupAnalytics.calculate_on_off_splits(player_name, game_ids)
    
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
    
    duos = LineupAnalytics.calculate_duo_compatibility(game_ids)
    
    return jsonify({
        "game_type": game_type,
        "duos": duos[:50]  # Top 50 duos
    })


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
    
    trios = LineupAnalytics.calculate_trio_compatibility(game_ids)
    
    return jsonify({
        "game_type": game_type,
        "trios": trios[:30]  # Top 30 trios
    })


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
    
    rankings = LineupAnalytics.get_lineup_efficiency_rankings(game_ids, min_possessions)
    
    return jsonify({
        "game_type": game_type,
        "min_possessions": min_possessions,
        "rankings": rankings[:20]  # Top 20 lineups
    })


@advanced_api_bp.route("/rotation/<int:game_id>")
@login_required
def get_rotation_analysis(game_id):
    """Get rotation analysis for a game."""
    rotation = LineupAnalytics.get_rotation_analysis(game_id)
    
    return jsonify(rotation)


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
        game_id=game_id,
        player_name=player_name,
        play_id=play_id,
        game_ids=game_ids
    )
    
    return jsonify({
        "total_shots": len(shots),
        "shots": shots
    })


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
    
    return jsonify({
        "player": player_name,
        "game_type": game_type,
        "heatmap": heatmap
    })


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
    
    return jsonify({
        "player": player_name,
        "hex_size": hex_size,
        "hexbins": hexbin
    })


@advanced_api_bp.route("/shots/by-play/<int:play_id>")
@login_required
def get_shots_by_play(play_id):
    """Get all shots for a specific play type."""
    shots = ShotChartAnalytics.get_shot_chart_data(play_id=play_id)
    
    # Aggregate stats
    total = len(shots)
    makes = sum(1 for s in shots if s['result'] == 'made')
    points = sum(s['points'] or 0 for s in shots)
    
    return jsonify({
        "play_id": play_id,
        "total_shots": total,
        "makes": makes,
        "fg_pct": round(makes / total * 100, 1) if total > 0 else 0,
        "total_points": points,
        "shots": shots
    })


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
    
    return jsonify({
        "game_type": game_type,
        "rankings": rankings
    })


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
    
    return jsonify({
        "game_id": game_id,
        "game_type": game_type,
        "four_factors": factors
    })


# =============================================================================
# POSSESSION RECONSTRUCTION
# =============================================================================

@advanced_api_bp.route("/possessions/reconstruct/<int:game_id>", methods=["POST"])
@login_required
def reconstruct_game_possessions(game_id):
    """Reconstruct and save possessions for a game."""
    count = PossessionReconstructor.save_possessions(game_id)
    
    return jsonify({
        "game_id": game_id,
        "possessions_created": count,
        "message": f"Successfully reconstructed {count} possessions"
    })


@advanced_api_bp.route("/possessions/<int:game_id>")
@login_required
def get_game_possessions(game_id):
    """Get possession data for a game."""
    possessions = Possession.query.filter_by(game_id=game_id).order_by(Possession.id).all()
    
    return jsonify({
        "game_id": game_id,
        "total_possessions": len(possessions),
        "possessions": [
            {
                "id": p.id,
                "team_possession": p.team_possession,
                "quarter": p.quarter,
                "points": p.points,
                "play_id": p.play_id
            }
            for p in possessions
        ]
    })


# =============================================================================
# SHOT ZONES
# =============================================================================

@advanced_api_bp.route("/zones")
@login_required
def get_shot_zones():
    """Get all shot zone definitions."""
    zones = ShotZone.query.all()
    
    return jsonify({
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
                    "y_max": z.y_max
                } if z.x_min else None
            }
            for z in zones
        ]
    })


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
    
    return jsonify({
        "zone": zone,
        "expected_value": expected,
        "coordinates": {"x": x_loc, "y": y_loc},
        "shot_type": shot_type
    })
