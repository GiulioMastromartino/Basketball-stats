import copy
import json
import re
from typing import Any, Dict, List, Optional

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
        return detail.get("play_name") or detail.get("playName") or detail.get("play")

    # If it's a string, try to parse it
    if isinstance(detail, str):
        # Try JSON parse first
        try:
            parsed = json.loads(detail)
            if isinstance(parsed, dict):
                return parsed.get("play_name") or parsed.get("playName") or parsed.get("play")
        except (json.JSONDecodeError, ValueError):
            pass

        # Try ast.literal_eval for Python dict strings like "{'play_id': 8, 'play_name': 'Personale'}"
        try:
            import ast

            parsed = ast.literal_eval(detail)
            if isinstance(parsed, dict):
                return parsed.get("play_name") or parsed.get("playName") or parsed.get("play")
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


def infer_zone_from_coords(x, y):
    """Infer shot zone from x, y coordinates.
    
    Court dimensions: x (0-500), y (0-470)
    - Rim: x near basket (around 250) and y close to baseline
    - Paint: inside the paint area
    - Midrange: between paint and 3-point line
    - Corner_3: corner 3-point shots
    - Above_Break_3: above the break 3-point shots
    """
    if x is None or y is None:
        return None
    
    # Court is 500 x 470 (normalized)
    # Basket is at approximately x=250
    
    # Corner 3: x < 50 or x > 450, and y < 150 (close to baseline)
    if (x < 50 or x > 450) and y < 150:
        return "Corner_3"
    
    # Above break 3: y > 300 (above the 3-point line)
    if y > 300:
        return "Above_Break_3"
    
    # Paint: x between 170-330 and y < 190 (inside paint)
    if 170 <= x <= 330 and y < 190:
        return "Paint"
    
    # Rim: very close to basket (x around 250, y < 100)
    if 220 <= x <= 280 and y < 100:
        return "Rim"
    
    # Midrange: everything else
    return "Midrange"


def _normalize_payload_plays(data, is_nested_import):
    """Extract payload-defined plays from explicit lists and embedded rescue refs."""
    play_entries = get_nested_value(data, "plays", "Plays", default=None)
    if play_entries is None and is_nested_import:
        play_entries = get_nested_value(data.get("game", {}), "plays", "Plays", default=[])

    normalized = []
    seen = set()

    def add_entry(play_id=None, play_name=None, play_type="Offense"):
        normalized_name = play_name.strip() if isinstance(play_name, str) else ""
        normalized_id = _safe_int(play_id)
        key = (normalized_id, normalized_name, play_type or "Offense")
        if normalized_id is None and not normalized_name:
            return
        if key in seen:
            return
        seen.add(key)
        payload = {"play_type": play_type or "Offense"}
        if normalized_id is not None:
            payload["id"] = normalized_id
        if normalized_name:
            payload["name"] = normalized_name
        normalized.append(payload)

    for entry in play_entries or []:
        if not isinstance(entry, dict):
            continue
        add_entry(
            get_nested_value(entry, "id", "play_id", "playId"),
            get_nested_value(entry, "name", "play_name", "playName"),
            get_nested_value(entry, "play_type", "playType", default="Offense"),
        )

    shot_events_source = get_nested_value(
        data, "shot_events", "shot_locations", "ShotEvents", "shots", "Shots", default=[]
    )
    game_events_source = get_nested_value(
        data, "game_events", "GameEvents", "events", "Events", default=[]
    )

    for shot in shot_events_source or []:
        if not isinstance(shot, dict):
            continue
        add_entry(
            get_nested_value(shot, "play_id", "playId"),
            get_nested_value(shot, "play_name", "playName")
            or extract_play_name_from_detail(get_nested_value(shot, "detail", "Detail")),
        )

    for event in game_events_source or []:
        if not isinstance(event, dict):
            continue
        detail = get_nested_value(event, "detail", "Detail")
        detail_name = extract_play_name_from_detail(detail)
        detail_id = None
        if isinstance(detail, dict):
            detail_id = get_nested_value(detail, "play_id", "playId")
        add_entry(
            get_nested_value(event, "play_id", "playId", default=detail_id),
            get_nested_value(event, "play_name", "playName", default=detail_name) or detail_name,
        )

    return normalized



def get_nested_value(data, *keys, default=None):
    """Get a value from a dict trying multiple possible key names."""
    for key in keys:
        if key in data:
            return data[key]
    return default


