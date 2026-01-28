import os
import json
import statistics
import re
from datetime import datetime
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, make_response
from flask_login import login_required
from sqlalchemy import case, func

from core.models import Game, PlayerStat, ShotEvent, GameEvent, db, Play
from core.csv_processor import CSVProcessor
from core.parser import parse_game_pdf
from core.services import create_game_from_live_data  # This now imports from core/services/__init__.py
from core.play_analytics import (
    get_play_stats,
    get_play_player_stats,
    get_player_play_stats,
    get_untracked_percentages,
)
from core.utils import (
    FT_ATTEMPT_WEIGHT,
    THREE_POINT_WEIGHT,
    calculate_efficiency,
    calculate_efg_percent,
    calculate_game_score,
    calculate_ortg,
    calculate_per_100_minutes,
    calculate_possessions,
    calculate_ppp,
    calculate_ts_percent,
    calculate_two_point_stats,
    parse_minutes,
    safe_percentage,
    normalize_date_to_display,
)

main_bp = Blueprint("main", __name__)

VALID_GAME_TYPES = {"ALL", "Season", "Friendly", "Playoff"}
ALLOWED_EXTENSIONS = {"csv", "pdf", "json"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_date_to_sort(date_str: str) -> str:
    """Return YYYY-MM-DD."""
    display = normalize_date_to_display(date_str)
    if not display:
        return ""
    day, month, year = display.split("/")
    return f"{year}-{month}-{day}"


def coerce_json_game_dates(game_data: dict) -> tuple[str, str]:
    """Return (date_display, sort_date) for JSON import.

    Prefers sort_date (YYYY-MM-DD) if present; derives date display as DD/MM/YYYY.
    """
    raw_sort = (game_data.get("sort_date") or "").strip()
    raw_date = (game_data.get("date") or "").strip()

    sort_date = raw_sort
    if not sort_date and raw_date:
        # Try to derive sort_date from raw_date (DD/MM/YYYY or DD-MM-YYYY)
        sort_date = normalize_date_to_sort(raw_date)

    date_display = ""
    if sort_date and re.match(r"^\d{4}-\d{2}-\d{2}$", sort_date):
        # Canonical: derive display date from sort_date
        date_display = datetime.strptime(sort_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    else:
        # Fallback: use raw_date normalization if possible
        date_display = normalize_date_to_display(raw_date) or raw_date

    return date_display, sort_date


@main_bp.route("/")
@login_required
def index():
    """Dashboard home page"""
    games = Game.query.order_by(Game.sort_date.desc()).all()
    total_games = len(games)
    total_players = db.session.query(PlayerStat.player_name).distinct().count()
    wins = sum(1 for g in games if g.result == "W")
    losses = sum(1 for g in games if g.result == "L")

    return render_template(
        "index.html",
        games=games,
        stats={
            "games": total_games,
            "players": total_players,
            "wins": wins,
            "losses": losses,
        },
    )


@main_bp.route("/glossary")
@login_required
def glossary():
    """Stats glossary page"""
    return render_template("glossary.html")


@main_bp.route("/live-game")
@login_required
def live_game():
    """Interface for live game stat tracking"""
    # Fetch existing player names for easy selection
    existing_players = [r[0] for r in db.session.query(PlayerStat.player_name).distinct().order_by(PlayerStat.player_name).all()]

    # Fetch available plays for selection (also injected, but JS fetches from API)
    # Convert SQLAlchemy objects to dicts for JSON serialization in template
    plays_query = Play.query.order_by(Play.play_type, Play.name).all()
    plays_list = [
        {
            "id": p.id,
            "name": p.name,
            "type": p.play_type,
            "description": p.description,
        }
        for p in plays_query
    ]

    from datetime import datetime
    now_date = datetime.now().strftime("%Y-%m-%d")
    return render_template("live_game.html", existing_players=existing_players, now_date=now_date, plays=plays_list)


@main_bp.route("/api/plays")
@login_required
def api_plays():
    """API endpoint to get list of plays for live game selector"""
    plays = Play.query.order_by(Play.play_type, Play.name).all()
    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "type": p.play_type,
            "description": p.description,
        }
        for p in plays
    ])


