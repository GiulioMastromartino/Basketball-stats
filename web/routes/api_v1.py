"""
Merged API v1 routes.
Combines routes from legacy api.py and play_builder_api.py under a single blueprint.
"""

import json
import re
from datetime import datetime

from flask import Blueprint, jsonify, request, session, abort, current_app
from flask_login import login_required
from core.models import (
    Play,
    PlaySequence,
    PlayType,
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    LineupSegment,
    db,
)
from core.csv_processor import CSVProcessor
from core.parser import parse_game_pdf
from core.services import create_game_from_live_data
from web.decorators import team_access_required

api_v1_bp = Blueprint("api_v1", __name__)


def _coerce_json_game_dates(game_data: dict) -> tuple[str, str]:
    raw_sort = (game_data.get("sort_date") or game_data.get("sortdate") or "").strip()
    raw_date = (game_data.get("date") or "").strip()
    sort_date = raw_sort
    if not sort_date and raw_date:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            sort_date = raw_date
        else:
            parts = re.split(r"[-/]", raw_date)
            if len(parts) == 3:
                sort_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
    return (raw_date, sort_date)


@api_v1_bp.route("/games", methods=["GET"])
@login_required
@team_access_required
def get_games():
    """Get all games with their database IDs, for cross-referencing native data."""
    team_id = session.get('current_team_id')
    games = (
        Game.query.filter_by(team_id=team_id)
        .order_by(Game.sort_date.asc())
        .all()
    )
    return jsonify(
        [
            {
                "id": g.id,
                "date": g.date,
                "sort_date": g.sort_date,
                "opponent": g.opponent,
                "team_score": g.team_score,
                "opponent_score": g.opponent_score,
                "result": g.result,
                "game_type": g.game_type,
            }
            for g in games
        ]
    )


def _column_dict(instance):
    """Serialize a SQLAlchemy model instance to a dict of column values."""
    if not instance:
        return None
    return {c.name: getattr(instance, c.name) for c in instance.__table__.columns}


@api_v1_bp.route("/sync", methods=["GET"])
@login_required
@team_access_required
def sync_all():
    """Full team snapshot for native-app sync: games (with stats, shots,
    events, lineup segments) plus the playbook. The server is the source of
    truth; the native app replaces its server-present data with this payload."""
    team_id = session.get("current_team_id")

    games = (
        Game.query.filter_by(team_id=team_id).order_by(Game.sort_date.asc()).all()
    )
    games_payload = []
    for game in games:
        player_stats = (
            PlayerStat.query.filter_by(game_id=game.id).order_by(PlayerStat.id).all()
        )
        shot_events = (
            ShotEvent.query.filter_by(game_id=game.id).order_by(ShotEvent.id).all()
        )
        try:
            game_events = (
                GameEvent.query.filter_by(game_id=game.id)
                .order_by(GameEvent.timestamp)
                .all()
            )
        except Exception:
            game_events = []
        segments = (
            LineupSegment.query.filter_by(game_id=game.id)
            .order_by(LineupSegment.start_timestamp)
            .all()
        )
        starting_lineup = None
        for seg in segments:
            players = seg.players or []
            if len(players) == 5:
                starting_lineup = players
                break
        if starting_lineup is None and segments:
            starting_lineup = segments[0].players or None

        games_payload.append(
            {
                "game": _column_dict(game),
                "player_stats": [_column_dict(ps) for ps in player_stats],
                "shot_events": [_column_dict(se) for se in shot_events],
                "game_events": [_column_dict(ge) for ge in game_events],
                "starting_lineup": starting_lineup,
                "lineup_segments": [
                    _column_dict(seg) for seg in segments
                ],
            }
        )

    plays = Play.query.filter_by(team_id=team_id).order_by(Play.play_type, Play.name).all()
    plays_payload = []
    for play in plays:
        payload = _column_dict(play)
        sequences = (
            PlaySequence.query.filter_by(play_id=play.id)
            .order_by(PlaySequence.sequence_number)
            .all()
        )
        payload["frames"] = [_column_dict(seq) for seq in sequences]
        plays_payload.append(payload)

    play_types = PlayType.query.filter_by(team_id=team_id).order_by(PlayType.name).all()

    return jsonify(
        {
            "exported_at": datetime.utcnow().isoformat(),
            "games": games_payload,
            "plays": plays_payload,
            "play_types": [_column_dict(pt) for pt in play_types],
        }
    )