def _safe_int(value):
    """Best-effort integer coercion for imported timeline fields."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _clock_seconds_to_time_remaining(clock_seconds: Optional[int]) -> Optional[str]:
    """Convert elapsed quarter seconds to MM:SS remaining."""
    if clock_seconds is None:
        return None

    remaining = max(0, 600 - clock_seconds)
    minutes = remaining // 60
    seconds = remaining % 60
    return f"{minutes}:{seconds:02d}"


def _time_remaining_to_clock_seconds(time_remaining: Optional[str]) -> Optional[int]:
    """Convert MM:SS remaining to elapsed quarter seconds."""
    if not time_remaining or ":" not in str(time_remaining):
        return None
    try:
        minutes_str, seconds_str = str(time_remaining).split(":", 1)
        remaining = (int(minutes_str) * 60) + int(seconds_str)
    except (TypeError, ValueError):
        return None
    return max(0, 600 - remaining)


def _derive_timeline_from_quarter_clock(
    quarter: Optional[int], clock_seconds: Optional[int]
) -> Dict[str, Optional[int]]:
    """Derive absolute timeline fields from quarter-local clock seconds."""
    if quarter is None or clock_seconds is None:
        return {"game_seconds": None, "time_remaining": None}

    return {
        "game_seconds": ((quarter - 1) * 600) + clock_seconds,
        "time_remaining": _clock_seconds_to_time_remaining(clock_seconds),
    }


def _parse_detail_dict(detail: Any) -> Dict[str, Any]:
    """Parse detail payloads stored as dict/JSON/stringified dict."""
    if detail is None:
        return {}
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        try:
            parsed = json.loads(detail)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            import ast

            parsed = ast.literal_eval(detail)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, SyntaxError):
            return {}
    return {}


def _normalize_shot_family(event_type: Optional[str]) -> Optional[str]:
    """Map game event shot types to shot_events schema values."""
    if event_type == "SHOT_2PT":
        return "2pt"
    if event_type == "SHOT_3PT":
        return "3pt"
    if event_type in ("FT", "FT_MADE", "FT_MISS"):
        return "ft"
    return None


def _build_shot_import_records(
    shot_events_source: List[Dict[str, Any]], is_nested_import: bool
) -> List[Dict[str, Any]]:
    """Keep raw shot metadata for schema 4 event reconciliation."""
    records: List[Dict[str, Any]] = []

    for index, s_data in enumerate(shot_events_source):
        shooter = get_nested_value(
            s_data, "player_name", "player", "shooter", default=""
        )
        quarter = _safe_int(get_nested_value(s_data, "quarter", "q", "period"))
        clock_seconds = _safe_int(
            get_nested_value(s_data, "clockSeconds", "clock_seconds", "clock")
        )
        timestamp = _safe_int(get_nested_value(s_data, "timestamp", "time", default=0))
        shot_type = get_nested_value(s_data, "shot_type", "type", "ShotType", default="")
        result = get_nested_value(s_data, "result", "Result", "made")
        x = get_nested_value(s_data, "x_loc", "x", "xLoc")
        y = get_nested_value(s_data, "y_loc", "y", "yLoc")
        points = _safe_int(get_nested_value(s_data, "points", "Points", "pts", default=0))

        records.append(
            {
                "index": index,
                "shooter": shooter.strip().lower() if shooter else "",
                "quarter": quarter,
                "clock_seconds": clock_seconds,
                "timestamp": timestamp,
                "shot_type": shot_type.strip().lower() if shot_type else "",
                "result": result,
                "x_loc": float(x) if x is not None else None,
                "y_loc": float(y) if y is not None else None,
                "points": points or 0,
                "used": False,
            }
        )

    return records


def _build_raw_event_contexts(game_events_source: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize raw event timeline metadata for schema 4 gap filling."""
    contexts: List[Dict[str, Any]] = []

    for index, e_data in enumerate(game_events_source):
        quarter = _safe_int(get_nested_value(e_data, "quarter", "q", "period"))
        clock_seconds = _safe_int(
            get_nested_value(e_data, "clockSeconds", "clock_seconds", "clock")
        )
        game_seconds = _safe_int(get_nested_value(e_data, "game_seconds", "gameSeconds"))
        time_remaining = get_nested_value(
            e_data, "time_remaining", "timeRemaining", "TimeRemaining"
        )
        timestamp = _safe_int(get_nested_value(e_data, "timestamp", "time", default=0)) or 0
        score_margin = _safe_int(get_nested_value(e_data, "score_margin", "scoreMargin"))
        possession_number = _safe_int(
            get_nested_value(e_data, "possession_number", "possessionNumber")
        )

        if game_seconds is None or not time_remaining:
            derived = _derive_timeline_from_quarter_clock(quarter, clock_seconds)
            game_seconds = game_seconds if game_seconds is not None else derived["game_seconds"]
            time_remaining = time_remaining or derived["time_remaining"]

        contexts.append(
            {
                "index": index,
                "quarter": quarter,
                "clock_seconds": clock_seconds,
                "game_seconds": game_seconds,
                "time_remaining": time_remaining,
                "timestamp": timestamp,
                "score_margin": score_margin,
                "possession_number": possession_number,
            }
        )

    return contexts