@main_bp.route("/live-game/save", methods=["POST"])
@login_required
def save_live_game():
    """Receive JSON data from live tracker and save to DB

    Returns JSON response:
    - Success: {"success": true, "game_id": <id>}
    - Error: {"error": "error message", "details": "optional details"}
    """
    data = request.get_json()

    if not data:
        return jsonify({
            "error": "No data received",
            "details": "Request body is empty or not valid JSON"
        }), 400

    try:
        game = create_game_from_live_data(data)
        current_app.logger.info(f"Live game saved successfully: Game ID {game.id}")
        return jsonify({
            "success": True,
            "game_id": game.id,
            "message": f"Game saved: {game.opponent} ({game.result})"
        }), 201

    except ValueError as e:
        # Validation errors (invalid play IDs, missing required fields, etc.)
        db.session.rollback()
        error_msg = str(e)
        current_app.logger.warning(f"Live game validation error: {error_msg}")
        return jsonify({
            "error": "Validation Error",
            "details": error_msg
        }), 400

    except Exception as e:
        # Unexpected errors (database errors, FK violations, etc.)
        db.session.rollback()
        error_msg = str(e)
        current_app.logger.error(f"Live game save error: {error_msg}", exc_info=True)

        # Provide user-friendly error message
        user_msg = "An unexpected error occurred while saving the game."
        if "foreign key" in error_msg.lower():
            user_msg = "Database integrity error: Invalid reference to play or other data."
        elif "constraint" in error_msg.lower():
            user_msg = "Data constraint violation: Check that all required fields are valid."

        return jsonify({
            "error": user_msg,
            "details": error_msg if current_app.debug else None
        }), 500


