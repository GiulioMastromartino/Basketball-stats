
from sqlalchemy import func, case, and_
from core.models import db, Play, ShotEvent, GameEvent

def get_play_stats(game_id, play_type="Offense"):
    """
    Calculate comprehensive stats for plays in a specific game.
    Includes both shot events and turnovers.
    """
    
    # 1. Fetch all plays of the requested type
    plays = Play.query.filter_by(play_type=play_type).all()
    play_map = {p.id: p for p in plays}
    
    if not plays:
        return []

    # 2. Query Shot Events (Grouped by Play)
    shot_stats = (
        db.session.query(
            ShotEvent.play_id,
            func.count(ShotEvent.id).label("shot_attempts"),
            func.sum(case((ShotEvent.result == "made", 1), else_=0)).label("made_shots"),
            func.sum(ShotEvent.points).label("points_scored"),
            func.sum(case((ShotEvent.shot_type == "3pt", 1), else_=0)).label("three_attempts"),
            func.sum(case((and_(ShotEvent.shot_type == "3pt", ShotEvent.result == "made"), 1), else_=0)).label("three_made")
        )
        .filter(ShotEvent.game_id == game_id, ShotEvent.play_id.isnot(None))
        .group_by(ShotEvent.play_id)
        .all()
    )
    
    # 3. Query Turnover Events (Grouped by Play)
    turnover_stats = (
        db.session.query(
            GameEvent.play_id,
            func.count(GameEvent.id).label("turnovers")
        )
        .filter(
            GameEvent.game_id == game_id, 
            GameEvent.play_id.isnot(None),
            GameEvent.event_type == "TURNOVER"
        )
        .group_by(GameEvent.play_id)
        .all()
    )
    
    # 4. Merge Data
    stats_by_play = {}
    
    # Initialize entries for all plays that have events
    active_play_ids = set([s.play_id for s in shot_stats] + [t.play_id for t in turnover_stats])
    
    for play_id in active_play_ids:
        if play_id not in play_map:
            continue
            
        play_name = play_map[play_id].name
        stats_by_play[play_id] = {
            "id": play_id,
            "name": play_name,
            "shot_attempts": 0,
            "made_shots": 0,
            "points": 0,
            "turnovers": 0,
            "three_attempts": 0,
            "three_made": 0
        }

    # Fill Shot Data
    for row in shot_stats:
        if row.play_id in stats_by_play:
            stats_by_play[row.play_id]["shot_attempts"] = row.shot_attempts or 0
            stats_by_play[row.play_id]["made_shots"] = row.made_shots or 0
            stats_by_play[row.play_id]["points"] = row.points_scored or 0
            stats_by_play[row.play_id]["three_attempts"] = row.three_attempts or 0
            stats_by_play[row.play_id]["three_made"] = row.three_made or 0

    # Fill Turnover Data
    for row in turnover_stats:
        if row.play_id in stats_by_play:
            stats_by_play[row.play_id]["turnovers"] = row.turnovers or 0

    # 5. Calculate Advanced Metrics
    final_stats = []
    
    for pid, data in stats_by_play.items():
        possessions = data["shot_attempts"] + data["turnovers"]
        # Note: We don't have separate shooting foul events linked to plays yet, 
        # so this possession count is a slight underestimation if FTA are frequent without FGA.
        # But for play tagging, usually the shot is recorded.
        
        if possessions == 0:
            continue

        ppp = data["points"] / possessions
        tov_pct = (data["turnovers"] / possessions) * 100
        score_pct = (data["made_shots"] / possessions) * 100
        fg_pct = (data["made_shots"] / data["shot_attempts"]) * 100 if data["shot_attempts"] > 0 else 0
        eFG_pct = ((data["made_shots"] + 0.5 * data["three_made"]) / data["shot_attempts"]) * 100 if data["shot_attempts"] > 0 else 0

        final_stats.append({
            "id": pid,
            "name": data["name"],
            "possessions": possessions,
            "points": data["points"],
            "ppp": round(ppp, 2),
            "turnovers": data["turnovers"],
            "tov_pct": round(tov_pct, 1),
            "score_pct": round(score_pct, 1),
            "made_shots": data["made_shots"],
            "shot_attempts": data["shot_attempts"],
            "fg_pct": round(fg_pct, 1),
            "efg_pct": round(eFG_pct, 1)
        })
    
    # Sort by frequency (possessions) descending
    final_stats.sort(key=lambda x: x["possessions"], reverse=True)
    
    return final_stats
