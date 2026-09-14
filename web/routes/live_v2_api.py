"""Live Game v2 per-event API.

Slice: backend for the v2 console pending queue
(``web/static/js/live_game_v2.js``). Unlike the legacy bulk
``POST /live-game/save`` (full game JSON persisted via
``create_game_from_live_data``), these endpoints persist a single
``GameEvent`` row per action — plus a ``ShotEvent`` row for shots —
so the console can sync each queued event individually.
"""

import json
import time

from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required

from core.models import Game, GameEvent, ShotEvent, db
from web.decorators import team_access_required

live_v2_bp = Blueprint("live_v2", __name__, url_prefix="/api/live-v2")

# Console display labels -> canonical GameEvent.event_type values.
_ACTION_ALIASES = {
    "2PT MADE": ("SHOT_2PT", "made"),
    "3PT MADE": ("SHOT_3PT", "made"),
    "2PT MISS": ("SHOT_2PT", "missed"),
    "3PT MISS": ("SHOT_3PT", "missed"),
    "SHOT_2PT": ("SHOT_2PT", None),
    "SHOT_3PT": ("SHOT_3PT", None),
    "FT MADE": ("FT_MADE", "made"),
    "FT_MADE": ("FT_MADE", "made"),
    "FT MISS": ("FT_MISS", "missed"),
    "FT_MISS": ("FT_MISS", "missed"),
    "FT": ("FT_MISS", "missed"),
    "ASSIST": ("ASSIST", None),
    "REBOUND": ("REBOUND", None),
    "BLOCK": ("BLOCK", None),
    "STEAL": ("STEAL", None),
    "FOUL": ("FOUL", None),
    "TECH FOUL": ("TECH_FOUL", None),
    "TECH_FOUL": ("TECH_FOUL", None),
    "TECHNICAL FOUL": ("TECH_FOUL", None),
    "TOV": ("TURNOVER", None),
    "TURNOVER": ("TURNOVER", None),
    "TIME OUT": ("TIMEOUT", None),
    "TIMEOUT": ("TIMEOUT", None),
    "TIME_OUT": ("TIMEOUT", None),
    "SUB": ("SUB", None),
    "SUBSTITUTION": ("SUB", None),
}

# Canonical types that require a player reference.
_PLAYER_REQUIRED = {
    "SHOT_2PT",
    "SHOT_3PT",
    "FT_MADE",
    "FT_MISS",
    "ASSIST",
    "REBOUND",
    "BLOCK",
    "STEAL",
    "FOUL",
    "TECH_FOUL",
    "TURNOVER",
}

_SHOT_TYPES = {"SHOT_2PT", "SHOT_3PT", "FT_MADE", "FT_MISS"}
_SHOT_TYPE_MAP = {
    "SHOT_2PT": "2pt",
    "SHOT_3PT": "3pt",
    "FT_MADE": "ft",
    "FT_MISS": "ft",
}
_POINTS_MAP = {"SHOT_2PT": 2, "SHOT_3PT": 3, "FT_MADE": 1, "FT_MISS": 1}

_ALLOWED_ZONES = {"PAINT", "MIDRANGE", "3PT"}


def _error(message, status):
    return jsonify({"error": message}), status


def _scoped_game(game_id):
    """Return (game, None) when the id exists and is in team scope.

    Otherwise (None, (response, status)) with 404 for unknown games and
    403 for games belonging to another team.
    """
    game = Game.query.get(game_id)
    if game is None:
        return None, _error("Game not found", 404)
    team_id = session.get("current_team_id")
    if game.team_id != team_id:
        return None, _error("Game belongs to another team", 403)
    if current_app.config.get("LOGIN_DISABLED", False):
        return game, None
    try:
        allowed = {t.id for t in current_user.assigned_teams}
    except Exception:
        allowed = set()
    # No empty-set bypass: a user with no team assignments may not act on
    # any game, even when the session still carries a stale team id.
    if game.team_id not in allowed:
        return None, _error("Game belongs to another team", 403)
    return game, None


def _normalize_action(raw):
    if raw is None:
        return None, None
    key = str(raw).strip().upper()
    if key in _ACTION_ALIASES:
        return _ACTION_ALIASES[key]
    collapsed = "_".join(key.split())
    if collapsed in _ACTION_ALIASES:
        return _ACTION_ALIASES[collapsed]
    return None, None


