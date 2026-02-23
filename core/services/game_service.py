import json
import re

from core.models import Game, PlayerStat, ShotEvent, GameEvent, Play, db
from core.services.lineup_service import process_game_lineups
from core.utils import normalize_date_to_display
from flask import current_app


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


def find_or_create_play(play_name, play_type="Offense"):
    """Find an existing play by name or create a new one.

    Args:
        play_name: Name of the play to find or create
        play_type: Type of play (Offense, Defense, Special) - default Offense

    Returns:
        Play object (existing or newly created)
    """
    from core.models import Play

    if not play_name or not play_name.strip():
        return None

    play_name = play_name.strip()

    # Try to find existing play
    existing = Play.query.filter_by(name=play_name).first()
    if existing:
        return existing

    # Create new play
    new_play = Play(
        name=play_name,
        play_type=play_type,
        description="Auto-created from game import",
        source="imported",
    )
    db.session.add(new_play)
    db.session.flush()  # Get the ID without committing

    current_app.logger.info(f"Auto-created play: {play_name} (ID: {new_play.id})")
    return new_play


def extract_play_name_from_detail(detail):
    """Extract play_name from detail string or dict.

    Args:
        detail: Can be a string (JSON/dict representation) or dict

    Returns:
        play_name string or None
    """
    if not detail:
        return None

    # If it's already a dict
    if isinstance(detail, dict):
        return detail.get("play_name")

    # If it's a string, try to parse it
    if isinstance(detail, str):
        # Try JSON parse first
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                return parsed.get("play_name")
        except (json.JSONDecodeError, ValueError):
            pass

        # Try ast.literal_eval for Python dict strings like "{'play_id': 8, 'play_name': 'Personale'}"
        try:
            import ast

            parsed = ast.literal_eval(detail)
            if isinstance(parsed, dict):
                return parsed.get("play_name")
        except (ValueError, SyntaxError):
            pass

    return None


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


def get_nested_value(data, *keys, default=None):
    """Get a value from a dict trying multiple possible key names."""
    for key in keys:
        if key in data:
            return data[key]
    return default


def assign_possession_numbers(game_id: int) -> None:
    """
    Assign possession numbers to GameEvents after import.

    Groups related events into single possessions:
    - Each SHOT_2PT, SHOT_3PT, TURNOVER ends a team possession
    - Consecutive FT events for same player = one possession
    - Each OPP_SCORE ends an opponent possession

    Args:
        game_id: ID of the game to process
    """
    events = (
        GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.timestamp).all()
    )

    if not events:
        return

    possession_number = 0
    last_ft_player = None
    ft_possession_active = False

    POSSESSION_ENDING = {"SHOT_2PT", "SHOT_3PT", "TURNOVER"}
    FT_EVENTS = {"FT", "FT_MADE", "FT_MISS"}

    for event in events:
        if event.event_type in POSSESSION_ENDING:
            possession_number += 1
            event.possession_number = possession_number
            ft_possession_active = False
            last_ft_player = None

        elif event.event_type in FT_EVENTS:
            if not ft_possession_active or event.player_name != last_ft_player:
                possession_number += 1
                ft_possession_active = True
                last_ft_player = event.player_name
            event.possession_number = possession_number

        elif event.event_type == "OPP_SCORE":
            possession_number += 1
            event.possession_number = possession_number
            ft_possession_active = False
            last_ft_player = None

        elif event.event_type == "OPP_OREB":
            if possession_number > 0:
                event.possession_number = possession_number

    db.session.commit()
    current_app.logger.info(
        f"Assigned {possession_number} possessions for game {game_id}"
    )