def _save_game_from_data(game_data):
    team_id = session.get("current_team_id")
    game = Game(
        date=game_data["date"],
        opponent=game_data["opponent"],
        team_score=game_data["team_score"],
        opponent_score=game_data["opponent_score"],
        result=game_data["result"],
        game_type=game_data["game_type"],
        sort_date=game_data["sort_date"],
        team_id=team_id,
        source="IMPORT",
    )
    db.session.add(game)
    db.session.flush()
    for player in game_data["players"]:
        if not player.get("name"):
            continue
        db.session.add(
            PlayerStat(
                game_id=game.id,
                player_name=player["name"].strip(),
                minutes=player.get("minutes", "0"),
                points=int(player.get("points", 0) or 0),
                fgm=int(player.get("fgm", 0) or 0),
                fga=int(player.get("fga", 0) or 0),
                fg_percent=float(player.get("fg_percent", 0) or 0),
                tpm=int(player.get("tpm", 0) or 0),
                tpa=int(player.get("tpa", 0) or 0),
                tp_percent=float(player.get("tp_percent", 0) or 0),
                ftm=int(player.get("ftm", 0) or 0),
                fta=int(player.get("fta", 0) or 0),
                ft_percent=float(player.get("ft_percent", 0) or 0),
                oreb=int(player.get("oreb", 0) or 0),
                dreb=int(player.get("dreb", 0) or 0),
                reb=int(player.get("reb", 0) or 0),
                ast=int(player.get("ast", 0) or 0),
                tov=int(player.get("tov", 0) or 0),
                stl=int(player.get("stl", 0) or 0),
                blk=int(player.get("blk", 0) or 0),
                pf=int(player.get("pf", 0) or 0),
                plus_minus=int(player.get("plus_minus", 0) or 0),
                reb_conceded=int(player.get("reb_conceded", 0) or 0),
            )
        )
    db.session.commit()
    return game


@api_v1_bp.route("/import", methods=["POST"])
@login_required
@team_access_required
def import_games():
    """JSON API mirror of the web upload flow: batch CSV, single PDF, batch JSON."""
    import_type = (request.form.get("import_type") or "csv").lower().strip()
    if import_type not in {"csv", "pdf", "json"}:
        return jsonify({"success_count": 0, "errors": ["Invalid import type"]}), 400

    team_id = session.get("current_team_id")
    errors = []
    success_count = 0

    try:
        if import_type in {"csv", "json"}:
            files = request.files.getlist("file")
            if not files or files[0].filename == "":
                return jsonify({"success_count": 0, "errors": ["No file uploaded"]}), 400

            for file in files:
                try:
                    if not file.filename.lower().endswith(f".{import_type}"):
                        errors.append(f"{file.filename}: invalid file type")
                        continue

                    if import_type == "csv":
                        info = CSVProcessor.parse_filename(file.filename)
                        if not info:
                            errors.append(f"{file.filename}: invalid filename format")
                            continue
                        if Game.query.filter_by(
                            sort_date=info["sort_date"], opponent=info["opponent"], team_id=team_id
                        ).first():
                            errors.append(f"{file.filename}: game already exists")
                            continue
                        game_data = CSVProcessor.process_game(file.stream, info)
                        if not game_data:
                            errors.append(f"{file.filename}: failed to process")
                            continue
                    else:
                        try:
                            payload = json.loads(file.read())
                        except json.JSONDecodeError:
                            errors.append(f"{file.filename}: invalid JSON format")
                            continue
                        game_data = payload.get("game") or payload
                        if not isinstance(game_data, dict) or not (payload.get("player_stats") or game_data.get("players")):
                            errors.append(f"{file.filename}: no player rows in payload")
                            continue
                        date_display, sort_date = _coerce_json_game_dates(game_data)
                        opponent = (game_data.get("opponent") or game_data.get("Opponent") or game_data.get("vs") or "").strip()
                        if not sort_date or not opponent:
                            errors.append(f"{file.filename}: missing date or opponent")
                            continue
                        if Game.query.filter_by(
                            sort_date=sort_date, opponent=opponent, team_id=team_id
                        ).first():
                            errors.append(f"{file.filename}: game already exists")
                            continue
                        create_game_from_live_data(payload, team_id=team_id)
                        success_count += 1
                        continue

                    _save_game_from_data(game_data)
                    success_count += 1
                except Exception as exc:
                    db.session.rollback()
                    errors.append(f"{file.filename}: {exc}")

        elif import_type == "pdf":
            file = request.files.get("file")
            if not file or file.filename == "":
                return jsonify({"success_count": 0, "errors": ["No PDF file uploaded"]}), 400
            try:
                parsed = parse_game_pdf(file.stream)
                players = parsed.get("players") or []
                if not players:
                    return jsonify({"success_count": 0, "errors": ["No player rows detected in PDF"]}), 400

                opponent = (request.form.get("opponent") or parsed.get("opponent") or "Unknown").strip()
                date_display = request.form.get("date") or parsed.get("date") or ""
                team_score = int(request.form.get("team_score") or parsed.get("team_score") or 0)
                opp_score = int(request.form.get("opponent_score") or parsed.get("opponent_score") or 0)
                result = "W" if team_score > opp_score else ("L" if team_score < opp_score else "D")
                game_type = request.form.get("game_type") or parsed.get("game_type") or "Season"
                try:
                    sort_date = datetime.strptime(date_display, "%d/%m/%Y").date().isoformat()
                except ValueError:
                    try:
                        sort_date = datetime.strptime(date_display, "%Y-%m-%d").date().isoformat()
                    except ValueError:
                        sort_date = ""
                _save_game_from_data(
                    {
                        "date": date_display,
                        "opponent": opponent,
                        "team_score": team_score,
                        "opponent_score": opp_score,
                        "result": result,
                        "game_type": game_type,
                        "sort_date": sort_date,
                        "players": players,
                    }
                )
                success_count += 1
            except Exception as exc:
                db.session.rollback()
                errors.append(f"PDF import failed: {exc}")
    except Exception as exc:
        db.session.rollback()
        errors.append(str(exc))

    return jsonify({"success_count": success_count, "errors": errors})