def _match_schema4_shot_record(
    shot_records: List[Dict[str, Any]],
    player_name: Optional[str],
    quarter: Optional[int],
    event_type: Optional[str],
    timestamp: Optional[int],
    clock_seconds: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Match a team shot event to the best raw shot record deterministically."""
    normalized_player = player_name.strip().lower() if player_name else ""
    shot_family = _normalize_shot_family(event_type)

    candidates = [
        shot
        for shot in shot_records
        if not shot["used"]
        and shot["shooter"] == normalized_player
        and shot["quarter"] == quarter
        and shot["shot_type"] == shot_family
    ]
    if not candidates:
        return None

    exact_timestamp = [
        shot
        for shot in candidates
        if timestamp not in (None, 0)
        and shot["timestamp"] is not None
        and shot["timestamp"] == timestamp
    ]
    if len(exact_timestamp) > 1:
        return None
    if len(exact_timestamp) == 1:
        match = exact_timestamp[0]
        match["used"] = True
        return match

    exact_clock = [
        shot
        for shot in candidates
        if clock_seconds is not None
        and shot["clock_seconds"] is not None
        and shot["clock_seconds"] == clock_seconds
    ]
    if len(exact_clock) > 1:
        return None
    if len(exact_clock) == 1:
        match = exact_clock[0]
        match["used"] = True
        return match

    if len(candidates) != 1:
        return None

    match = candidates[0]
    match["used"] = True
    return match


def _build_safe_shot_backfill_matches(
    shot_records: List[Dict[str, Any]],
    game_events: List[GameEvent],
) -> Dict[GameEvent, int]:
    """Build a deterministic event->shot mapping for safe play_id backfill.

    Matching priority:
    1. exact quarter + shot family + player + timestamp
    2. exact quarter + shot family + player + clock_seconds

    Ambiguous matches are ignored instead of guessed.
    """
    event_to_shot = {}
    matched_shots = set()

    for event in game_events:
        if event.event_type not in ("SHOT_2PT", "SHOT_3PT"):
            continue
        if not event.play_id or not event.player_name:
            continue

        player_key = event.player_name.strip().lower()
        shot_family = _normalize_shot_family(event.event_type)
        if not shot_family:
            continue

        matched_index = getattr(event, "_matched_shot_index", None)
        if matched_index is not None:
            event_to_shot[event] = matched_index
            matched_shots.add(matched_index)
            continue

        candidates = [
            shot
            for shot in shot_records
            if shot["index"] not in matched_shots
            and shot["quarter"] == event.quarter
            and shot["shot_type"] == shot_family
            and shot["shooter"] == player_key
        ]
        if not candidates:
            continue

        exact_timestamp = [
            shot
            for shot in candidates
            if event.timestamp not in (None, 0)
            and shot["timestamp"] is not None
            and shot["timestamp"] == event.timestamp
        ]
        if len(exact_timestamp) == 1:
            chosen = exact_timestamp[0]
        elif len(exact_timestamp) > 1:
            continue
        else:
            event_clock_seconds = _time_remaining_to_clock_seconds(event.time_remaining)
            exact_clock = [
                shot
                for shot in candidates
                if event_clock_seconds is not None
                and shot["clock_seconds"] is not None
                and shot["clock_seconds"] == event_clock_seconds
            ]
            if len(exact_clock) != 1:
                continue
            chosen = exact_clock[0]

        matched_shots.add(chosen["index"])
        event_to_shot[event] = chosen["index"]

    return event_to_shot


def _nearest_raw_context(
    contexts: List[Dict[str, Any]],
    quarter: Optional[int],
    timestamp: Optional[int],
    clock_seconds: Optional[int],
    event_index: int,
) -> Optional[Dict[str, Any]]:
    """Pick the closest raw event with usable timeline metadata."""
    candidates = [
        ctx
        for ctx in contexts
        if ctx["index"] != event_index
        and ctx["quarter"] == quarter
        and (
            ctx["score_margin"] is not None
            or ctx["possession_number"] is not None
            or ctx["game_seconds"] is not None
            or ctx["time_remaining"] is not None
        )
    ]
    if not candidates:
        return None

    def _rank(candidate: Dict[str, Any]) -> tuple:
        ts_diff = abs(candidate["timestamp"] - timestamp) if candidate["timestamp"] and timestamp else 10**12
        clock_diff = (
            abs(candidate["clock_seconds"] - clock_seconds)
            if candidate["clock_seconds"] is not None and clock_seconds is not None
            else 10**6
        )
        return (ts_diff, clock_diff, abs(candidate["index"] - event_index))

    return min(candidates, key=_rank)


def _score_delta_for_event(event: GameEvent) -> int:
    """Return score-margin delta introduced by a single event."""
    if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
        return 2
    if event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
        return 3
    if event.event_type == "FT_MADE":
        return 1
    if event.event_type == "FT":
        return _parse_detail_dict(event.detail).get("ftm", 0) or 0
    if event.event_type == "OPP_SCORE":
        detail = _parse_detail_dict(event.detail)
        points = detail.get("points", 0)
        points = _safe_int(points)
        return -(points or 0)
    return 0


def _backfill_missing_score_margin(events: List[GameEvent]) -> None:
    """Fill missing score margins from the imported event sequence."""
    ordered = sorted(
        events,
        key=lambda event: (
            event.timestamp or 0,
            event.game_seconds if event.game_seconds is not None else 10**9,
        ),
    )

    current_margin = 0
    for event in ordered:
        if event.score_margin is None:
            current_margin += _score_delta_for_event(event)
            event.score_margin = current_margin
        else:
            current_margin = event.score_margin


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

    possession_number = 1
    last_ft_player = None
    ft_possession_active = False

    # Define ending events
    POSSESSION_ENDING = {"SHOT_2PT", "SHOT_3PT", "TURNOVER", "OPP_SCORE", "OPP_OREB"}
    FT_EVENTS = {"FT", "FT_MADE", "FT_MISS"}

    for event in events:
        # 1. Start new possession for new FT trip BEFORE assignment
        if event.event_type in FT_EVENTS:
            if not ft_possession_active or event.player_name != last_ft_player:
                if ft_possession_active or (not ft_possession_active and event.timestamp > events[0].timestamp):
                   possession_number += 1
                ft_possession_active = True
                last_ft_player = event.player_name
        else:
            # Any non-FT event after a FT sequence ends that FT possession trip
            if ft_possession_active and event.event_type not in ["SUB_IN", "SUB_OUT"]:
                ft_possession_active = False
                last_ft_player = None

        # 2. Assign current possession to the event
        event.possession_number = possession_number

        # 3. Increment AFTER possession-ending event (except FT which handles it at start)
        if event.event_type in POSSESSION_ENDING:
            possession_number += 1
            ft_possession_active = False
            last_ft_player = None

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
    
    # For re-imports: remove IDs from data to prevent SQLAlchemy from updating existing records
    # This ensures new records are created instead of updating existing ones
    if is_nested_import and "game" in data:
        data = copy.deepcopy(data)
        if "game" in data and isinstance(data["game"], dict):
            data["game"].pop("id", None)
        for key in ["game_events", "shot_events", "player_stats"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    if isinstance(item, dict):
                        item.pop("id", None)
                        item.pop("game_id", None)
                        item.pop("lineup_segment_id", None)

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
        
        # Override schema version if provided in the nested game object
        schema_version = get_nested_value(game_data, "schema_version", "schemaversion", default=schema_version)

        # Player stats list - support multiple key names
        player_stats_source = get_nested_value(
            data, "player_stats", "PlayerStats", "players", "Players", default=[]
        )
        # Support 'shot_locations' in nested format too (often found in rescue files)
        shot_events_source = get_nested_value(
            data, "shot_events", "shot_locations", "ShotEvents", "shots", "Shots", default=[]
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
        
        # Override schema version if provided in flat payload
        schema_version = get_nested_value(data, "schema_version", "schemaversion", default=schema_version)

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

    # Clean schema version (handle string like "3.0")
    try:
        if isinstance(schema_version, str):
            schema_version = float(schema_version)
        schema_version = int(schema_version)
    except:
        schema_version = 1

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

    # --- Performance Optimization: Play Cache ---
    # Pre-fetch all plays and sync payload-provided plays before ingesting events.
    from core.models import Play
    existing_plays = Play.query.all()
    play_cache = {p.name: p.id for p in existing_plays}
    play_id_cache = {p.id: p.id for p in existing_plays}

    payload_plays = _normalize_payload_plays(data, is_nested_import)
    for payload_play in payload_plays:
        if not isinstance(payload_play, dict):
            continue
        payload_play_id = _safe_int(get_nested_value(payload_play, "id", "play_id", "playId"))
        payload_play_name = get_nested_value(payload_play, "name", "play_name", "playName")
        payload_play_name = payload_play_name.strip() if isinstance(payload_play_name, str) else ""
        payload_play_type = get_nested_value(payload_play, "play_type", "playType", default="Offense") or "Offense"

        existing_by_name = Play.query.filter_by(name=payload_play_name).first() if payload_play_name else None
        existing_by_id = Play.query.get(payload_play_id) if payload_play_id else None

        if existing_by_id:
            synced_play = existing_by_id
        elif existing_by_name:
            synced_play = existing_by_name
        elif payload_play_name:
            synced_play = Play(name=payload_play_name, play_type=payload_play_type, source="imported")
            db.session.add(synced_play)
            db.session.flush()
        else:
            continue

        play_cache[synced_play.name] = synced_play.id
        play_id_cache[synced_play.id] = synced_play.id
        if payload_play_id:
            play_id_cache[payload_play_id] = synced_play.id

    def get_cached_play_id(name):
        if not name: return None
        name = name.strip()
        if name in play_cache:
            return play_cache[name]
        
        # Create new if not in cache
        new_p = Play(name=name, play_type="Offense", source="imported")
        db.session.add(new_p)
        db.session.flush()
        play_cache[name] = new_p.id
        play_id_cache[new_p.id] = new_p.id
        return new_p.id

    def get_cached_play_id_by_id(play_id, play_name=None):
        if not play_id:
            return None
        try:
            play_id_int = int(play_id)
        except (ValueError, TypeError):
            return None
        if play_id_int in play_id_cache:
            return play_id_cache[play_id_int]

        existing = Play.query.get(play_id_int)
        if existing:
            play_id_cache[play_id_int] = existing.id
            play_cache.setdefault(existing.name, existing.id)
            return existing.id
        name = (play_name or "").strip()
        if not name:
            return None
        new_p = Play(name=name, play_type="Offense", source="imported")
        db.session.add(new_p)
        db.session.flush()
        play_id_cache[new_p.id] = new_p.id
        play_cache.setdefault(new_p.name, new_p.id)
        return new_p.id

    # Objects to batch insert
    all_player_stats = []
    all_shot_events = []
    all_game_events = []

    # --- Process Player Stats ---
    # Robustly handle both dict-based (Live/Rescue) and list-based (Export) player stats
    if isinstance(player_stats_source, dict):
        # LIVE or RESCUE format: {"Player Name": {stats...}}
        for p_name, stats in player_stats_source.items():
            if not p_name: continue
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
            plus_minus = get_nested_value(stats, "plus_minus", "+/-", "pm", "PlusMinus", default=0)
            reb_conceded = get_nested_value(
                stats,
                "reb_conceded",
                "REB_CONCEDED",
                "rebConceded",
                "rebounds_conceded",
                default=0,
            )

            fg_pct = (fgm / fga * 100) if fga > 0 else 0.0
            tp_pct = (tpm / tpa * 100) if tpa > 0 else 0.0
            ft_pct = (ftm / fta * 100) if fta > 0 else 0.0

            all_player_stats.append(PlayerStat(
                game_id=game.id, player_name=p_name, minutes=minutes, points=points,
                fgm=fgm, fga=fga, fg_percent=fg_pct, tpm=tpm, tpa=tpa, tp_percent=tp_pct,
                ftm=ftm, fta=fta, ft_percent=ft_pct, oreb=oreb, dreb=dreb, reb=oreb + dreb,
                ast=ast, tov=tov, stl=stl, blk=blk, pf=pf,
                plus_minus=int(plus_minus or 0),
                reb_conceded=int(reb_conceded or 0),
            ))
    else:
        # EXPORT format: [{"name": "Player Name", ...}]
        for p_data in player_stats_source:
            player_name = get_nested_value(p_data, "player_name", "PlayerName", "name", "Name", "player")
            if not player_name: continue
            valid_keys = {c.name for c in PlayerStat.__table__.columns if c.name not in ("id", "game_id")}
            stat_kwargs = {k: v for k, v in p_data.items() if k in valid_keys}
            if "player_name" not in stat_kwargs: stat_kwargs["player_name"] = player_name
            all_player_stats.append(PlayerStat(game_id=game.id, **stat_kwargs))

    db.session.add_all(all_player_stats)

    # --- Process Shot Events ---
    for s_data in shot_events_source:
        if is_nested_import:
            # First try mapping exact database keys
            shooter = get_nested_value(s_data, "player_name", "player", "shooter", default="")
            shot_type = get_nested_value(s_data, "shot_type", "type", "ShotType", default="")
            pts = int(get_nested_value(s_data, "points", "Points", "pts", default=0))
            result = get_nested_value(s_data, "result", "Result", "made", default="made")
            x = get_nested_value(s_data, "x_loc", "x", "xLoc")
            y = get_nested_value(s_data, "y_loc", "y", "yLoc")
            q = get_nested_value(s_data, "quarter", "q", "period")
            play_id_val = get_nested_value(s_data, "play_id", "playId")
            play_name = get_nested_value(s_data, "play_name", "playName")
            if not play_name:
                play_name = extract_play_name_from_detail(get_nested_value(s_data, "detail", "Detail"))
            play_id_nested = (
                get_cached_play_id_by_id(play_id_val, play_name)
                if play_id_val
                else get_cached_play_id(play_name)
            )
            
            all_shot_events.append(ShotEvent(
                game_id=game.id, player_name=shooter.strip() if shooter else "",
                shot_type=shot_type.strip() if shot_type else "", result=result, points=pts,
                x_loc=float(x) if x is not None else None, y_loc=float(y) if y is not None else None,
                quarter=int(q) if q is not None else None, play_id=play_id_nested,
            ))
        else:
            shooter = get_nested_value(s_data, "shooter", "player", "player_name", default="")
            shot_type = get_nested_value(s_data, "type", "shot_type", "ShotType", default="")
            pts = int(get_nested_value(s_data, "points", "Points", "pts", default=0))
            result = get_nested_value(s_data, "result", "Result", "made", default="made")
            x = get_nested_value(s_data, "x", "x_loc", "xLoc")
            y = get_nested_value(s_data, "y", "y_loc", "yLoc")
            q = get_nested_value(s_data, "quarter", "q", "period")
            play_id_val = get_nested_value(s_data, "play_id", "playId")
            p_name = get_nested_value(s_data, "play_name", "playName")
            if not p_name:
                p_name = extract_play_name_from_detail(get_nested_value(s_data, "detail", "Detail"))
            v_play_id = (
                get_cached_play_id_by_id(play_id_val, p_name)
                if play_id_val
                else get_cached_play_id(p_name)
            )

            all_shot_events.append(ShotEvent(
                game_id=game.id, player_name=shooter.strip() if shooter else "",
                shot_type=shot_type.strip() if shot_type else "", result=result, points=pts,
                x_loc=float(x) if x is not None else None, y_loc=float(y) if y is not None else None,
                quarter=int(q) if q is not None else None, play_id=v_play_id,
            ))
    
    db.session.add_all(all_shot_events)

    # Keep raw source metadata for schema 4 reconciliation before persisting game events.
    shot_import_records = _build_shot_import_records(shot_events_source, is_nested_import)
    shot_results_lookup = {}
    for shot in shot_import_records:
        key = (shot["shooter"], shot["quarter"], shot["shot_type"])
        shot_results_lookup.setdefault(key, []).append(shot["result"])

    raw_event_contexts = _build_raw_event_contexts(game_events_source)
    is_schema4 = schema_version >= 4
    unmatched_schema4_shots = 0

    # We need to store original shot event data, will do this after game_events created
    
    # --- Process Game Events ---
    for event_index, e_data in enumerate(game_events_source):
        if is_nested_import:
            event_type = get_nested_value(e_data, "event_type", "type", "EventType")
            player_name = get_nested_value(e_data, "player_name", "player", "PlayerName")
            detail = get_nested_value(e_data, "detail", "Detail", "description")
            timestamp = get_nested_value(e_data, "timestamp", "time", "Timestamp", default=0)
            quarter = get_nested_value(e_data, "quarter", "q", "period")
            quarter = _safe_int(quarter)
            clock_seconds = _safe_int(
                get_nested_value(e_data, "clockSeconds", "clock_seconds", "clock")
            )
            shot_attempt = get_nested_value(e_data, "shot_attempt", "ShotAttempt")
            time_remaining = get_nested_value(e_data, "time_remaining", "timeRemaining", "time_remaining")
            score_margin = get_nested_value(e_data, "score_margin", "scoreMargin")
            possession_number = get_nested_value(e_data, "possession_number", "possessionNumber")
            game_seconds = get_nested_value(e_data, "game_seconds", "gameSeconds")
            x = get_nested_value(e_data, "x_loc", "x", "xLoc")
            y = get_nested_value(e_data, "y_loc", "y", "yLoc")
            zone = get_nested_value(e_data, "zone", "Zone")
            
            # Extract zone/location from detail field if not at top level
            # (e.g., OPP_SCORE events store this in detail JSON)
            detail_parsed = _parse_detail_dict(detail)
            
            # Override with detail values if top-level values are missing
            if detail_parsed:
                if x is None:
                    x = detail_parsed.get("x_loc") or detail_parsed.get("x")
                if y is None:
                    y = detail_parsed.get("y_loc") or detail_parsed.get("y")
                if zone is None:
                    zone = detail_parsed.get("zone")
                
                # If still no zone, infer from coordinates
                if zone is None:
                    zone = infer_zone_from_coords(x, y)
            
            # Ignore IDs from export - create new records for re-import
            # (prevents SQLAlchemy from trying to update existing records)
            _event_id = get_nested_value(e_data, "id")
            _event_game_id = get_nested_value(e_data, "game_id")
            _lineup_segment_id = get_nested_value(e_data, "lineup_segment_id")
            
            play_id_val = get_nested_value(e_data, "play_id", "playId")
            play_name_val = get_nested_value(e_data, "play_name", "playName")

            # Use play_id directly if provided, otherwise use play_name, otherwise extract from detail
            if play_id_val:
                p_id = get_cached_play_id_by_id(play_id_val, play_name_val)
            elif play_name_val:
                p_id = get_cached_play_id(play_name_val)
            else:
                p_id = get_cached_play_id(extract_play_name_from_detail(detail))
            
            matched_shot = None
            if is_schema4 and event_type in ("SHOT_2PT", "SHOT_3PT"):
                matched_shot = _match_schema4_shot_record(
                    shot_import_records,
                    player_name,
                    quarter,
                    event_type,
                    _safe_int(timestamp),
                    clock_seconds,
                )
                if matched_shot is None:
                    unmatched_schema4_shots += 1

            if matched_shot is not None:
                if shot_attempt is None:
                    shot_attempt = matched_shot["result"]
                if x is None:
                    x = matched_shot["x_loc"]
                if y is None:
                    y = matched_shot["y_loc"]
                if zone is None:
                    zone = infer_zone_from_coords(x, y)
                if timestamp in (None, 0) and matched_shot["timestamp"]:
                    timestamp = matched_shot["timestamp"]
                if clock_seconds is None:
                    clock_seconds = matched_shot["clock_seconds"]

            if shot_attempt is None and event_type == "FT":
                ftm = detail_parsed.get("ftm", 0)
                shot_attempt = "made" if ftm > 0 else "missed"
            elif shot_attempt is None and event_type in ("SHOT_2PT", "SHOT_3PT") and player_name:
                key = (
                    player_name.strip().lower(),
                    quarter,
                    _normalize_shot_family(event_type),
                )
                if shot_results_lookup.get(key):
                    shot_attempt = shot_results_lookup[key][0]

            game_seconds = _safe_int(game_seconds)
            score_margin = _safe_int(score_margin)
            possession_number = _safe_int(possession_number)

            if game_seconds is None or not time_remaining:
                derived = _derive_timeline_from_quarter_clock(quarter, clock_seconds)
                game_seconds = game_seconds if game_seconds is not None else derived["game_seconds"]
                time_remaining = time_remaining or derived["time_remaining"]

            nearby_context = _nearest_raw_context(
                raw_event_contexts,
                quarter,
                _safe_int(timestamp),
                clock_seconds,
                event_index,
            )
            if nearby_context:
                if game_seconds is None:
                    game_seconds = nearby_context["game_seconds"]
                if not time_remaining:
                    time_remaining = nearby_context["time_remaining"]
                if score_margin is None:
                    score_margin = nearby_context["score_margin"]
                if possession_number is None:
                    possession_number = nearby_context["possession_number"]

            if isinstance(detail, dict):
                detail = json.dumps(detail)

            game_event = GameEvent(
                game_id=game.id, event_type=event_type,
                player_name=player_name.strip() if player_name else None,
                detail=str(detail) if detail is not None else None,
                timestamp=int(timestamp) if timestamp else 0,
                shot_attempt=shot_attempt, play_id=p_id,
                quarter=quarter,
                time_remaining=time_remaining,
                score_margin=score_margin,
                possession_number=possession_number,
                game_seconds=game_seconds,
                x_loc=float(x) if x is not None else None,
                y_loc=float(y) if y is not None else None,
                zone=zone,
            )
            if matched_shot is not None:
                game_event._matched_shot_index = matched_shot["index"]
            all_game_events.append(game_event)
        else:
            event_type = get_nested_value(e_data, "type", "event_type", "EventType")
            player_name = get_nested_value(e_data, "player", "player_name", "PlayerName")
            detail = get_nested_value(e_data, "detail", "Detail", "description")
            timestamp = get_nested_value(e_data, "timestamp", "time", "Timestamp", default=0)
            quarter = get_nested_value(e_data, "quarter", "q", "period")
            quarter = _safe_int(quarter)
            clock_seconds = _safe_int(
                get_nested_value(e_data, "clockSeconds", "clock_seconds", "clock")
            )
            shot_attempt = get_nested_value(e_data, "shot_attempt", "ShotAttempt")
            time_remaining = get_nested_value(e_data, "time_remaining", "timeRemaining", "time_remaining")
            score_margin = get_nested_value(e_data, "score_margin", "scoreMargin")
            possession_number = get_nested_value(e_data, "possession_number", "possessionNumber")
            game_seconds = get_nested_value(e_data, "game_seconds", "gameSeconds")
            x = get_nested_value(e_data, "x_loc", "x", "xLoc")
            y = get_nested_value(e_data, "y_loc", "y", "yLoc")
            zone = get_nested_value(e_data, "zone", "Zone")
            detail_parsed = _parse_detail_dict(detail)

            matched_shot = None
            if is_schema4 and event_type in ("SHOT_2PT", "SHOT_3PT"):
                matched_shot = _match_schema4_shot_record(
                    shot_import_records,
                    player_name,
                    quarter,
                    event_type,
                    _safe_int(timestamp),
                    clock_seconds,
                )
                if matched_shot is None:
                    unmatched_schema4_shots += 1

            if matched_shot is not None:
                if shot_attempt is None:
                    shot_attempt = matched_shot["result"]
                if x is None:
                    x = matched_shot["x_loc"]
                if y is None:
                    y = matched_shot["y_loc"]
                if zone is None:
                    zone = infer_zone_from_coords(x, y)
                if timestamp in (None, 0) and matched_shot["timestamp"]:
                    timestamp = matched_shot["timestamp"]
                if clock_seconds is None:
                    clock_seconds = matched_shot["clock_seconds"]

            if shot_attempt is None and event_type == "FT":
                ftm = detail_parsed.get("ftm", 0)
                shot_attempt = "made" if ftm > 0 else "missed"
            elif shot_attempt is None and event_type in ("SHOT_2PT", "SHOT_3PT") and player_name:
                key = (
                    player_name.strip().lower(),
                    quarter,
                    _normalize_shot_family(event_type),
                )
                if shot_results_lookup.get(key):
                    shot_attempt = shot_results_lookup[key][0]

            game_seconds = _safe_int(game_seconds)
            score_margin = _safe_int(score_margin)
            possession_number = _safe_int(possession_number)

            if game_seconds is None or not time_remaining:
                derived = _derive_timeline_from_quarter_clock(quarter, clock_seconds)
                game_seconds = game_seconds if game_seconds is not None else derived["game_seconds"]
                time_remaining = time_remaining or derived["time_remaining"]

            nearby_context = _nearest_raw_context(
                raw_event_contexts,
                quarter,
                _safe_int(timestamp),
                clock_seconds,
                event_index,
            )
            if nearby_context:
                if game_seconds is None:
                    game_seconds = nearby_context["game_seconds"]
                if not time_remaining:
                    time_remaining = nearby_context["time_remaining"]
                if score_margin is None:
                    score_margin = nearby_context["score_margin"]
                if possession_number is None:
                    possession_number = nearby_context["possession_number"]

            play_id_val = get_nested_value(e_data, "play_id", "playId")
            play_name_val = get_nested_value(e_data, "play_name", "playName")
            if play_id_val:
                v_p_id = get_cached_play_id_by_id(play_id_val, play_name_val)
            elif play_name_val:
                v_p_id = get_cached_play_id(play_name_val)
            else:
                v_p_id = get_cached_play_id(extract_play_name_from_detail(detail))
            if isinstance(detail, dict):
                detail = json.dumps(detail)

            game_event = GameEvent(
                game_id=game.id, event_type=event_type,
                player_name=player_name.strip() if player_name else None,
                detail=str(detail) if detail is not None else None,
                timestamp=int(timestamp) if timestamp else 0,
                shot_attempt=shot_attempt, play_id=v_p_id,
                quarter=quarter,
                time_remaining=time_remaining,
                score_margin=score_margin,
                possession_number=possession_number,
                game_seconds=game_seconds,
                x_loc=float(x) if x is not None else None,
                y_loc=float(y) if y is not None else None,
                zone=zone,
            )
            if matched_shot is not None:
                game_event._matched_shot_index = matched_shot["index"]
            all_game_events.append(game_event)

    _backfill_missing_score_margin(all_game_events)
    
    db.session.add_all(all_game_events)

    if unmatched_schema4_shots:
        current_app.logger.warning(
            "Schema 4 import for game %s left %s shot events unmatched",
            game.id,
            unmatched_schema4_shots,
        )
    
    safe_backfill_matches = _build_safe_shot_backfill_matches(
        shot_import_records,
        all_game_events,
    )
    for game_event, shot_index in safe_backfill_matches.items():
        if 0 <= shot_index < len(all_shot_events):
            shot_event = all_shot_events[shot_index]
            if not shot_event.play_id:
                shot_event.play_id = game_event.play_id
    
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

    # Handle SHOT_ZONES and PLAY_TRACKING feature flags
    has_shot_zones = schema_version >= 3 or features.get("SHOT_ZONES", False)
    has_play_tracking = schema_version >= 3 or features.get("PLAY_TRACKING", False)

    # Log schema version for debugging/monitoring
    current_app.logger.info(
        f"Game {game.id} saved with schema_version={schema_version}, "
        f"features={list(features.keys()) if features else 'none'}, "
        f"has_shot_zones={has_shot_zones}, has_play_tracking={has_play_tracking}"
    )

    return game