@main_bp.route("/upload-game", methods=["GET", "POST"])
@login_required
def upload_game():
    """Upload a CSV, PDF, or JSON file to add a game"""
    if request.method == "POST":
        import_type = request.form.get("import_type", "csv").lower().strip()
        if import_type not in {"csv", "pdf", "json"}:
            import_type = "csv"

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        filepath = None

        try:
            # --- CSV Import ---
            if import_type == "csv":
                if "csv_file" not in request.files:
                    flash("No CSV file uploaded", "danger")
                    return redirect(request.url)

                file = request.files["csv_file"]
                if file.filename == "":
                    flash("No file selected", "danger")
                    return redirect(request.url)

                if not allowed_file(file.filename) or not file.filename.lower().endswith(".csv"):
                    flash("Only CSV files are allowed for CSV import", "danger")
                    return redirect(request.url)

                filename = secure_filename(file.filename)
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)

                info = CSVProcessor.parse_filename(filename)
                if not info:
                    flash(
                        "Invalid filename format. Expected: Opponent_TeamScore-OppScore_DD-MM-YYYY_[F/S/P].csv",
                        "danger",
                    )
                    return redirect(request.url)

                existing = Game.query.filter_by(sort_date=info["sort_date"], opponent=info["opponent"]).first()
                if existing:
                    flash(f"Game already exists: {existing.opponent} on {existing.date}", "warning")
                    return redirect(url_for("main.index"))

                game_data = CSVProcessor.process_game(filepath, info)
                if not game_data:
                    flash("Failed to process CSV content. Check file format.", "danger")
                    return redirect(request.url)

                game = Game(
                    date=game_data["date"],
                    opponent=game_data["opponent"],
                    team_score=game_data["team_score"],
                    opponent_score=game_data["opponent_score"],
                    result=game_data["result"],
                    game_type=game_data["game_type"],
                    sort_date=game_data["sort_date"],
                    source="IMPORT",
                )
                db.session.add(game)
                db.session.flush()

                for player in game_data["players"]:
                    if not player.get("name"):
                        continue

                    stat = PlayerStat(
                        game_id=game.id,
                        player_name=player["name"],
                        minutes=player["minutes"],
                        points=player["points"],
                        fgm=player["fgm"],
                        fga=player["fga"],
                        fg_percent=player["fg_percent"],
                        tpm=player["tpm"],
                        tpa=player["tpa"],
                        tp_percent=player["tp_percent"],
                        ftm=player["ftm"],
                        fta=player["fta"],
                        ft_percent=player["ft_percent"],
                        oreb=player["oreb"],
                        dreb=player["dreb"],
                        reb=player["reb"],
                        ast=player["ast"],
                        tov=player["tov"],
                        stl=player["stl"],
                        blk=player["blk"],
                        pf=player["pf"],
                        plus_minus=int(player.get("plus_minus", 0) or 0),
                    )
                    db.session.add(stat)

                db.session.commit()
                flash(f"Successfully imported game (CSV): {game.opponent} ({game.result})", "success")
                return redirect(url_for("main.game_detail", game_id=game.id))

            # --- PDF import ---
            elif import_type == "pdf":
                if "pdf_file" not in request.files:
                    flash("No PDF file uploaded", "danger")
                    return redirect(request.url)

                file = request.files["pdf_file"]
                if file.filename == "":
                    flash("No file selected", "danger")
                    return redirect(request.url)

                if not allowed_file(file.filename) or not file.filename.lower().endswith(".pdf"):
                    flash("Only PDF files are allowed for PDF import", "danger")
                    return redirect(request.url)

                filename = secure_filename(file.filename)
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)

                parsed = parse_game_pdf(filepath)

                # Overrides (optional)
                override_opponent = (request.form.get("pdf_opponent") or "").strip()
                override_date = (request.form.get("pdf_date") or "").strip()
                override_team_score = (request.form.get("pdf_team_score") or "").strip()
                override_opponent_score = (request.form.get("pdf_opponent_score") or "").strip()
                override_game_type = (request.form.get("pdf_game_type") or "").strip()

                opponent = override_opponent or parsed.get("opponent") or "Unknown"

                date_display = normalize_date_to_display(override_date) if override_date else (parsed.get("date") or "")
                if override_date and not date_display:
                    flash("Invalid date format. Use DD-MM-YYYY or DD/MM/YYYY.", "danger")
                    return redirect(request.url)

                sort_date = normalize_date_to_sort(override_date) if override_date else (parsed.get("sort_date") or "")

                # Scores
                team_score = parsed.get("team_score") or 0
                opp_score = parsed.get("opponent_score") or 0
                if override_team_score:
                    team_score = int(override_team_score)
                if override_opponent_score:
                    opp_score = int(override_opponent_score)

                if not date_display or not sort_date:
                    flash("Could not determine game date from PDF. Please fill the Date override.", "danger")
                    return redirect(request.url)

                if team_score == opp_score:
                    flash("Team score and opponent score cannot be equal. Please verify overrides.", "danger")
                    return redirect(request.url)

                result = "W" if team_score > opp_score else "L"

                game_type = override_game_type if override_game_type in {"Season", "Friendly", "Playoff"} else (parsed.get("game_type") or "Season")

                # Duplicate check
                existing = Game.query.filter_by(sort_date=sort_date, opponent=opponent).first()
                if existing:
                    flash(f"Game already exists: {existing.opponent} on {existing.date}", "warning")
                    return redirect(url_for("main.index"))

                players = parsed.get("players") or []
                if not players:
                    flash("No player rows detected in the PDF. Please check PDF format.", "danger")
                    return redirect(request.url)

                game = Game(
                    date=date_display,
                    opponent=opponent,
                    team_score=team_score,
                    opponent_score=opp_score,
                    result=result,
                    game_type=game_type,
                    sort_date=sort_date,
                    source="IMPORT",
                )
                db.session.add(game)
                db.session.flush()

                for player in players:
                    if not player.get("name"):
                        continue

                    stat = PlayerStat(
                        game_id=game.id,
                        player_name=player.get("name", "").strip(),
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
                    )
                    db.session.add(stat)

                db.session.commit()
                flash(f"Successfully imported game (PDF): {game.opponent} ({game.result})", "success")
                return redirect(url_for("main.game_detail", game_id=game.id))

            # --- JSON Import ---
            elif import_type == "json":
                if "json_file" not in request.files:
                    flash("No JSON file uploaded", "danger")
                    return redirect(request.url)

                file = request.files["json_file"]
                if file.filename == "":
                    flash("No file selected", "danger")
                    return redirect(request.url)

                if not allowed_file(file.filename) or not file.filename.lower().endswith(".json"):
                    flash("Only JSON files are allowed for JSON import", "danger")
                    return redirect(request.url)

                filename = secure_filename(file.filename)

                # Load JSON
                try:
                    data = json.load(file)
                except json.JSONDecodeError:
                    flash("Invalid JSON file format.", "danger")
                    return redirect(request.url)

                # Validate structure
                game_data = data.get("game")
                if not game_data:
                    flash("JSON file is missing required 'game' data.", "danger")
                    return redirect(request.url)

                # Coerce dates (prevents varchar(10) truncation on Game.date)
                date_display, sort_date = coerce_json_game_dates(game_data)
                if not date_display or len(date_display) != 10:
                    flash(f"Invalid game date in JSON: '{game_data.get('date')}'.", "danger")
                    return redirect(request.url)
                if not sort_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", sort_date):
                    flash(f"Invalid sort_date in JSON: '{game_data.get('sort_date')}'.", "danger")
                    return redirect(request.url)

                # Duplicate check
                existing = Game.query.filter_by(sort_date=sort_date, opponent=game_data.get("opponent")).first()
                if existing:
                    flash(f"Game already exists: {existing.opponent} on {existing.date}", "warning")
                    return redirect(url_for("main.index"))

                # Create Game
                game = Game(
                    date=date_display,
                    opponent=game_data.get("opponent"),
                    team_score=game_data.get("team_score", 0),
                    opponent_score=game_data.get("opponent_score", 0),
                    result=game_data.get("result", "W"),
                    game_type=game_data.get("game_type", "Season"),
                    sort_date=sort_date,
                    source="IMPORT_JSON",
                )
                db.session.add(game)
                db.session.flush()

                # Process PlayerStat
                for p_data in data.get("player_stats", []):
                    # Filter valid fields for PlayerStat model
                    valid_keys = {c.name for c in PlayerStat.__table__.columns if c.name not in ('id', 'game_id')}
                    stat_kwargs = {k: v for k, v in p_data.items() if k in valid_keys}

                    stat = PlayerStat(game_id=game.id, **stat_kwargs)
                    db.session.add(stat)

                # Process ShotEvent
                for s_data in data.get("shot_events", []):
                    valid_keys = {c.name for c in ShotEvent.__table__.columns if c.name not in ('id', 'game_id', 'play_id')}
                    shot_kwargs = {k: v for k, v in s_data.items() if k in valid_keys}

                    shot = ShotEvent(game_id=game.id, play_id=None, **shot_kwargs)
                    db.session.add(shot)

                # Process GameEvent (if present)
                for e_data in data.get("game_events", []):
                    valid_keys = {c.name for c in GameEvent.__table__.columns if c.name not in ('id', 'game_id', 'play_id')}
                    event_kwargs = {k: v for k, v in e_data.items() if k in valid_keys}

                    event = GameEvent(game_id=game.id, play_id=None, **event_kwargs)
                    db.session.add(event)

                db.session.commit()
                flash(f"Successfully imported game (JSON): {game.opponent} ({game.result})", "success")
                return redirect(url_for("main.game_detail", game_id=game.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error importing game: {str(e)}", "danger")
            current_app.logger.error(f"Upload error: {e}", exc_info=True)
            return redirect(request.url)

        finally:
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass

    return render_template("upload_game.html")


def serialize_model_instance(instance):
    """Serialize a single SQLAlchemy model instance to a dict of column values."""
    if not instance:
        return None
    data = {}
    for column in instance.__table__.columns:
        data[column.name] = getattr(instance, column.name)
    return data


@main_bp.route("/game/<int:game_id>/export-raw")
@login_required
def export_game_raw(game_id):
    """Export raw DB data for a specific game as JSON"""
    game = Game.query.get_or_404(game_id)

    # Collect data from DB only
    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    shot_events = ShotEvent.query.filter_by(game_id=game.id).all()

    # Try importing GameEvent if available (future proofing)
    game_events = []
    try:
        # We need to query this if the table exists and is populated
        game_events_rows = GameEvent.query.filter_by(game_id=game.id).order_by(GameEvent.timestamp).all()
        game_events = [serialize_model_instance(ev) for ev in game_events_rows]
    except Exception:
        # Table might be empty or query failing, just skip
        game_events = []

    # Build payload
    payload = {
        "schema_version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "source": {
            "app": "HoopsStats",
            "branch": "Dev"
        },
        "game": serialize_model_instance(game),
        "player_stats": [serialize_model_instance(s) for s in stats],
        "shot_events": [serialize_model_instance(se) for se in shot_events],
        "game_events": game_events
    }

    # Format filename
    safe_opponent = secure_filename(game.opponent)
    filename = f"game_raw_{game.sort_date}_{safe_opponent}.json"

    # Create response
    response = make_response(jsonify(payload))
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "application/json"

    return response