@api_v1_bp.route("/plays", methods=["GET"])
@login_required
@team_access_required
def get_plays():
    """Get all plays, optionally filtered by type"""
    play_type = request.args.get("type", "All")

    team_id = session.get('current_team_id')
    if play_type == "All":
        plays = Play.query.filter_by(team_id=team_id).order_by(Play.play_type, Play.name).all()
    else:
        plays = Play.query.filter_by(play_type=play_type, team_id=team_id).order_by(Play.name).all()

    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "type": p.play_type,
                "description": p.description,
            }
            for p in plays
        ]
    )


@api_v1_bp.route("/plays/types", methods=["GET"])
@login_required
@team_access_required
def get_play_types():
    """Get unique play types"""
    play_types = (
        db.session.query(Play.play_type)
        .filter(Play.team_id == session.get('current_team_id'))
        .distinct().order_by(Play.play_type).all()
    )
    return jsonify([pt[0] for pt in play_types])


@api_v1_bp.route("/plays/api/save-canvas", methods=["POST"])
@login_required
@team_access_required
def save_canvas():
    """
    Save the play metadata, canvas JSON, SVG preview, and animation frames.
    Expected JSON payload:
    {
        "play_id": <int> (optional, if update),
        "metadata": { ... },
        "canvas_json": <dict>,
        "diagram_svg": <str>,
        "frames": [ ... ]
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"success": False, "error": "No data provided"}), 400

    metadata = payload.get("metadata", {})
    name = metadata.get("name")

    if not name:
        return jsonify({"success": False, "error": "Play name is required"}), 400

    play_id = payload.get("play_id")

    team_id = session.get('current_team_id')
    if play_id:
        # Update existing play
        play = Play.query.filter_by(id=play_id, team_id=team_id).first()
        if not play:
            return jsonify({"success": False, "error": "Play not found"}), 404

        # Check unique name (exclude self)
        existing = Play.query.filter_by(name=name, team_id=team_id).first()
        if existing and existing.id != play.id:
            return jsonify({"success": False, "error": "Name already exists"}), 400
    else:
        # Create new play
        if Play.query.filter_by(name=name, team_id=team_id).first():
            return jsonify({"success": False, "error": "Name already exists"}), 400

        play = Play(team_id=team_id)
        db.session.add(play)

    # Update fields
    play.name = name
    play.description = metadata.get("description")
    play.play_type = metadata.get("play_type", "Offense")
    play.difficulty = metadata.get("difficulty", "Medium")
    play.personnel_required = metadata.get("personnel")
    play.tags = metadata.get("tags")
    play.canvas_data = payload.get("canvas_json")

    # Save SVG preview if provided
    if "diagram_svg" in payload:
        play.diagram_svg = payload["diagram_svg"]

    # Commit play first to get ID for sequences
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

    # Handle animation frames (sequences)
    frames = payload.get("frames", [])

    if frames:
        try:
            # Delete existing sequences
            from core.models import PlaySequence

            PlaySequence.query.filter_by(play_id=play.id).delete()

            # Create new sequences
            for idx, frame in enumerate(frames):
                sequence = PlaySequence(
                    play_id=play.id,
                    sequence_number=idx + 1,
                    element_data=frame.get("data"),
                    caption=frame.get("caption", f"Frame {idx + 1}"),
                )
                db.session.add(sequence)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Sequence save failed: {str(e)}"}
            ), 500

    return jsonify(
        {"success": True, "play_id": play.id, "message": "Play saved successfully"}
    )


@api_v1_bp.route("/plays/api/load-canvas/<int:play_id>", methods=["GET"])
@login_required
@team_access_required
def load_canvas(play_id):
    """
    Return the canvas JSON, metadata, and animation frames for a given play.
    """
    play = Play.query.filter_by(id=play_id, team_id=session.get('current_team_id')).first()
    if not play:
        abort(404)

    # Load sequences
    from core.models import PlaySequence

    sequences = (
        PlaySequence.query.filter_by(play_id=play.id)
        .order_by(PlaySequence.sequence_number)
        .all()
    )

    frames = []
    for seq in sequences:
        frames.append({"id": seq.id, "data": seq.element_data, "caption": seq.caption})

    response = {
        "success": True,
        "play_id": play.id,
        "metadata": {
            "name": play.name,
            "description": play.description,
            "play_type": play.play_type,
            "difficulty": play.difficulty,
            "personnel": play.personnel_required,
            "tags": play.tags,
            "created_at": play.created_at.isoformat(),
            "updated_at": play.updated_at.isoformat(),
        },
        "canvas_json": play.canvas_data,
        "frames": frames,
    }

    return jsonify(response)