def create_game_from_live_data(data):
    """
    Creates a new Game, PlayerStats, ShotEvents, and GameEvents from the JSON data payload.
    Validates all play IDs before database insertion.
    Handles 'IMPORT_JSON' style structure (nested objects) vs 'LIVE' style (flat structure).
    Also supports legacy key name variations for backwards compatibility.
    """
    if not data:
        raise ValueError("No data received")

    # Extract format metadata for post-processing decisions
    schema_version = data.get("schema_version", 1)  # Default to v1 if not present
    features = data.get("features", {})  # Feature flags dict

    # Detect structure type (Nested 'game' object vs Flat)
    is_nested_import = "game" in data

    if is_nested_import:
        # Structure: {"game": {...}, "player_stats": [...], "shot_events": [...], ...}
        game_data = data["game"]
        raw_date = get_nested_value(game_data, "date", "Date", "game_date")

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

        opponent = get_nested_value(game_data, "opponent", "Opponent", "vs", "versus")
        team_score = int(
            get_nested_value(
                game_data, "team_score", "TeamScore", "our_score", default=0
            )
        )
        opponent_score = int(
            get_nested_value(
                game_data, "opponent_score", "OpponentScore", "their_score", default=0
            )
        )
        game_type = get_nested_value(
            game_data, "game_type", "GameType", "type", default="Season"
        )
        source = "IMPORT_JSON"

        # Player stats list - support multiple key names
        player_stats_source = get_nested_value(
            data, "player_stats", "PlayerStats", "players", "Players", default=[]
        )
        shot_events_source = get_nested_value(
            data, "shot_events", "ShotEvents", "shots", "Shots", default=[]
        )
        game_events_source = get_nested_value(
            data, "game_events", "GameEvents", "events", "Events", default=[]
        )

    else:
        # Structure: Flat fields + "player_stats": {"Name": {...}} + "shot_locations": [...]
        # LIVE GAME payload
        raw_date = get_nested_value(data, "date", "Date", "game_date")

        # Handle date logic for LIVE input
        if raw_date and re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            sort_date = raw_date
            parts = raw_date.split("-")
            display_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else:
            display_date = normalize_date_to_display(raw_date)
            sort_date = normalize_sort_date(raw_date)

        opponent = get_nested_value(data, "opponent", "Opponent", "vs", "versus")
        team_score = int(
            get_nested_value(data, "team_score", "TeamScore", "our_score", default=0)
        )
        opponent_score = int(
            get_nested_value(
                data, "opponent_score", "OpponentScore", "their_score", default=0
            )
        )
        game_type = get_nested_value(
            data, "game_type", "GameType", "type", default="Season"
        )
        source = "LIVE"

        # LIVE payload uses a Dict for player_stats, list for others
        player_stats_source = get_nested_value(
            data, "player_stats", "PlayerStats", "players", default={}
        )
        # Support both 'shot_locations' and 'shot_events' for LIVE format
        shot_events_source = get_nested_value(
            data, "shot_locations", "shot_events", "Shots", "shots", default=[]
        )
        game_events_source = get_nested_value(
            data, "game_events", "GameEvents", "events", "Events", default=[]
        )

    # Validate constraints
    if len(display_date) > 10:
        # Emergency truncation or fix to prevent DB crash
        # If it's 2026/01/2015 -> try to salvage or fail
        current_app.logger.warning(
            f"Date format too long: {display_date}. Attempting fix."
        )
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
        schema_version=schema_version,
    )
    db.session.add(game)
    db.session.flush()

    # --- Process Player Stats ---
    if is_nested_import:
        # List of dicts
        for p_data in player_stats_source:
            # Normalize player name key
            player_name = get_nested_value(
                p_data, "player_name", "PlayerName", "name", "Name", "player"
            )
            if not player_name:
                continue

            # Filter valid keys
            valid_keys = {
                c.name
                for c in PlayerStat.__table__.columns
                if c.name not in ("id", "game_id")
            }
            stat_kwargs = {k: v for k, v in p_data.items() if k in valid_keys}

            # Ensure player_name is set
            if "player_name" not in stat_kwargs:
                stat_kwargs["player_name"] = player_name

            stat = PlayerStat(game_id=game.id, **stat_kwargs)
            db.session.add(stat)
    else:
        # Dict of dicts (LIVE)
        for p_name, stats in player_stats_source.items():
            if not p_name:
                continue

            # Support legacy key names in player stats
            fgm = get_nested_value(stats, "fgm", "FGM", "fg", default=0)
            fga = get_nested_value(stats, "fga", "FGA", default=0)
            tpm = get_nested_value(stats, "tpm", "3PM", "tp", "three_pm", default=0)
            tpa = get_nested_value(stats, "tpa", "3PA", "three_pa", default=0)
            ftm = get_nested_value(stats, "ftm", "FTM", "ft", default=0)
            fta = get_nested_value(stats, "fta", "FTA", default=0)
            oreb = get_nested_value(stats, "oreb", "OREB", "orb", default=0)
            dreb = get_nested_value(stats, "dreb", "DREB", "drb", default=0)
            ast = get_nested_value(stats, "ast", "AST", "assists", default=0)
            tov = get_nested_value(stats, "tov", "TOV", "turnovers", "to", default=0)
            stl = get_nested_value(stats, "stl", "STL", "steals", default=0)
            blk = get_nested_value(stats, "blk", "BLK", "blocks", default=0)
            pf = get_nested_value(stats, "pf", "PF", "fouls", default=0)
            points = get_nested_value(stats, "points", "PTS", "pts", default=0)
            minutes = get_nested_value(stats, "minutes", "MIN", "min", default="00:00")
            plus_minus = get_nested_value(
                stats, "plus_minus", "+/-", "pm", "PlusMinus", default=0
            )

            fg_pct = (fgm / fga * 100) if fga > 0 else 0.0
            tp_pct = (tpm / tpa * 100) if tpa > 0 else 0.0
            ft_pct = (ftm / fta * 100) if fta > 0 else 0.0

            new_stat = PlayerStat(
                game_id=game.id,
                player_name=p_name,
                minutes=minutes,
                points=points,
                fgm=fgm,
                fga=fga,
                fg_percent=fg_pct,
                tpm=tpm,
                tpa=tpa,
                tp_percent=tp_pct,
                ftm=ftm,
                fta=fta,
                ft_percent=ft_pct,
                oreb=oreb,
                dreb=dreb,
                reb=oreb + dreb,
                ast=ast,
                tov=tov,
                stl=stl,
                blk=blk,
                pf=pf,
                plus_minus=int(plus_minus or 0),
            )
            db.session.add(new_stat)

    # --- Process Shot Events ---
    for s_data in shot_events_source:
        if is_nested_import:
            # List of dicts with DB keys
            valid_keys = {
                c.name
                for c in ShotEvent.__table__.columns
                if c.name not in ("id", "game_id", "play_id")
            }
            shot_kwargs = {k: v for k, v in s_data.items() if k in valid_keys}

            # Extract play_name from detail and create/find play
            play_id_nested = None
            detail_nested = s_data.get("detail")
            play_name_nested = extract_play_name_from_detail(detail_nested)
            if play_name_nested:
                play_nested = find_or_create_play(play_name_nested)
                if play_nested:
                    play_id_nested = play_nested.id

            shot = ShotEvent(game_id=game.id, play_id=play_id_nested, **shot_kwargs)
        else:
            # LIVE format - support legacy key names
            shooter = get_nested_value(
                s_data, "shooter", "player", "player_name", default=""
            )
            shot_type = get_nested_value(
                s_data, "type", "shot_type", "ShotType", default=""
            )
            points = int(get_nested_value(s_data, "points", "Points", "pts", default=0))
            result = get_nested_value(
                s_data, "result", "Result", "made", default="made"
            )
            play_id = get_nested_value(s_data, "play_id", "PlayId", "playId")
            x = get_nested_value(s_data, "x", "x_loc", "xLoc")
            y = get_nested_value(s_data, "y", "y_loc", "yLoc")
            q = get_nested_value(s_data, "quarter", "q", "period")

            validated_play_id = None
            if play_id:
                try:
                    validated_play_id = validate_play_id(play_id)
                except ValueError:
                    pass

            # If no valid play_id, try to extract play_name from detail and create/find play
            if not validated_play_id:
                detail_val = get_nested_value(s_data, "detail", "Detail")
                play_name = extract_play_name_from_detail(detail_val)
                if play_name:
                    play = find_or_create_play(play_name)
                    if play:
                        validated_play_id = play.id

            shot = ShotEvent(
                game_id=game.id,
                player_name=shooter.strip() if shooter else "",
                shot_type=shot_type.strip() if shot_type else "",
                result=result,
                points=points,
                x_loc=float(x) if x is not None else None,
                y_loc=float(y) if y is not None else None,
                quarter=int(q) if q is not None else None,
                play_id=validated_play_id,
            )
        db.session.add(shot)

    # --- Process Game Events ---
    for e_data in game_events_source:
        if is_nested_import:
            # List of dicts with DB keys
            valid_keys = {
                c.name
                for c in GameEvent.__table__.columns
                if c.name not in ("id", "game_id", "play_id")
            }
            event_kwargs = {k: v for k, v in e_data.items() if k in valid_keys}

            # Extract play_name from detail and create/find play
            play_id_nested = None
            detail_nested = e_data.get("detail")
            play_name_nested = extract_play_name_from_detail(detail_nested)
            if play_name_nested:
                play_nested = find_or_create_play(play_name_nested)
                if play_nested:
                    play_id_nested = play_nested.id

            event = GameEvent(game_id=game.id, play_id=play_id_nested, **event_kwargs)
        else:
            # LIVE format - support legacy key names

            event_type = get_nested_value(e_data, "type", "event_type", "EventType")
            player_name = get_nested_value(
                e_data, "player", "player_name", "PlayerName"
            )
            detail = get_nested_value(e_data, "detail", "Detail", "description")
            timestamp = get_nested_value(
                e_data, "timestamp", "time", "Timestamp", default=0
            )
            shot_attempt = get_nested_value(e_data, "shot_attempt", "ShotAttempt")
            play_id = get_nested_value(e_data, "play_id", "PlayId", "playId")

            # New timeline fields
            quarter = get_nested_value(e_data, "quarter", "q", "period")
            time_remaining = get_nested_value(
                e_data, "time_remaining", "timeRemaining", "time_remaining"
            )
            score_margin = get_nested_value(e_data, "score_margin", "scoreMargin")
            possession_number = get_nested_value(
                e_data, "possession_number", "possessionNumber"
            )
            game_seconds = get_nested_value(e_data, "game_seconds", "gameSeconds")
            x = get_nested_value(e_data, "x_loc", "x", "xLoc")
            y = get_nested_value(e_data, "y_loc", "y", "yLoc")

            validated_play_id = None
            if play_id:
                try:
                    validated_play_id = validate_play_id(play_id)
                except ValueError:
                    pass

            # If no valid play_id, try to extract play_name from detail and create/find play
            if not validated_play_id and detail:
                play_name = extract_play_name_from_detail(detail)
                if play_name:
                    play = find_or_create_play(play_name)
                    if play:
                        validated_play_id = play.id

            # Serialize detail if it's a dict
            if isinstance(detail, dict):
                detail = json.dumps(detail)

            event = GameEvent(
                game_id=game.id,
                event_type=event_type,
                player_name=player_name.strip() if player_name else None,
                detail=str(detail) if detail is not None else None,
                timestamp=int(timestamp) if timestamp else 0,
                shot_attempt=shot_attempt,
                play_id=validated_play_id,
                quarter=int(quarter) if quarter is not None else None,
                time_remaining=time_remaining,
                score_margin=int(score_margin) if score_margin is not None else None,
                possession_number=int(possession_number)
                if possession_number is not None
                else None,
                game_seconds=int(game_seconds) if game_seconds is not None else None,
                x_loc=float(x) if x is not None else None,
                y_loc=float(y) if y is not None else None,
            )
        db.session.add(event)

    db.session.commit()

    # Assign possession numbers to events (for lineup stats calculation)
    assign_possession_numbers(game.id)

    starting_lineup = get_nested_value(
        data, "starting_lineup", "starters", "startingLineup", default=None
    )

    # Process lineup segments if we have events and lineup tracking is enabled
    saved_events = (
        GameEvent.query.filter_by(game_id=game.id).order_by(GameEvent.timestamp).all()
    )

    # Only process lineups when explicitly enabled (non-retroactive)
    has_lineup_tracking = schema_version >= 2 or features.get("LINEUP_TRACKING", False)

    if saved_events and has_lineup_tracking:
        try:
            process_game_lineups(game.id, saved_events, starting_lineup)
        except Exception as e:
            current_app.logger.warning(f"Failed to process lineup segments: {e}")

    # Log schema version for debugging/monitoring
    current_app.logger.info(
        f"Game {game.id} saved with schema_version={schema_version}, "
        f"features={list(features.keys()) if features else 'none'}"
    )

    return game
