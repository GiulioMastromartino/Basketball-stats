from core.models import Game, PlayerStat, ShotEvent, GameEvent, Play, db
from core.utils import normalize_date_to_display
from flask import current_app
import re

def validate_play_id(play_id):
    """
    Validate that a play ID exists in the database before using it.
    Returns the validated play_id or raises ValueError if invalid.
    """
    if not play_id:
        return None
    
    try:
        play_id_int = int(play_id)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid play ID type: {play_id}. Must be an integer.")
    
    play = Play.query.get(play_id_int)
    if not play:
        raise ValueError(f"Play ID {play_id_int} does not exist in the database.")
    
    return play_id_int

def normalize_sort_date(date_str: str) -> str:
    """Ensure sort_date is strictly YYYY-MM-DD for DB storage."""
    if not date_str:
        return ""
    
    # If already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str
        
    # If DD/MM/YYYY or DD-MM-YYYY
    match = re.match(r"^(\d{2})[-/](\d{2})[-/](\d{4})$", date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
        
    return date_str  # fallback, might fail DB constraints if too long

def create_game_from_live_data(data):
    """
    Creates a new Game, PlayerStats, ShotEvents, and GameEvents from the JSON data payload.
    Validates all play IDs before database insertion.
    Handles 'IMPORT_JSON' style structure (nested objects) vs 'LIVE' style (flat structure).
    """
    if not data:
        raise ValueError("No data received")

    # Detect structure type (Nested 'game' object vs Flat)
    is_nested_import = "game" in data
    
    if is_nested_import:
        # Structure: {"game": {...}, "player_stats": [...], "shot_events": [...], ...}
        game_data = data["game"]
        raw_date = game_data.get("date")
        
        # Determine dates
        # JSON import usually has pre-formatted dates, but we verify
        if raw_date and re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            # It's YYYY-MM-DD
            sort_date = raw_date
            # Convert to DD-MM-YYYY for display
            parts = raw_date.split("-")
            display_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else:
            # Assume it's already display format or needs normalization
            display_date = normalize_date_to_display(raw_date)
            sort_date = normalize_sort_date(raw_date)
            
        opponent = game_data.get("opponent")
        team_score = int(game_data.get("team_score", 0))
        opponent_score = int(game_data.get("opponent_score", 0))
        game_type = game_data.get("game_type", "Season")
        source = "IMPORT_JSON"
        
        # Player stats list
        player_stats_source = data.get("player_stats", [])
        shot_events_source = data.get("shot_events", [])
        game_events_source = data.get("game_events", [])
        
    else:
        # Structure: Flat fields + "player_stats": {"Name": {...}} + "shot_locations": [...]
        # LIVE GAME payload
        raw_date = data.get("date")
        
        # Handle date logic for LIVE input
        if raw_date and re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            sort_date = raw_date
            parts = raw_date.split("-")
            display_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else:
            display_date = normalize_date_to_display(raw_date)
            sort_date = normalize_sort_date(raw_date)

        opponent = data.get("opponent")
        team_score = int(data.get("team_score", 0))
        opponent_score = int(data.get("opponent_score", 0))
        game_type = data.get("game_type", "Season")
        source = "LIVE"
        
        # LIVE payload uses a Dict for player_stats, list for others
        player_stats_source = data.get("player_stats", {})
        shot_events_source = data.get("shot_locations", [])
        game_events_source = data.get("game_events", [])

    # Validate constraints
    if len(display_date) > 10:
        # Emergency truncation or fix to prevent DB crash
        # If it's 2026/01/2015 -> try to salvage or fail
        current_app.logger.warning(f"Date format too long: {display_date}. Attempting fix.")
        display_date = display_date[:10]

    # Create Game
    game = Game(
        date=display_date,
        opponent=opponent,
        team_score=team_score,
        opponent_score=opponent_score,
        result="W" if team_score > opponent_score else "L",
        game_type=game_type,
        sort_date=sort_date,
        source=source,
    )
    db.session.add(game)
    db.session.flush()

    # --- Process Player Stats ---
    if is_nested_import:
        # List of dicts
        for p_data in player_stats_source:
            # Filter valid keys
            valid_keys = {c.name for c in PlayerStat.__table__.columns if c.name not in ('id', 'game_id')}
            stat_kwargs = {k: v for k, v in p_data.items() if k in valid_keys}
            stat = PlayerStat(game_id=game.id, **stat_kwargs)
            db.session.add(stat)
    else:
        # Dict of dicts (LIVE)
        for p_name, stats in player_stats_source.items():
            if not p_name:
                continue
            
            fg_pct = (stats["fgm"] / stats["fga"] * 100) if stats["fga"] > 0 else 0.0
            tp_pct = (stats["tpm"] / stats["tpa"] * 100) if stats["tpa"] > 0 else 0.0
            ft_pct = (stats["ftm"] / stats["fta"] * 100) if stats["fta"] > 0 else 0.0

            new_stat = PlayerStat(
                game_id=game.id,
                player_name=p_name,
                minutes=stats.get("minutes", "00:00"),
                points=stats["points"],
                fgm=stats["fgm"],
                fga=stats["fga"],
                fg_percent=fg_pct,
                tpm=stats["tpm"],
                tpa=stats["tpa"],
                tp_percent=tp_pct,
                ftm=stats["ftm"],
                fta=stats["fta"],
                ft_percent=ft_pct,
                oreb=stats["oreb"],
                dreb=stats["dreb"],
                reb=stats["oreb"] + stats["dreb"],
                ast=stats["ast"],
                tov=stats["tov"],
                stl=stats["stl"],
                blk=stats["blk"],
                pf=stats["pf"],
                plus_minus=int(stats.get("plus_minus", 0) or 0),
            )
            db.session.add(new_stat)

    # --- Process Shot Events ---
    for s_data in shot_events_source:
        if is_nested_import:
            # List of dicts with DB keys
            valid_keys = {c.name for c in ShotEvent.__table__.columns if c.name not in ('id', 'game_id', 'play_id')}
            shot_kwargs = {k: v for k, v in s_data.items() if k in valid_keys}
            shot = ShotEvent(game_id=game.id, play_id=None, **shot_kwargs)
        else:
            # LIVE format
            shooter = (s_data.get("shooter") or "").strip()
            shot_type = (s_data.get("type") or "").strip()
            points = int(s_data.get("points") or 0)
            result = s_data.get("result", "made")
            play_id = s_data.get("play_id")
            x = s_data.get("x")
            y = s_data.get("y")
            q = s_data.get("quarter")

            validated_play_id = None
            if play_id:
                try:
                    validated_play_id = validate_play_id(play_id)
                except ValueError:
                    pass

            shot = ShotEvent(
                game_id=game.id,
                player_name=shooter,
                shot_type=shot_type,
                result=result,
                points=points,
                x_loc=float(x) if x is not None else None,
                y_loc=float(y) if y is not None else None,
                quarter=int(q) if q is not None else None,
                play_id=validated_play_id
            )
        db.session.add(shot)

    # --- Process Game Events ---
    for e_data in game_events_source:
        if is_nested_import:
             # List of dicts with DB keys
            valid_keys = {c.name for c in GameEvent.__table__.columns if c.name not in ('id', 'game_id', 'play_id')}
            event_kwargs = {k: v for k, v in e_data.items() if k in valid_keys}
            event = GameEvent(game_id=game.id, play_id=None, **event_kwargs)
        else:
             # LIVE format
            event_type = e_data.get("type")
            player_name = e_data.get("player")
            detail = e_data.get("detail")
            timestamp = e_data.get("timestamp", 0)
            shot_attempt = e_data.get("shot_attempt")
            play_id = e_data.get("play_id")

            validated_play_id = None
            if play_id:
                try:
                    validated_play_id = validate_play_id(play_id)
                except ValueError:
                    pass

            event = GameEvent(
                game_id=game.id,
                event_type=event_type,
                player_name=player_name,
                detail=str(detail) if detail is not None else "",
                timestamp=int(timestamp),
                shot_attempt=shot_attempt,
                play_id=validated_play_id
            )
        db.session.add(event)

    db.session.commit()
    return game
