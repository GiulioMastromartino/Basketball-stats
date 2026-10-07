import copy
import json
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.models import Game, PlayerStat, ShotEvent, GameEvent, Play, db
from core.services.lineup_service import process_game_lineups, resolve_team_id
from core.services.season_service import resolve_season_id
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
    if isinstance(x, bool) or isinstance(y, bool):
        return None
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
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
    if not isinstance(data, dict):
        return default
    for key in keys:
        if key in data:
            return data[key]
    return default


def _safe_int(value):
    """Best-effort integer coercion for imported timeline fields."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _safe_float(value):
    """Best-effort float coercion; returns None on garbage, never crashes."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


_VALID_GAME_TYPES = {"Season", "Friendly", "Playoff", "Tournament"}


def _parse_schema_version(value):
    """Strictly parse schema_version into 1..4; raise ValueError otherwise."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return 1
    if isinstance(value, bool):
        raise ValueError("Invalid schema_version: must be 1..4")
    try:
        if isinstance(value, str):
            parsed = int(float(value.strip()))
        elif isinstance(value, float):
            parsed = int(value)
        else:
            parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid schema_version: must be 1..4")
    if parsed < 1 or parsed > 4:
        raise ValueError("Invalid schema_version: must be 1..4")
    return parsed


def _normalize_game_type(value):
    """None-safe allowlisted game_type truncated to the DB column width."""
    if value is None:
        return "Season"
    text = value.strip() if isinstance(value, str) else str(value).strip()
    if not text:
        return "Season"
    text = text[:20]
    if text not in _VALID_GAME_TYPES:
        return "Season"
    return text


def _coerce_score(value):
    """Coerce a score via _safe_int with >=0 clamp; garbage becomes 0."""
    coerced = _safe_int(value)
    if coerced is None:
        return 0
    return max(0, coerced)


def _validate_game_dates(raw_date):
    """Validate raw date with datetime; return (display_date, sort_date).

    Rejects impossible month/day and raises ValueError instead of
    silently truncating overlong strings.
    """
    if raw_date is None:
        raise ValueError("Game date is required")
    raw_str = str(raw_date).strip()
    if not raw_str:
        raise ValueError("Game date is required")

    if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}$", raw_str):
        try:
            if "-" in raw_str:
                parsed = datetime.strptime(raw_str, "%Y-%m-%d")
            else:
                parsed = datetime.strptime(raw_str, "%Y/%m/%d")
        except ValueError:
            raise ValueError(f"Invalid game date: {raw_str}")
        sort_date = f"{parsed.year:04d}-{parsed.month:02d}-{parsed.day:02d}"
        display_date = f"{parsed.day:02d}-{parsed.month:02d}-{parsed.year:04d}"
        return display_date, sort_date

    match = re.match(r"^(\d{2})[-/](\d{2})[-/](\d{4})$", raw_str)
    if match:
        day_s, month_s, year_s = match.groups()
        try:
            parsed = datetime(int(year_s), int(month_s), int(day_s))
        except ValueError:
            raise ValueError(f"Invalid game date: {raw_str}")
        sort_date = f"{parsed.year:04d}-{parsed.month:02d}-{parsed.day:02d}"
        display_date = normalize_date_to_display(raw_str)
        if not re.match(r"^\d{2}/\d{2}/\d{4}$", display_date):
            display_date = f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year:04d}"
        return display_date, sort_date

    raise ValueError(f"Invalid game date: {raw_str}")


def _validate_minutes(value):
    """Validate MM:SS minutes; garbage becomes '00:00', never crashes."""
    if value is None:
        return "00:00"
    text = value.strip()[:10] if isinstance(value, str) else str(value).strip()[:10]
    if re.match(r"^\d{1,3}:\d{2}$", text):
        try:
            _mm, _ss = text.split(":", 1)
            if 0 <= int(_ss) < 60:
                return text
        except (TypeError, ValueError):
            pass
        return "00:00"
    return "00:00"


def _normalize_shot_type(value):
    """Normalize shot_type; None-safe, lowercased, DB-width truncated."""
    if value is None:
        return ""
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text.strip().lower()[:10]


def _normalize_shot_result(value):
    """Normalize shot result; defaults to None (not 'made'), never crashes."""
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    return text[:10]


def _normalize_play_lookup(name):
    """Normalize a play name for lookup: strip + collapse whitespace.

    Lookup is case-preserving (display name keeps its case); only
    surrounding whitespace and repeated internal spaces are collapsed
    so "  Horns   Twist " and "Horns Twist" resolve to the same key.
    Returns "" for non-string / empty / whitespace-only input.
    """
    if not isinstance(name, str):
        return ""
    return " ".join(name.strip().split())


def _create_scoped_play(team_id, display_name, play_type="Offense"):
    """Create a team-scoped Play, tolerating concurrent-create races.

    Uses a SAVEPOINT (begin_nested) so an IntegrityError only rolls back
    the single Play insert, not the enclosing game import. On conflict,
    re-SELECTs the team-scoped row and returns it. Never falls back to a
    cross-team row: if the scoped SELECT finds nothing (e.g. legacy
    global UNIQUE on plays.name blocks a cross-team duplicate), returns
    None so callers store play_id=None instead of hijacking another
    team's Play. Callers must already have strip-guarded display_name.
    """
    from sqlalchemy.exc import IntegrityError

    if not display_name:
        return None
    try:
        with db.session.begin_nested():
            new_play = Play(
                name=display_name,
                play_type=play_type or "Offense",
                source="imported",
                team_id=team_id,
            )
            db.session.add(new_play)
            db.session.flush()
        return new_play
    except IntegrityError:
        existing = Play.query.filter_by(team_id=team_id, name=display_name).first()
        if existing is not None:
            return existing
        try:
            current_app.logger.warning(
                "Play create conflict for team %s name %r without scoped row; skipping",
                team_id,
                display_name,
            )
        except Exception:
            pass
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

    source_list = shot_events_source if isinstance(shot_events_source, list) else []
    for s_data in source_list:
        if not isinstance(s_data, dict):
            continue
        shooter = get_nested_value(
            s_data, "player_name", "player", "shooter", default=""
        )
        quarter = _safe_int(get_nested_value(s_data, "quarter", "q", "period"))
        clock_seconds = _safe_int(
            get_nested_value(s_data, "clockSeconds", "clock_seconds", "clock")
        )
        timestamp = _safe_int(get_nested_value(s_data, "timestamp", "time", default=0))
        shot_type_raw = get_nested_value(s_data, "shot_type", "type", "ShotType", default="")
        result_raw = get_nested_value(s_data, "result", "Result", "made")
        x = get_nested_value(s_data, "x_loc", "x", "xLoc")
        y = get_nested_value(s_data, "y_loc", "y", "yLoc")
        points = _safe_int(get_nested_value(s_data, "points", "Points", "pts", default=0))

        shooter_norm = shooter.strip().lower() if isinstance(shooter, str) else ""
        shot_type_norm = _normalize_shot_type(shot_type_raw)
        result_norm = _normalize_shot_result(result_raw)

        records.append(
            {
                "index": len(records),
                "shooter": shooter_norm,
                "quarter": quarter,
                "clock_seconds": clock_seconds,
                "timestamp": timestamp,
                "shot_type": shot_type_norm,
                "result": result_norm,
                "x_loc": _safe_float(x),
                "y_loc": _safe_float(y),
                "points": max(0, points) if points is not None else 0,
                "used": False,
            }
        )

    return records


def _build_raw_event_contexts(game_events_source: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize raw event timeline metadata for schema 4 gap filling."""
    contexts: List[Dict[str, Any]] = []

    source_list = game_events_source if isinstance(game_events_source, list) else []
    for index, e_data in enumerate(source_list):
        if not isinstance(e_data, dict):
            continue
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
    normalized_player = player_name.strip().lower() if isinstance(player_name, str) else ""
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

        player_key = event.player_name.strip().lower() if isinstance(event.player_name, str) else ""
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
        ftm_raw = _parse_detail_dict(event.detail).get("ftm", 0)
        ftm_val = _safe_int(ftm_raw)
        return ftm_val if ftm_val is not None else 0
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