def _parse_period(value):
    if value is None or value == "":
        return None
    try:
        period = int(value)
    except (TypeError, ValueError):
        return "invalid"
    if period < 1 or period > 10:
        return "invalid"
    return period


def _parse_clock(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return "invalid"
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except (TypeError, ValueError):
        return "invalid"
    if minutes < 0 or minutes > 99 or seconds < 0 or seconds > 59:
        return "invalid"
    return f"{minutes}:{seconds:02d}"


def _parse_coord(value, name, errors):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{name} must be numeric")
        return None


def _parse_points(value, errors):
    if value is None or value == "":
        return None
    try:
        points = int(value)
    except (TypeError, ValueError):
        errors.append("points must be an integer")
        return None
    if points < 0 or points > 4:
        errors.append("points must be between 0 and 4")
        return None
    return points


def _detail_payload(client_event_id, team, number, action):
    # GameEvent.detail is String(255): cap each field so the JSON envelope
    # always fits, keeping it parseable for idempotency lookups.
    return json.dumps(
        {
            "client_event_id": (client_event_id or "")[:64] or None,
            "team": (str(team)[:16] if team is not None else None),
            "number": (str(number)[:16] if number is not None else None),
            "action": (str(action)[:64] if action is not None else None),
        }
    )


def _find_duplicate(game_id, client_event_id):
    """Return an existing event with this client_event_id, if any.

    Scans only the most recent rows: duplicates arrive as immediate retries
    of a just-sent event, so materializing the whole game log per request is
    wasteful. Deliberately backend-agnostic — detail is a plain String
    holding JSON, with no portable JSON operator across SQLite/Postgres.
    """
    if not client_event_id:
        return None
    recent = (
        GameEvent.query.filter_by(game_id=game_id)
        .order_by(GameEvent.id.desc())
        .limit(50)
        .all()
    )
    for event in recent:
        try:
            detail = json.loads(event.detail) if event.detail else {}
        except (TypeError, ValueError):
            continue
        if isinstance(detail, dict) and detail.get("client_event_id") == client_event_id:
            return event
    return None


def _event_to_dict(event):
    return {
        "id": event.id,
        "event_type": event.event_type,
        "player_name": event.player_name,
        "detail": event.detail,
        "quarter": event.quarter,
        "time_remaining": event.time_remaining,
        "x_loc": event.x_loc,
        "y_loc": event.y_loc,
        "zone": event.zone,
        "shot_attempt": event.shot_attempt,
        "server_timestamp": event.timestamp,
    }


@live_v2_bp.route("/events", methods=["POST"])
@login_required
@team_access_required
def post_event():
    """Persist a single console action as GameEvent (+ShotEvent for shots)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    game_id = data.get("game_id", data.get("gameId"))
    if game_id is None or game_id == "":
        return _error("game_id is required", 400)
    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        return _error("game_id must be an integer", 400)

    game, denied = _scoped_game(game_id)
    if denied is not None:
        return denied

    raw_action = data.get("event_type", data.get("action", data.get("type")))
    event_type, shot_attempt = _normalize_action(raw_action)
    if event_type is None:
        return _error("Unknown event type", 400)

    player_name = data.get("player_name", data.get("player", data.get("name")))
    if isinstance(player_name, str):
        player_name = player_name.strip() or None
    elif player_name is not None:
        player_name = str(player_name)
    if event_type in _PLAYER_REQUIRED and not player_name:
        return _error("player_name is required for this event type", 400)

    period = _parse_period(data.get("period", data.get("quarter", data.get("q"))))
    if period == "invalid":
        return _error("period must be an integer between 1 and 10", 400)

    clock = _parse_clock(
        data.get("clock", data.get("time_remaining", data.get("timeRemaining")))
    )
    if clock == "invalid":
        return _error("clock must use MM:SS format", 400)

    errors = []
    x_loc = _parse_coord(data.get("x", data.get("x_loc", data.get("xLoc"))), "x", errors)
    y_loc = _parse_coord(data.get("y", data.get("y_loc", data.get("yLoc"))), "y", errors)
    points = _parse_points(data.get("points", data.get("pts")), errors)
    if errors:
        return _error("; ".join(errors), 400)

    zone = data.get("zone")
    if zone is not None and zone != "":
        zone = str(zone).strip().upper()
        if zone not in _ALLOWED_ZONES:
            return _error("zone must be one of PAINT, MIDRANGE, 3PT", 400)
    else:
        zone = None

    client_event_id = data.get("client_event_id", data.get("clientEventId"))
    if client_event_id is not None:
        client_event_id = str(client_event_id).strip()[:64] or None

    duplicate = _find_duplicate(game_id, client_event_id)
    if duplicate is not None:
        return (
            jsonify(
                {
                    "id": duplicate.id,
                    "server_timestamp": duplicate.timestamp,
                    "duplicate": True,
                }
            ),
            200,
        )

    team = data.get("team")
    number = data.get("number", data.get("jersey_number", data.get("jerseyNumber")))
    now_ms = int(time.time() * 1000)
    event = GameEvent(
        game_id=game.id,
        event_type=event_type,
        player_name=player_name,
        detail=_detail_payload(client_event_id, team, number, raw_action),
        timestamp=now_ms,
        shot_attempt=shot_attempt,
        quarter=period,
        time_remaining=clock,
        x_loc=x_loc,
        y_loc=y_loc,
        zone=zone,
    )
    try:
        db.session.add(event)
        db.session.flush()
        if event_type in _SHOT_TYPES:
            made = (shot_attempt == "made") or (
                shot_attempt is None and event_type == "FT_MADE"
            )
            resolved_points = (
                points if points is not None else _POINTS_MAP[event_type]
            )
            shot = ShotEvent(
                game_id=game.id,
                player_name=player_name,
                shot_type=_SHOT_TYPE_MAP[event_type],
                result="made" if made else "missed",
                points=resolved_points if made else 0,
                x_loc=x_loc,
                y_loc=y_loc,
                zone=zone,
                quarter=period,
            )
            db.session.add(shot)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error("Failed to persist event", 500)

    return (
        jsonify(
            {"id": event.id, "server_timestamp": event.timestamp, "duplicate": False}
        ),
        201,
    )


@live_v2_bp.route("/events", methods=["GET"])
@login_required
@team_access_required
def list_events():
    """Return the persisted game log so the console can resync."""
    game_id = request.args.get("game_id", request.args.get("gameId"))
    if game_id is None or game_id == "":
        return _error("game_id is required", 400)
    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        return _error("game_id must be an integer", 400)

    game, denied = _scoped_game(game_id)
    if denied is not None:
        return denied

    events = (
        GameEvent.query.filter_by(game_id=game.id).order_by(GameEvent.id.asc()).all()
    )
    return jsonify({"game_id": game.id, "events": [_event_to_dict(e) for e in events]})


@live_v2_bp.route("/undo", methods=["POST"])
@login_required
@team_access_required
def undo_event():
    """Delete the most recent event for the game (console undo)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    game_id = data.get("game_id", data.get("gameId"))
    if game_id is None or game_id == "":
        return _error("game_id is required", 400)
    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        return _error("game_id must be an integer", 400)

    game, denied = _scoped_game(game_id)
    if denied is not None:
        return denied

    event = (
        GameEvent.query.filter_by(game_id=game.id)
        .order_by(GameEvent.id.desc())
        .first()
    )
    if event is None:
        return _error("No events to undo", 404)

    undone_id = event.id
    try:
        if event.event_type in _SHOT_TYPES:
            # ShotEvent rows carry no event FK: remove the most recent shot
            # matching this event's type AND result — one quarter can hold a
            # 2PT made and a 3PT missed by the same player.
            shot_query = ShotEvent.query.filter_by(
                game_id=game.id,
                player_name=event.player_name,
                quarter=event.quarter,
                shot_type=_SHOT_TYPE_MAP[event.event_type],
            )
            if event.shot_attempt in ("made", "missed"):
                shot_query = shot_query.filter_by(result=event.shot_attempt)
            shot = shot_query.order_by(ShotEvent.id.desc()).first()
            if shot is not None:
                db.session.delete(shot)
        db.session.delete(event)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return _error("Failed to undo event", 500)

    return jsonify({"undone_id": undone_id})