def create_game_from_live_data(data, team_id: int = None, season_id: int = None):
    """
    Creates a new Game, PlayerStats, ShotEvents, and GameEvents from the JSON data payload.
    Validates all play IDs before database insertion.
    Handles 'IMPORT_JSON' style structure (nested objects) vs 'LIVE' style (flat structure).
    Also supports legacy key name variations for backwards compatibility.
    """
    if not isinstance(data, dict) or not data:
        raise ValueError("No data received")

    # team_id is required by the schema; fall back to the first team so
    # scripts/tests without team context keep working (routes pass it explicitly).
    team_id = resolve_team_id(team_id)

    # Extract format metadata for post-processing decisions
    schema_version = _parse_schema_version(data.get("schema_version", 1))
    raw_features = data.get("features")
    features = raw_features if isinstance(raw_features, dict) else {}

    # Detect structure type (Nested 'game' object vs Flat)
    is_nested_import = isinstance(data.get("game"), dict)

    # For re-imports: remove IDs from data to prevent SQLAlchemy from updating existing records
    # This ensures new records are created instead of updating existing ones
    if is_nested_import:
        data = copy.deepcopy(data)
        if isinstance(data.get("game"), dict):
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

        # Strict date validation: coerce via str().strip(), reject
        # impossible month/day via datetime, raise instead of truncating.
        display_date, sort_date = _validate_game_dates(raw_date)

        opponent_raw = get_nested_value(game_data, "opponent", "Opponent", "vs", "versus")
        opponent = opponent_raw.strip() if isinstance(opponent_raw, str) else (
            str(opponent_raw).strip() if opponent_raw is not None else ""
        )
        if not opponent:
            raise ValueError("Opponent is required")
        if len(opponent) > 100:
            raise ValueError("Opponent must be 1..100 characters")
        team_score = _coerce_score(
            get_nested_value(
                game_data, "team_score", "TeamScore", "our_score", default=0
            )
        )
        opponent_score = _coerce_score(
            get_nested_value(
                game_data, "opponent_score", "OpponentScore", "their_score", default=0
            )
        )
        game_type = _normalize_game_type(
            get_nested_value(
                game_data, "game_type", "GameType", "type", default="Season"
            )
        )
        source = "IMPORT_JSON"

        # Override schema version if provided in the nested game object
        schema_version = _parse_schema_version(
            get_nested_value(game_data, "schema_version", "schemaversion", default=schema_version)
        )

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

        # Strict date validation: coerce via str().strip(), reject
        # impossible month/day via datetime, raise instead of truncating.
        display_date, sort_date = _validate_game_dates(raw_date)

        opponent_raw = get_nested_value(data, "opponent", "Opponent", "vs", "versus")
        opponent = opponent_raw.strip() if isinstance(opponent_raw, str) else (
            str(opponent_raw).strip() if opponent_raw is not None else ""
        )
        if not opponent:
            raise ValueError("Opponent is required")
        if len(opponent) > 100:
            raise ValueError("Opponent must be 1..100 characters")
        team_score = _coerce_score(
            get_nested_value(data, "team_score", "TeamScore", "our_score", default=0)
        )
        opponent_score = _coerce_score(
            get_nested_value(
                data, "opponent_score", "OpponentScore", "their_score", default=0
            )
        )
        game_type = _normalize_game_type(
            get_nested_value(
                data, "game_type", "GameType", "type", default="Season"
            )
        )
        source = "LIVE"

        # Override schema version if provided in flat payload
        schema_version = _parse_schema_version(
            get_nested_value(data, "schema_version", "schemaversion", default=schema_version)
        )

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

    # Duplicate guard mirroring upload_game CSV/PDF/JSON checks so the
    # route maps this ValueError to 400/409 instead of double-importing.
    existing_game = Game.query.filter_by(
        team_id=team_id, sort_date=sort_date, opponent=opponent
    ).first()
    if existing_game:
        raise ValueError("Game already exists")

    # Create Game
    game = Game(
        team_id=team_id,
        date=display_date,
        opponent=opponent,
        team_score=team_score,
        opponent_score=opponent_score,
        result="W" if team_score > opponent_score else "L",
        game_type=game_type,
        sort_date=sort_date,
        source=source,
        schema_version=schema_version,
        season_id=resolve_season_id(team_id, season_id, sort_date),
    )
    db.session.add(game)
    db.session.flush()

    # --- Performance Optimization: Play Cache ---
    # Pre-fetch all plays and sync payload-provided plays before ingesting events.
    # Tenant-scoped: every lookup/creation below is filtered by team_id so a
    # payload can never resolve to (hijack) another team's Play. Mirrors the
    # route pattern Play.query.filter_by(id=..., team_id=...).first().
    from core.models import Play
    existing_plays = Play.query.filter_by(team_id=team_id).all()
    play_cache = {_normalize_play_lookup(p.name): p.id for p in existing_plays}
    play_id_cache = {p.id: p.id for p in existing_plays}

    payload_plays = _normalize_payload_plays(data, is_nested_import)
    # Import-local payload-id -> synced-id map. Payload-defined ids (e.g. 101)
    # are external references, not DB ids: mapping them locally preserves
    # valid imports (shot/event play_id 101 -> synced play) without ever
    # aliasing arbitrary ids into the global play_id_cache (which would let
    # a payload claim a cross-team DB id). Team isolation (filter_by team_id)
    # below is untouched.
    payload_id_map: Dict[int, int] = {}
    for payload_play in payload_plays:
        if not isinstance(payload_play, dict):
            continue
        payload_play_id = _safe_int(get_nested_value(payload_play, "id", "play_id", "playId"))
        raw_play_name = get_nested_value(payload_play, "name", "play_name", "playName")
        lookup_name = _normalize_play_lookup(raw_play_name)
        display_name = lookup_name  # collapsed, case-preserved; never ""-created (guarded below)
        payload_play_type = get_nested_value(payload_play, "play_type", "playType", default="Offense") or "Offense"

        existing_by_id = (
            Play.query.filter_by(id=payload_play_id, team_id=team_id).first()
            if payload_play_id
            else None
        )
        existing_by_name = None
        if lookup_name:
            if lookup_name in play_cache:
                cached_id = play_cache[lookup_name]
                existing_by_name = Play.query.filter_by(id=cached_id, team_id=team_id).first()
                if existing_by_name is None:
                    existing_by_name = Play.query.filter_by(team_id=team_id, name=display_name).first()
            else:
                existing_by_name = Play.query.filter_by(team_id=team_id, name=display_name).first()

        if existing_by_id:
            synced_play = existing_by_id
        elif existing_by_name:
            synced_play = existing_by_name
        elif display_name:
            synced_play = _create_scoped_play(team_id, display_name, payload_play_type)
            if synced_play is None:
                continue
        else:
            continue

        play_cache[_normalize_play_lookup(synced_play.name)] = synced_play.id
        play_id_cache[synced_play.id] = synced_play.id
        # Import-local mapping only (not global alias): payload ids defined
        # with a name in this import resolve to the synced play for later
        # shot/event references. Arbitrary/undefined ids are never aliased.
        if payload_play_id is not None and payload_play_id != synced_play.id:
            # Only map ids that were explicitly defined with a name in the
            # payload plays list (or embedded refs with names); bare id-only
            # entries (no name) are skipped above via display_name guard, so
            # they never create a mapping here.
            if lookup_name:
                payload_id_map.setdefault(payload_play_id, synced_play.id)
        # SECURITY: never alias play_id_cache[payload_play_id] = synced_play.id
        # when the requested id differs from the created/found id. That alias
        # would let a payload claim an arbitrary (e.g. cross-team) id and have
        # later events silently resolve to the wrong Play.

    def get_cached_play_id(name):
        # Strip-before-guard: whitespace-only must return None, never create Play(name="").
        lookup = _normalize_play_lookup(name)
        if not lookup:
            return None
        if lookup in play_cache:
            return play_cache[lookup]

        existing = Play.query.filter_by(team_id=team_id, name=lookup).first()
        if existing is not None:
            play_cache[lookup] = existing.id
            play_id_cache[existing.id] = existing.id
            return existing.id

        # Create new if not in cache (IntegrityError-safe with retry-SELECT).
        new_p = _create_scoped_play(team_id, lookup, "Offense")
        if new_p is None:
            return None
        play_cache[lookup] = new_p.id
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
        # Import-local payload mapping (defined ids with names in this
        # payload only): preserves valid shot/event references without
        # polluting the global cache with arbitrary ids.
        if play_id_int in payload_id_map:
            return payload_id_map[play_id_int]

        existing = Play.query.filter_by(id=play_id_int, team_id=team_id).first()
        if existing:
            play_id_cache[play_id_int] = existing.id
            play_cache.setdefault(_normalize_play_lookup(existing.name), existing.id)
            return existing.id
        # Requested id is missing or belongs to another team: fall back to
        # name resolution only, without aliasing the requested id.
        lookup = _normalize_play_lookup(play_name)
        if not lookup:
            return None
        if lookup in play_cache:
            return play_cache[lookup]
        existing_by_name = Play.query.filter_by(team_id=team_id, name=lookup).first()
        if existing_by_name is not None:
            play_cache[lookup] = existing_by_name.id
            return existing_by_name.id
        new_p = _create_scoped_play(team_id, lookup, "Offense")
        if new_p is None:
            return None
        play_id_cache[new_p.id] = new_p.id
        play_cache.setdefault(lookup, new_p.id)
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
            if not p_name:
                continue
            if not isinstance(stats, dict):
                continue
            player_name_clean = p_name.strip() if isinstance(p_name, str) else str(p_name).strip()
            if not player_name_clean:
                continue
            player_name_clean = player_name_clean[:100]

            def _coerce_count(*keys):
                coerced = _safe_int(get_nested_value(stats, *keys, default=0))
                if coerced is None:
                    return 0
                return max(0, coerced)

            fgm = _coerce_count("fgm", "FGM", "fg")
            fga = _coerce_count("fga", "FGA")
            tpm = _coerce_count("tpm", "3PM", "tp", "three_pm")
            tpa = _coerce_count("tpa", "3PA", "three_pa")
            ftm = _coerce_count("ftm", "FTM", "ft")
            fta = _coerce_count("fta", "FTA")
            oreb = _coerce_count("oreb", "OREB", "orb")
            dreb = _coerce_count("dreb", "DREB", "drb")
            ast = _coerce_count("ast", "AST", "assists")
            tov = _coerce_count("tov", "TOV", "turnovers", "to")
            stl = _coerce_count("stl", "STL", "steals")
            blk = _coerce_count("blk", "BLK", "blocks")
            pf = _coerce_count("pf", "PF", "fouls")
            points = _coerce_count("points", "PTS", "pts")
            minutes = _validate_minutes(get_nested_value(stats, "minutes", "MIN", "min", default="00:00"))
            plus_minus_raw = _safe_int(get_nested_value(stats, "plus_minus", "+/-", "pm", "PlusMinus", default=0))
            plus_minus = plus_minus_raw if plus_minus_raw is not None else 0
            reb_conceded = _coerce_count(
                "reb_conceded",
                "REB_CONCEDED",
                "rebConceded",
                "rebounds_conceded",
            )

            fg_pct = (fgm / fga * 100) if fga > 0 else 0.0
            tp_pct = (tpm / tpa * 100) if tpa > 0 else 0.0
            ft_pct = (ftm / fta * 100) if fta > 0 else 0.0

            all_player_stats.append(PlayerStat(
                game_id=game.id, player_name=player_name_clean, minutes=minutes, points=points,
                fgm=fgm, fga=fga, fg_percent=fg_pct, tpm=tpm, tpa=tpa, tp_percent=tp_pct,
                ftm=ftm, fta=fta, ft_percent=ft_pct, oreb=oreb, dreb=dreb, reb=oreb + dreb,
                ast=ast, tov=tov, stl=stl, blk=blk, pf=pf,
                plus_minus=plus_minus,
                reb_conceded=reb_conceded,
            ))
    elif isinstance(player_stats_source, list):
        # EXPORT format: [{"name": "Player Name", ...}]
        _int_stat_keys = {
            "points", "fgm", "fga", "tpm", "tpa", "ftm", "fta",
            "oreb", "dreb", "reb", "ast", "tov", "stl", "blk",
            "pf", "plus_minus", "reb_conceded",
        }
        _float_stat_keys = {"fg_percent", "tp_percent", "ft_percent"}
        for p_data in player_stats_source:
            if not isinstance(p_data, dict):
                continue
            player_name = get_nested_value(p_data, "player_name", "PlayerName", "name", "Name", "player")
            if not player_name:
                continue
            player_name = player_name.strip() if isinstance(player_name, str) else str(player_name).strip()
            if not player_name:
                continue
            player_name = player_name[:100]
            valid_keys = {c.name for c in PlayerStat.__table__.columns if c.name not in ("id", "game_id")}
            stat_kwargs = {k: v for k, v in p_data.items() if k in valid_keys}
            for key in list(stat_kwargs.keys()):
                if key in _int_stat_keys:
                    coerced = _safe_int(stat_kwargs[key])
                    if key == "plus_minus":
                        stat_kwargs[key] = coerced if coerced is not None else 0
                    else:
                        stat_kwargs[key] = max(0, coerced) if coerced is not None else 0
                elif key in _float_stat_keys:
                    coerced_f = _safe_float(stat_kwargs[key])
                    stat_kwargs[key] = coerced_f if coerced_f is not None else 0.0
                elif key == "minutes":
                    stat_kwargs[key] = _validate_minutes(stat_kwargs[key])
            if "player_name" not in stat_kwargs:
                stat_kwargs["player_name"] = player_name
            else:
                raw_name = stat_kwargs["player_name"]
                clean_name = raw_name.strip() if isinstance(raw_name, str) else str(raw_name).strip()
                stat_kwargs["player_name"] = (clean_name[:100] or player_name)
            all_player_stats.append(PlayerStat(game_id=game.id, **stat_kwargs))

    db.session.add_all(all_player_stats)

    # --- Process Shot Events ---
    shot_source_list = shot_events_source if isinstance(shot_events_source, list) else []
    for s_data in shot_source_list:
        if not isinstance(s_data, dict):
            continue
        if is_nested_import:
            # First try mapping exact database keys
            shooter = get_nested_value(s_data, "player_name", "player", "shooter", default="")
            shot_type_raw = get_nested_value(s_data, "shot_type", "type", "ShotType", default="")
            pts_raw = _safe_int(get_nested_value(s_data, "points", "Points", "pts", default=0))
            pts = max(0, pts_raw) if pts_raw is not None else 0
            result = _normalize_shot_result(get_nested_value(s_data, "result", "Result", "made"))
            x = get_nested_value(s_data, "x_loc", "x", "xLoc")
            y = get_nested_value(s_data, "y_loc", "y", "yLoc")
            q = _safe_int(get_nested_value(s_data, "quarter", "q", "period"))
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
                game_id=game.id, player_name=shooter.strip() if isinstance(shooter, str) else "",
                shot_type=_normalize_shot_type(shot_type_raw), result=result, points=pts,
                x_loc=_safe_float(x), y_loc=_safe_float(y),
                quarter=q, play_id=play_id_nested,
            ))
        else:
            shooter = get_nested_value(s_data, "shooter", "player", "player_name", default="")
            shot_type_raw = get_nested_value(s_data, "type", "shot_type", "ShotType", default="")
            pts_raw = _safe_int(get_nested_value(s_data, "points", "Points", "pts", default=0))
            pts = max(0, pts_raw) if pts_raw is not None else 0
            result = _normalize_shot_result(get_nested_value(s_data, "result", "Result", "made"))
            x = get_nested_value(s_data, "x", "x_loc", "xLoc")
            y = get_nested_value(s_data, "y", "y_loc", "yLoc")
            q = _safe_int(get_nested_value(s_data, "quarter", "q", "period"))
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
                game_id=game.id, player_name=shooter.strip() if isinstance(shooter, str) else "",
                shot_type=_normalize_shot_type(shot_type_raw), result=result, points=pts,
                x_loc=_safe_float(x), y_loc=_safe_float(y),
                quarter=q, play_id=v_play_id,
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
    game_source_list = game_events_source if isinstance(game_events_source, list) else []
    for event_index, e_data in enumerate(game_source_list):
        if not isinstance(e_data, dict):
            continue
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
                ftm_raw = detail_parsed.get("ftm", 0)
                ftm_val = _safe_int(ftm_raw)
                ftm_val = ftm_val if ftm_val is not None else 0
                shot_attempt = "made" if ftm_val > 0 else "missed"
            elif shot_attempt is None and event_type in ("SHOT_2PT", "SHOT_3PT") and player_name:
                key = (
                    player_name.strip().lower() if isinstance(player_name, str) else "",
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

            timestamp_val = _safe_int(timestamp)
            timestamp_val = timestamp_val if timestamp_val is not None else 0
            game_event = GameEvent(
                game_id=game.id, event_type=event_type,
                player_name=player_name.strip() if isinstance(player_name, str) else None,
                detail=str(detail) if detail is not None else None,
                timestamp=timestamp_val,
                shot_attempt=shot_attempt, play_id=p_id,
                quarter=quarter,
                time_remaining=time_remaining,
                score_margin=score_margin,
                possession_number=possession_number,
                game_seconds=game_seconds,
                x_loc=_safe_float(x),
                y_loc=_safe_float(y),
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
                ftm_raw = detail_parsed.get("ftm", 0)
                ftm_val = _safe_int(ftm_raw)
                ftm_val = ftm_val if ftm_val is not None else 0
                shot_attempt = "made" if ftm_val > 0 else "missed"
            elif shot_attempt is None and event_type in ("SHOT_2PT", "SHOT_3PT") and player_name:
                key = (
                    player_name.strip().lower() if isinstance(player_name, str) else "",
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

            timestamp_val = _safe_int(timestamp)
            timestamp_val = timestamp_val if timestamp_val is not None else 0
            game_event = GameEvent(
                game_id=game.id, event_type=event_type,
                player_name=player_name.strip() if isinstance(player_name, str) else None,
                detail=str(detail) if detail is not None else None,
                timestamp=timestamp_val,
                shot_attempt=shot_attempt, play_id=v_p_id,
                quarter=quarter,
                time_remaining=time_remaining,
                score_margin=score_margin,
                possession_number=possession_number,
                game_seconds=game_seconds,
                x_loc=_safe_float(x),
                y_loc=_safe_float(y),
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
            process_game_lineups(game.id, saved_events, starting_lineup, team_id)
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
