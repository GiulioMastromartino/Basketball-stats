import os
import json
import re
import zipfile
from datetime import datetime
from werkzeug.utils import secure_filename

from flask import (
    Blueprint,
    abort,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
    make_response,
    send_file,
    session,
)
from io import BytesIO
from urllib.parse import unquote
from flask_login import login_required, current_user
from sqlalchemy import func
from weasyprint import HTML

from core.models import (
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    Player,
    db,
    Play,
    User,
    SystemSetting,
    Lineup,
    LineupSegment,
    PlayerLineupStats,
    OrganizationMembership,
    Organization,
    Team,
    Season,
    TeamAssignment,
    AdminAudit,
    log_admin_action,
)
from core.services.season_service import (
    create_season as create_team_season,
    delete_season as delete_team_season,
    list_seasons,
    resolve_request_season_id,
    set_active_season as activate_team_season,
)
from core.csv_processor import CSVProcessor
from core.charts import (
    generate_team_shot_chart,
    generate_team_scoring_trend,
    generate_shooting_trend_base64,
)
from core.parser import parse_game_pdf

from core.utils import (
    calculate_efficiency,
    calculate_efg_percent,
    calculate_game_score,
    calculate_ortg,
    calculate_pace,
    calculate_possessions,
    calculate_ppp,
    calculate_ts_percent,
    calculate_two_point_stats,
    parse_minutes,
    safe_percentage,
    normalize_date_to_display,
    normalize_shot_events,
)
from core.services.notification_service import notify_game, notify_player_performance
from core.services import create_game_from_live_data
from core.services.analytics_service import AnalyticsService
from web.decorators import gm_required, team_access_required, admin_view_required

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
    Supports YYYY-MM-DD in the date field.
    """
    raw_sort = (game_data.get("sort_date") or game_data.get("sortdate") or "").strip()
    raw_date = (game_data.get("date") or "").strip()

    sort_date = raw_sort
    if not sort_date and raw_date:
        # Check if raw_date is already YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            sort_date = raw_date
        else:
            # Try to derive sort_date from raw_date (DD/MM/YYYY or DD-MM-YYYY)
            sort_date = normalize_date_to_sort(raw_date)

    date_display = ""
    if sort_date and re.match(r"^\d{4}-\d{2}-\d{2}$", sort_date):
        try:
            date_display = datetime.strptime(sort_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            date_display = raw_date
    else:
        date_display = normalize_date_to_display(raw_date) or raw_date

    return date_display, sort_date


def _calculate_player_season_averages(player_name: str, current_game_id: int) -> dict:
    """Calculate season averages for a player up to but not including the current game."""
    # Get all games before the current game
    prior_games = (
        db.session.query(Game.id)
        .filter(Game.id < current_game_id)
        .order_by(Game.sort_date)
        .all()
    )

    prior_game_ids = [g.id for g in prior_games]

    if not prior_game_ids:
        # Return zeros if no prior games
        return {
            "points": 0.0,
            "reb": 0.0,
            "oreb": 0.0,
            "dreb": 0.0,
            "ast": 0.0,
            "stl": 0.0,
            "blk": 0.0,
            "tov": 0.0,
            "fgm": 0.0,
            "fga": 0.0,
            "fg_percent": 0.0,
            "tpm": 0.0,
            "tpa": 0.0,
            "tp_percent": 0.0,
            "ftm": 0.0,
            "fta": 0.0,
            "ft_percent": 0.0,
        }

    # Get player stats for prior games
    prior_stats = PlayerStat.query.filter(
        PlayerStat.player_name == player_name, PlayerStat.game_id.in_(prior_game_ids)
    ).all()

    if not prior_stats:
        return {
            "points": 0.0,
            "reb": 0.0,
            "oreb": 0.0,
            "dreb": 0.0,
            "ast": 0.0,
            "stl": 0.0,
            "blk": 0.0,
            "tov": 0.0,
            "fgm": 0.0,
            "fga": 0.0,
            "fg_percent": 0.0,
            "tpm": 0.0,
            "tpa": 0.0,
            "tp_percent": 0.0,
            "ftm": 0.0,
            "fta": 0.0,
            "ft_percent": 0.0,
        }

    # Calculate averages
    count = len(prior_stats)
    totals = {
        "points": 0,
        "reb": 0,
        "oreb": 0,
        "dreb": 0,
        "ast": 0,
        "stl": 0,
        "blk": 0,
        "tov": 0,
        "fgm": 0,
        "fga": 0,
        "ftm": 0,
        "fta": 0,
        "tpm": 0,
        "tpa": 0,
    }

    for stat in prior_stats:
        totals["points"] += stat.points
        totals["reb"] += stat.reb
        totals["oreb"] += stat.oreb
        totals["dreb"] += stat.dreb
        totals["ast"] += stat.ast
        totals["stl"] += stat.stl
        totals["blk"] += stat.blk
        totals["tov"] += stat.tov
        totals["fgm"] += stat.fgm
        totals["fga"] += stat.fga
        totals["ftm"] += stat.ftm
        totals["fta"] += stat.fta
        totals["tpm"] += stat.tpm
        totals["tpa"] += stat.tpa

    # Calculate percentages
    fg_percent = (totals["fgm"] / totals["fga"] * 100) if totals["fga"] > 0 else 0.0
    tp_percent = (totals["tpm"] / totals["tpa"] * 100) if totals["tpa"] > 0 else 0.0
    ft_percent = (totals["ftm"] / totals["fta"] * 100) if totals["fta"] > 0 else 0.0

    return {
        "points": totals["points"] / count,
        "reb": totals["reb"] / count,
        "oreb": totals["oreb"] / count,
        "dreb": totals["dreb"] / count,
        "ast": totals["ast"] / count,
        "stl": totals["stl"] / count,
        "blk": totals["blk"] / count,
        "tov": totals["tov"] / count,
        "fgm": totals["fgm"] / count,
        "fga": totals["fga"] / count,
        "fg_percent": fg_percent,
        "tpm": totals["tpm"] / count,
        "tpa": totals["tpa"] / count,
        "tp_percent": tp_percent,
        "ftm": totals["ftm"] / count,
        "fta": totals["fta"] / count,
        "ft_percent": ft_percent,
    }


def _notify_users_game_saved(game: Game):
    """Notify users/players that a game was saved, routing through notification_service."""
    try:
        # ── Game-addition notifications to users ──────────────────────────
        enabled = SystemSetting.get_value("notify_game_added", default="false")
        if enabled == "true":
            non_gm_users = User.query.filter(User.id.notin_(
                db.session.query(OrganizationMembership.user_id).filter_by(is_gm=True)
            )).all()

            if non_gm_users:
                pdf_attachment = None
                attach_pdf = SystemSetting.get_value("attach_game_pdf", default="false")
                if attach_pdf == "true":
                    try:
                        from core.pdf_exports import PlaysBasedPDFGenerator
                        generator = PlaysBasedPDFGenerator()
                        pdf_buffer = generator.generate_game_report_pdf(game.id)
                        pdf_bytes = pdf_buffer.getvalue()
                        filename = (
                            f"Game_Report_{game.opponent.replace(' ', '_')}_{game.date}.pdf"
                        )
                        if pdf_bytes:
                            pdf_attachment = (filename, pdf_bytes)
                    except Exception as e:
                        current_app.logger.error(
                            f"Failed to generate PDF for game {game.id}: {e}"
                        )

                notify_game(non_gm_users, game, pdf_attachment=pdf_attachment, team=game.team)

        # ── Player performance reports ────────────────────────────────────
        send_player_reports = SystemSetting.get_value(
            "send_player_reports", default="true"
        )
        if send_player_reports == "true":
            players = Player.query.filter_by(active=True).all()
            for player in players:
                game_stat = PlayerStat.query.filter_by(
                    game_id=game.id, player_name=player.name
                ).first()
                if not game_stat:
                    continue

                game_stats = {
                    "points": game_stat.points,
                    "reb":    game_stat.reb,
                    "oreb":   game_stat.oreb,
                    "dreb":   game_stat.dreb,
                    "ast":    game_stat.ast,
                    "stl":    game_stat.stl,
                    "blk":    game_stat.blk,
                    "tov":    game_stat.tov,
                    "fgm":    game_stat.fgm,
                    "fga":    game_stat.fga,
                    "fg_percent": game_stat.fg_percent,
                    "tpm":    game_stat.tpm,
                    "tpa":    game_stat.tpa,
                    "tp_percent": game_stat.tp_percent,
                    "ftm":    game_stat.ftm,
                    "fta":    game_stat.fta,
                    "ft_percent": game_stat.ft_percent,
                }
                season_avg = _calculate_player_season_averages(player.name, game.id)
                notify_player_performance(player, player.name, game, game_stats, season_avg)

    except Exception as e:
        current_app.logger.error(
            f"Failed to send game notification (Game ID {getattr(game, 'id', None)}): {e}"
        )


@main_bp.route("/landing")
def landing():
    """Landing page for unauthenticated users"""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    return render_template("landing_oss.html")


@main_bp.route("/")
@team_access_required
def index():
    """Dashboard home page"""
    if not current_user.is_authenticated:
        return redirect(url_for("main.landing"))
    team_id = session.get("current_team_id")
    games = Game.query.filter_by(team_id=team_id).order_by(Game.sort_date.desc()).all()
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
@team_access_required
def live_game():
    """Interface for live game stat tracking"""
    team_id = session.get("current_team_id")
    existing_players = [
        r[0]
        for r in db.session.query(PlayerStat.player_name)
        .join(Game)
        .filter(Game.team_id == team_id)
        .distinct()
        .order_by(PlayerStat.player_name)
        .all()
    ]

    plays_query = Play.query.filter_by(team_id=team_id).order_by(Play.play_type, Play.name).all()
    plays_list = [
        {
            "id": p.id,
            "name": p.name,
            "type": p.play_type,
            "description": p.description,
        }
        for p in plays_query
    ]

    now_date = datetime.now().strftime("%Y-%m-%d")
    return render_template(
        "live_game.html",
        existing_players=existing_players,
        now_date=now_date,
        plays=plays_list,
    )


@main_bp.route("/api/plays")
@login_required
@team_access_required
def api_plays():
    """API endpoint to get list of plays for live game selector"""
    team_id = session.get("current_team_id")
    plays = Play.query.filter_by(team_id=team_id).order_by(Play.play_type, Play.name).all()
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


@main_bp.route("/live-game/save", methods=["POST"])
@login_required
@team_access_required
def save_live_game():
    """Receive JSON data from live tracker and save to DB."""
    data = request.get_json()

    if not data:
        return (
            jsonify(
                {
                    "error": "No data received",
                    "details": "Request body is empty or not valid JSON",
                }
            ),
            400,
        )

    try:
        team_id = session.get("current_team_id")
        game = create_game_from_live_data(
            data, team_id=team_id,
            season_id=session.get("current_season_id") if session.get("current_season_id") != "ALL" else None,
        )
        current_app.logger.info(f"Live game saved successfully: Game ID {game.id}")

        # Notify non-admin users (optional PDF attachment)
        _notify_users_game_saved(game)

        return (
            jsonify(
                {
                    "success": True,
                    "game_id": game.id,
                    "message": f"Game saved: {game.opponent} ({game.result})",
                }
            ),
            201,
        )

    except ValueError as e:
        db.session.rollback()
        error_msg = str(e)
        current_app.logger.warning(f"Live game validation error: {error_msg}")
        return (
            jsonify({"error": "Validation Error", "details": error_msg}),
            400,
        )

    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        current_app.logger.error(f"Live game save error: {error_msg}", exc_info=True)

        # Always return the root cause so the UI can display it to all users.
        return (
            jsonify(
                {
                    "error": error_msg,
                    "details": error_msg,
                }
            ),
            500,
        )


@main_bp.route("/upload-game", methods=["GET", "POST"])
@login_required
@team_access_required
def upload_game():
    """Upload a CSV, PDF, or JSON file to add a game"""
    if request.method == "POST":
        team_id = session.get("current_team_id")
        import_type = request.form.get("import_type", "csv").lower().strip()
        if import_type not in {"csv", "pdf", "json"}:
            import_type = "csv"

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        try:
            # --- CSV Import (Multiple Files) ---
            if import_type == "csv":
                files = request.files.getlist("csv_file")
                if not files or files[0].filename == "":
                    flash("No CSV file uploaded", "danger")
                    return redirect(request.url)

                success_count = 0
                errors = []

                for file in files:
                    filepath = None
                    try:
                        if not file or file.filename == "":
                            continue

                        if not allowed_file(
                            file.filename
                        ) or not file.filename.lower().endswith(".csv"):
                            errors.append(
                                f"{file.filename}: Invalid file type (must be .csv)"
                            )
                            continue

                        filename = secure_filename(file.filename)
                        filepath = os.path.join(upload_folder, filename)
                        file.save(filepath)

                        info = CSVProcessor.parse_filename(filename)
                        if not info:
                            errors.append(f"{file.filename}: Invalid filename format")
                            continue

                        existing = Game.query.filter_by(
                            sort_date=info["sort_date"], opponent=info["opponent"], team_id=team_id
                        ).first()
                        if existing:
                            errors.append(
                                f"{file.filename}: Game already exists ({existing.opponent} on {existing.date})"
                            )
                            continue

                        game_data = CSVProcessor.process_game(filepath, info)
                        if not game_data:
                            errors.append(f"{file.filename}: Failed to process content")
                            continue

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
                                reb_conceded=int(player.get("reb_conceded", 0) or 0),
                            )
                            db.session.add(stat)

                        db.session.commit()
                        _notify_users_game_saved(game)
                        success_count += 1

                    except Exception as e:
                        db.session.rollback()
                        errors.append(f"{file.filename}: {str(e)}")
                    finally:
                        if filepath and os.path.exists(filepath):
                            try:
                                os.remove(filepath)
                            except OSError:
                                pass

                if success_count > 0:
                    flash(
                        f"Successfully imported {success_count} CSV game(s).", "success"
                    )

                if errors:
                    flash(
                        f"Errors occurred with {len(errors)} file(s): "
                        + "; ".join(errors[:5])
                        + ("..." if len(errors) > 5 else ""),
                        "danger",
                    )

                return redirect(url_for("main.index"))

            # --- PDF import (Single File) ---
            elif import_type == "pdf":
                if "pdf_file" not in request.files:
                    flash("No PDF file uploaded", "danger")
                    return redirect(request.url)

                file = request.files["pdf_file"]
                if file.filename == "":
                    flash("No file selected", "danger")
                    return redirect(request.url)

                filepath = None
                try:
                    if not allowed_file(
                        file.filename
                    ) or not file.filename.lower().endswith(".pdf"):
                        flash("Only PDF files are allowed for PDF import", "danger")
                        return redirect(request.url)

                    filename = secure_filename(file.filename)
                    filepath = os.path.join(upload_folder, filename)
                    file.save(filepath)

                    parsed = parse_game_pdf(filepath)

                    # Overrides (optional)
                    override_opponent = (request.form.get("pdf_opponent") or "").strip()
                    override_date = (request.form.get("pdf_date") or "").strip()
                    override_team_score = (
                        request.form.get("pdf_team_score") or ""
                    ).strip()
                    override_opponent_score = (
                        request.form.get("pdf_opponent_score") or ""
                    ).strip()
                    override_game_type = (
                        request.form.get("pdf_game_type") or ""
                    ).strip()

                    opponent = override_opponent or parsed.get("opponent") or "Unknown"

                    date_display = (
                        normalize_date_to_display(override_date)
                        if override_date
                        else (parsed.get("date") or "")
                    )
                    if override_date and not date_display:
                        flash(
                            "Invalid date format. Use DD-MM-YYYY or DD/MM/YYYY.",
                            "danger",
                        )
                        return redirect(request.url)

                    sort_date = (
                        normalize_date_to_sort(override_date)
                        if override_date
                        else (parsed.get("sort_date") or "")
                    )

                    # Scores
                    team_score = parsed.get("team_score") or 0
                    opp_score = parsed.get("opponent_score") or 0
                    if override_team_score:
                        team_score = int(override_team_score)
                    if override_opponent_score:
                        opp_score = int(override_opponent_score)

                    if not date_display or not sort_date:
                        flash(
                            "Could not determine game date from PDF. Please fill the Date override.",
                            "danger",
                        )
                        return redirect(request.url)

                    if team_score == opp_score:
                        flash(
                            "Team score and opponent score cannot be equal. Please verify overrides.",
                            "danger",
                        )
                        return redirect(request.url)

                    result = "W" if team_score > opp_score else "L"

                    game_type = (
                        override_game_type
                        if override_game_type in {"Season", "Friendly", "Playoff"}
                        else (parsed.get("game_type") or "Season")
                    )

                    # Duplicate check
                    existing = Game.query.filter_by(
                        sort_date=sort_date, opponent=opponent, team_id=team_id
                    ).first()
                    if existing:
                        flash(
                            f"Game already exists: {existing.opponent} on {existing.date}",
                            "warning",
                        )
                        return redirect(url_for("main.index"))

                    players = parsed.get("players") or []
                    if not players:
                        flash(
                            "No player rows detected in the PDF. Please check PDF format.",
                            "danger",
                        )
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
                            reb_conceded=int(player.get("reb_conceded", 0) or 0),
                        )
                        db.session.add(stat)

                    db.session.commit()
                    _notify_users_game_saved(game)

                    flash(
                        f"Successfully imported game (PDF): {game.opponent} ({game.result})",
                        "success",
                    )
                    return redirect(url_for("main.game_detail", game_id=game.id))

                except Exception as e:
                    db.session.rollback()
                    flash(f"Error importing PDF: {str(e)}", "danger")
                    current_app.logger.error(f"Upload error: {e}", exc_info=True)
                    return redirect(request.url)
                finally:
                    if filepath and os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except OSError:
                            pass

            # --- JSON Import (Multiple Files) ---
            elif import_type == "json":
                files = request.files.getlist("json_file")
                if not files or files[0].filename == "":
                    flash("No JSON file uploaded", "danger")
                    return redirect(request.url)

                success_count = 0
                errors = []

                for file in files:
                    try:
                        if not file or file.filename == "":
                            continue

                        if not allowed_file(
                            file.filename
                        ) or not file.filename.lower().endswith(".json"):
                            errors.append(f"{file.filename}: Invalid file type")
                            continue

                        try:
                            data = json.load(file)
                        except json.JSONDecodeError:
                            errors.append(f"{file.filename}: Invalid JSON format")
                            continue

                        # Extract basic info for duplicate check
                        game_data = data.get("game", data)
                        date_display, sort_date = coerce_json_game_dates(game_data)
                        opponent = (
                            game_data.get("opponent")
                            or game_data.get("Opponent")
                            or game_data.get("vs")
                            or ""
                        ).strip()

                        if not sort_date or not opponent:
                            errors.append(f"{file.filename}: Missing date or opponent")
                            continue

                        existing = Game.query.filter_by(
                            sort_date=sort_date, opponent=opponent, team_id=team_id
                        ).first()
                        if existing:
                            errors.append(
                                f"{file.filename}: Game already exists ({existing.opponent})"
                            )
                            continue

                        # Use service to handle the heavy lifting (supports Schema 4, lineups, plays, etc.)
                        create_game_from_live_data(
                            data,
                            team_id=session.get("current_team_id"),
                            season_id=session.get("current_season_id") if session.get("current_season_id") != "ALL" else None,
                        )
                        success_count += 1

                    except Exception as e:
                        db.session.rollback()
                        errors.append(f"{file.filename}: {str(e)}")

                if success_count > 0:
                    flash(
                        f"Successfully imported {success_count} JSON game(s).",
                        "success",
                    )

                if errors:
                    flash(
                        f"Errors occurred with {len(errors)} file(s): "
                        + "; ".join(errors[:5])
                        + ("..." if len(errors) > 5 else ""),
                        "danger",
                    )

                return redirect(url_for("main.index"))

        except Exception as e:
            db.session.rollback()
            flash(f"Critical error during import: {str(e)}", "danger")
            current_app.logger.error(f"Upload error: {e}", exc_info=True)
            return redirect(request.url)

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
@team_access_required
def export_game_raw(game_id):
    """Export raw DB data for a specific game as JSON"""
    team_id = session.get("current_team_id")
    game = Game.query.filter_by(id=game_id, team_id=team_id).first()
    if not game:
        abort(404)

    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    shot_events = ShotEvent.query.filter_by(game_id=game.id).all()

    game_events = []
    try:
        game_events_rows = (
            GameEvent.query.filter_by(game_id=game.id)
            .order_by(GameEvent.timestamp)
            .all()
        )
        game_events = [serialize_model_instance(ev) for ev in game_events_rows]
    except Exception:
        game_events = []

    payload = {
        "schema_version": str(game.schema_version or "1.0"),
        "exported_at": datetime.utcnow().isoformat(),
        "source": {"app": "HoopsStats", "branch": "Dev"},
        "game": serialize_model_instance(game),
        "player_stats": [serialize_model_instance(s) for s in stats],
        "shot_events": [serialize_model_instance(se) for se in shot_events],
        "game_events": game_events,
    }

    safe_opponent = secure_filename(game.opponent)
    filename = f"game_raw_{game.sort_date}_{safe_opponent}.json"

    response = make_response(jsonify(payload))
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    response.headers["Content-Type"] = "application/json"

    return response


@main_bp.route("/game/<int:game_id>")
@login_required
@team_access_required
def game_detail(game_id):
    """Detailed stats for a specific game with Advanced Metrics"""
    team_id = session.get("current_team_id")
    game = Game.query.filter_by(id=game_id, team_id=team_id).first()
    if not game:
        abort(404)
    context = AnalyticsService.build_game_detail(game_id)
    return render_template("game_detail.html", **context)


@main_bp.route("/game/<int:game_id>/delete", methods=["POST"])
@login_required
@team_access_required
@gm_required
def delete_game(game_id):
    """Delete a game and all associated stats/events."""
    team_id = session.get("current_team_id")
    game = Game.query.filter_by(id=game_id, team_id=team_id).first()
    if not game:
        abort(404)

    try:
        PlayerStat.query.filter_by(game_id=game.id).delete()
        ShotEvent.query.filter_by(game_id=game.id).delete()
        GameEvent.query.filter_by(game_id=game.id).delete()

        # Get lineup_ids before deleting segments (to update cached stats)
        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        segment_ids = [s.id for s in segments]
        affected_lineup_ids = list(set(s.lineup_id for s in segments if s.lineup_id))

        # Delete PlayerLineupStats
        if segment_ids:
            PlayerLineupStats.query.filter(
                PlayerLineupStats.lineup_segment_id.in_(segment_ids)
            ).delete()

        # Delete LineupSegments
        LineupSegment.query.filter_by(game_id=game.id).delete()

        # Update or delete affected Lineups
        from core.services.lineup_service import update_lineup_cached_stats

        for lineup_id in affected_lineup_ids:
            lineup = Lineup.query.get(lineup_id)
            if lineup:
                # Check if lineup still has segments
                remaining_segments = LineupSegment.query.filter_by(
                    lineup_id=lineup_id
                ).count()
                if remaining_segments == 0:
                    db.session.delete(lineup)
                else:
                    update_lineup_cached_stats(lineup_id)

        db.session.delete(game)
        db.session.commit()
        flash(f"Deleted game: {game.opponent} on {game.date}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting game: {str(e)}", "danger")
        current_app.logger.error(f"Delete error: {e}", exc_info=True)

    return redirect(url_for("main.index"))


@main_bp.route("/player/<player_name>")
@login_required
@team_access_required
def player_detail(player_name):
    """Detailed player profile with comprehensive stats and charts"""
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"
    season_id = resolve_request_season_id(session.get("current_team_id"))
    try:
        context = AnalyticsService.build_player_detail(
            player_name, game_type,
            team_id=session.get("current_team_id"), season_id=season_id
        )
    except ValueError as e:
        flash(str(e) + " for " + player_name, "warning")
        return redirect(url_for("main.players"))
    return render_template(
        "player_detail.html",
        **context,
        report_url=url_for(
            "analytics.player_report_pdf", player_name=player_name, game_type=game_type, season=season_id
        ),
        back_url=url_for("main.players", game_type=game_type, season=season_id),
        back_label="Back to Players",
    )


@main_bp.route("/player/<player_name>/game-detail")
@login_required
@team_access_required
def player_game_detail(player_name):
    """Player game detail with comprehensive stats and charts"""
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"
    season_id = resolve_request_season_id(session.get("current_team_id"))
    try:
        context = AnalyticsService.build_player_game_detail(
            player_name, game_type,
            team_id=session.get("current_team_id"), season_id=season_id
        )
    except ValueError:
        flash("No stats available for this player", "warning")
        return redirect(url_for("main.players", game_type=game_type))
    return render_template(
        "player_game_detail.html",
        **context,
        report_url=url_for(
            "reports.player_report_pdf", player_name=player_name, game_type=game_type, season=season_id
        ),
        back_url=url_for("main.players", game_type=game_type, season=season_id),
        back_label="Back to Players",
    )


@main_bp.route("/team-detail")
@login_required
@team_access_required
def team_detail():
    """Team totals rendered on the same detail page as players."""
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"
    excluded_player = (request.args.get("exclude_player") or "").strip()
    season_id = resolve_request_season_id(session.get("current_team_id"))
    context = AnalyticsService.build_team_detail_context(
        game_type, excluded_player,
        team_id=session.get("current_team_id"), season_id=season_id
    )
    return render_template("player_detail.html", **context)


@main_bp.route("/players")
@login_required
@team_access_required
def players():
    """List of all players with Comprehensive Advanced Stats"""
    view = request.args.get("view", "cards")
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    try:
        limit = int(request.args.get("limit", 0))
        if limit < 0:
            limit = 0
    except ValueError:
        limit = 0

    sort_by = request.args.get("sort", "ppg")
    order = request.args.get("order", "desc")
    excluded_player = (request.args.get("exclude_player") or "").strip()
    season_id = resolve_request_season_id(session.get("current_team_id"))

    context = AnalyticsService.build_players_listing_context(
        game_type, limit, sort_by, order, excluded_player,
        team_id=session.get("current_team_id"), season_id=season_id
    )

    template = "players_table.html" if view == "table" else "players.html"

    return render_template(
        template,
        stats=context["stats"],
        total_row=context["total_row"],
        all_player_names=context["all_player_names"],
        filters=context["filters"],
    )


@main_bp.route("/players/cards.pdf")
@login_required
@team_access_required
def players_cards_pdf():
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    try:
        limit = int(request.args.get("limit", 0))
        if limit < 0:
            limit = 0
    except ValueError:
        limit = 0

    sort_by = request.args.get("sort", "ppg")
    order = request.args.get("order", "desc")
    excluded_player = (request.args.get("exclude_player") or "").strip()

    context = AnalyticsService.build_players_listing_context(
        game_type, limit, sort_by, order, excluded_player,
        team_id=session.get("current_team_id"),
        season_id=resolve_request_season_id(session.get("current_team_id")),
    )

    html = render_template("players_cards_pdf.html", **context)
    pdf_bytes = HTML(string=html, base_url=request.host_url).write_pdf()
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"player_cards_{game_type}.pdf",
    )


@main_bp.route("/players/pages.zip")
@login_required
@team_access_required
def players_pages_zip():

    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    try:
        limit = int(request.args.get("limit", 0))
        if limit < 0:
            limit = 0
    except ValueError:
        limit = 0

    sort_by = request.args.get("sort", "ppg")
    order = request.args.get("order", "desc")
    excluded_player = (request.args.get("exclude_player") or "").strip()
    season_id = resolve_request_season_id(session.get("current_team_id"))

    context = AnalyticsService.build_players_listing_context(
        game_type, limit, sort_by, order, excluded_player,
        team_id=session.get("current_team_id"), season_id=season_id
    )
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        team_context = AnalyticsService.build_team_detail_context(
            game_type, excluded_player,
            team_id=session.get("current_team_id"), season_id=season_id
        )
        team_html = render_template(
            "player_detail.html",
            **team_context,
            pdf_mode=True,
            report_url="",
            back_url="",
        )
        team_pdf = HTML(string=team_html, base_url=request.host_url).write_pdf()
        zipf.writestr("Team_Total_Page.pdf", team_pdf)

        for player in context["stats"]:
            detail_context = AnalyticsService.build_player_detail(
                player["player_name"], game_type,
                team_id=session.get("current_team_id"), season_id=season_id
            )
            html = render_template(
                "player_detail.html",
                **detail_context,
                pdf_mode=True,
                report_url="",
                back_url="",
            )
            pdf_data = HTML(string=html, base_url=request.host_url).write_pdf()
            filename = f"{player['player_name'].replace(' ', '_')}_page.pdf"
            zipf.writestr(filename, pdf_data)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"player_pages_{game_type}.zip",
    )


@main_bp.route("/games-list")
@login_required
@team_access_required
def games():
    """Summary of performance against opponents (formerly teams)"""
    team_id = session.get("current_team_id")
    season_id = resolve_request_season_id(team_id)
    opp_query = Game.query.filter(Game.team_id == team_id)
    if season_id != "ALL":
        opp_query = opp_query.filter(Game.season_id == int(season_id))
    results = opp_query.with_entities(Game.opponent).distinct().all()

    team_stats = []
    for r in results:
        opp_name = r[0]
        opp_q = Game.query.filter_by(opponent=opp_name, team_id=team_id)
        if season_id != "ALL":
            opp_q = opp_q.filter(Game.season_id == int(season_id))
        opp_games = opp_q.all()
        wins = sum(1 for g in opp_games if g.result == "W")
        losses = len(opp_games) - wins

        if len(opp_games) > 0:
            avg_team_score = sum(g.team_score for g in opp_games) / len(opp_games)
            avg_opp_score = sum(g.opponent_score for g in opp_games) / len(opp_games)
            avg_score = f"{int(avg_team_score)}-{int(avg_opp_score)}"
        else:
            avg_score = "0-0"

        team_stats.append(
            {
                "name": opp_name,
                "games": len(opp_games),
                "record": f"{wins}-{losses}",
                "avg_score": avg_score,
            }
        )

    return render_template("teams.html", teams=team_stats)


@main_bp.route("/teams/<opponent_name>")
@login_required
@team_access_required
def opponent_games(opponent_name):
    """Detailed performance view against a specific opponent"""
    team_id = session.get("current_team_id")
    season_id = resolve_request_season_id(team_id)
    opp_q = Game.query.filter_by(opponent=opponent_name, team_id=team_id)
    if season_id != "ALL":
        opp_q = opp_q.filter(Game.season_id == int(season_id))
    opp_games = opp_q.order_by(Game.sort_date.desc()).all()
    context = AnalyticsService.build_opponent_detail_context(opponent_name, opp_games)
    return render_template("opponent_detail.html", **context)


@main_bp.route("/advanced-analytics")
@login_required
@team_access_required
def advanced_analytics():
    """Advanced analytics dashboard"""
    team_id = session.get("current_team_id")
    # Get players for filters
    players = (
        db.session.query(PlayerStat.player_name)
        .join(Game, PlayerStat.game_id == Game.id)
        .filter(Game.team_id == team_id)
        .distinct()
        .order_by(PlayerStat.player_name)
        .all()
    )
    player_names = [p[0] for p in players]

    # Get plays for filters
    plays = Play.query.filter_by(team_id=team_id).order_by(Play.name).all()

    # Get games for filters
    games = Game.query.filter_by(team_id=team_id).order_by(Game.sort_date.desc()).all()

    return render_template(
        "advanced_analytics.html", players=player_names, plays=plays, games=games
    )


@main_bp.route("/game/<int:game_id>/advanced-report")
@login_required
@team_access_required
def advanced_game_report(game_id):
    """Advanced game report page with comprehensive analytics"""
    team_id = session.get("current_team_id")
    game = Game.query.filter_by(id=game_id, team_id=team_id).first()
    if not game:
        abort(404)
    return render_template(
        "reports/advanced_game_report.html", game=game, game_id=game_id
    )


# =============================================================================
# LINEUPS PAGES
# =============================================================================


@main_bp.route("/lineups")
@login_required
@team_access_required
def lineups_page():
    """Lineups browser page - shows all lineup combinations with stats."""
    return render_template("lineups.html")


@main_bp.route("/lineup/<int:lineup_id>")
@login_required
@team_access_required
def lineup_card(lineup_id):
    """Single lineup card page with detailed stats."""
    from core.models import Lineup

    team_id = session.get("current_team_id")
    lineup = Lineup.query.filter_by(id=lineup_id, team_id=team_id).first()
    if not lineup:
        abort(404)
    return render_template("lineup_card.html", lineup=lineup)


@main_bp.route("/game/<int:game_id>/lineup-combinations")
@login_required
@team_access_required
def game_lineup_combinations(game_id):
    """Game subpage with top 3 lineups, duos, and trios."""
    team_id = session.get("current_team_id")
    game = Game.query.filter_by(id=game_id, team_id=team_id).first()
    if not game:
        abort(404)
    from core.advanced_analytics import LineupAnalytics

    try:
        top_lineups = LineupAnalytics.get_game_lineup_rankings(game_id, top_n=3)
    except Exception:
        top_lineups = []

    try:
        top_duos = LineupAnalytics.get_combination_net_differentials(
            combination_type="duo",
            game_ids=[game_id],
            min_possessions=10,
            top_n=3,
            require_positive=False,
        )
    except Exception:
        top_duos = []

    try:
        top_trios = LineupAnalytics.get_combination_net_differentials(
            combination_type="trio",
            game_ids=[game_id],
            min_possessions=10,
            top_n=3,
            require_positive=False,
        )
    except Exception:
        top_trios = []

    return render_template(
        "game_lineup_combinations.html",
        game=game,
        top_lineups=top_lineups,
        top_duos=top_duos,
        top_trios=top_trios,
    )


@main_bp.route("/lineup-combo/<combo_type>/<path:players_key>")
@login_required
@team_access_required
def lineup_combo_card(combo_type, players_key):
    """Single duo/trio combination card page."""
    combo_type = (combo_type or "").strip().lower()
    if combo_type not in {"duo", "trio"}:
        abort(404)

    raw_players = unquote(players_key or "")
    players = [p.strip() for p in raw_players.split(",") if p.strip()]
    expected_count = 2 if combo_type == "duo" else 3
    if len(players) != expected_count:
        abort(404)

    return render_template(
        "lineup_combo_card.html",
        combo_type=combo_type,
        players=sorted(players),
    )


# =============================================================================
# TEST GAME GENERATOR
# =============================================================================


@main_bp.route("/create-test-game", methods=["POST"])
@login_required
@gm_required
def create_test_game():
    """Create a comprehensive test game with all features for testing."""
    import sys
    import os

    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )

    from scripts.generate_test_game import generate_test_game_payload
    import gc

    try:
        # Clear any existing memory before starting heavy operation
        gc.collect()

        payload = generate_test_game_payload()

        # After payload is ready, try to free any generation-time overhead
        gc.collect()

        game = create_game_from_live_data(
            payload,
            team_id=session.get("current_team_id"),
            season_id=session.get("current_season_id") if session.get("current_season_id") != "ALL" else None,
        )

        # Clear payload from memory after import
        del payload
        gc.collect()

        current_app.logger.info(f"Test game created: Game ID {game.id}")
        flash(
            f"Test game created successfully! {game.opponent} ({game.team_score}-{game.opponent_score})",
            "success",
        )
        return redirect(url_for("main.game_detail", game_id=game.id))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to create test game: {e}", exc_info=True)
        flash(f"Error creating test game: {str(e)}", "danger")
        return redirect(url_for("main.upload_game"))


# =============================================================================
# GM DASHBOARD
# =============================================================================


@main_bp.route("/gm/dashboard")
@login_required
@admin_view_required
def gm_dashboard():
    """GM dashboard showing org-wide overview with all teams."""
    org = Organization.query.get(getattr(current_user, "organization_id", None) or 0)
    if org is None:
        org = Organization.query.order_by(Organization.id).first()
    if org is None:
        flash("No organization exists yet.", "warning")
        return redirect(url_for("main.index"))
    # Session org switcher (GM plan idea 4): multi-org GMs pick context.
    requested_org = request.args.get("org_id", type=int)
    if requested_org:
        mem = OrganizationMembership.query.filter_by(
            user_id=current_user.id, organization_id=requested_org).first()
        if mem or getattr(current_user, "is_gm", False):
            org = Organization.query.get(requested_org) or org
    my_orgs = (Organization.query
               .join(OrganizationMembership,
                     OrganizationMembership.organization_id == Organization.id)
               .filter(OrganizationMembership.user_id == current_user.id)
               .order_by(Organization.name).all())
    teams = list(current_user.assigned_teams)
    if not teams and current_app.config.get("LOGIN_DISABLED"):
        # Dev/no-auth mode acts as GM without assignments: show the org's teams.
        teams = Team.query.filter_by(organization_id=org.id).order_by(Team.name).all()
    team_data = []
    for team in teams:
        games_q = Game.query.filter_by(team_id=team.id)
        total = games_q.count()
        wins = games_q.filter_by(result="W").count()
        losses = games_q.filter_by(result="L").count()
        pts = db.session.query(func.sum(Game.team_score)).filter_by(team_id=team.id).scalar() or 0
        opp_pts = db.session.query(func.sum(Game.opponent_score)).filter_by(team_id=team.id).scalar() or 0
        players = Player.query.filter_by(team_id=team.id, active=True).count()
        team_data.append({
            "id": team.id,
            "name": team.name,
            "slug": team.slug,
            "games": total,
            "wins": wins,
            "losses": losses,
            "points": pts,
            "opp_points": opp_pts,
            "avg_ppg": round(pts / total, 1) if total else 0,
            "avg_opp_ppg": round(opp_pts / total, 1) if total else 0,
            "players": players,
        })
    members = OrganizationMembership.query.filter_by(organization_id=org.id).count()
    # Empty-state guidance (GM plan idea 6): checklist for fresh orgs.
    has_seasons = Season.query.join(Team).filter(
        Team.organization_id == org.id).count() > 0
    has_games = Game.query.join(Team).filter(
        Team.organization_id == org.id).count() > 0
    checklist = {
        "has_teams": len(team_data) > 0,
        "has_members": members > 0,
        "has_seasons": has_seasons,
        "has_players": sum(t["players"] for t in team_data) > 0,
        "has_games": has_games,
    }
    return render_template(
        "gm/dashboard.html",
        org=org,
        team_data=team_data,
        members=members,
        my_orgs=my_orgs,
        checklist=checklist,
        is_auditor=bool(getattr(current_user, "is_auditor", False)),
    )


@main_bp.route("/switch-team", methods=["POST"])
@login_required
def switch_team():
    """Switch the current team context in the session."""
    team_id = request.form.get("team_id", type=int)
    if not team_id:
        flash("No team selected.", "warning")
        return redirect(request.referrer or url_for("main.index"))
    team = Team.query.get(team_id)
    if not team or team not in current_user.assigned_teams:
        flash("You do not have access to that team.", "danger")
        return redirect(request.referrer or url_for("main.index"))
    session["current_team_id"] = team.id
    session["current_team_name"] = team.name
    flash(f"Switched to {team.name}.", "success")
    return redirect(request.referrer or url_for("main.index"))


@main_bp.route("/switch-org", methods=["POST"])
@login_required
def switch_org():
    """Switch the session org context (GM plan idea 4, mirrors switch_team)."""
    org_id = request.form.get("org_id", type=int)
    if not org_id:
        flash("No organization selected.", "warning")
        return redirect(request.referrer or url_for("main.index"))
    org = Organization.query.get(org_id)
    if not org:
        flash("Unknown organization.", "danger")
        return redirect(request.referrer or url_for("main.index"))
    mem = OrganizationMembership.query.filter_by(
        user_id=current_user.id, organization_id=org.id).first()
    if not mem and not getattr(current_user, "is_gm", False) \
            and not current_app.config.get("LOGIN_DISABLED"):
        flash("You do not belong to that organization.", "danger")
        return redirect(request.referrer or url_for("main.index"))
    session["current_org_id"] = org.id
    # Point the team context at the first accessible team of that org.
    teams = Team.query.filter_by(organization_id=org.id).order_by(Team.name).all()
    if teams:
        session["current_team_id"] = teams[0].id
        session["current_team_name"] = teams[0].name
    flash(f"Switched to {org.name}.", "success")
    return redirect(request.referrer or url_for("main.index"))


# =============================================================================
# ADMIN PANEL
# =============================================================================

VALID_SECTIONS = {"users", "players", "settings", "seasons", "orgs", "matrix", "activity"}


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "unnamed"


def _safe_next(default_endpoint="main.admin_panel", **values):
    """Redirect target for org/team forms: honor a relative ``next`` field."""
    nxt = (request.form.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for(default_endpoint, **values))


@main_bp.route("/admin")
@main_bp.route("/admin/<section>")
@login_required
@admin_view_required
def admin_panel(section="users"):
    """Admin panel - manage users, players, settings and seasons"""
    if section not in VALID_SECTIONS:
        section = "users"

    users = User.query.order_by(User.username).all()
    team_id = session.get("current_team_id")
    players = Player.query.filter_by(team_id=team_id).order_by(Player.name).all()
    seasons = list_seasons(team_id) if team_id else []
    orgs = Organization.query.order_by(Organization.name).all()
    all_teams = Team.query.order_by(Team.name).all()

    # Org workspace filter (GM plan C-Phase 2): ?org_id narrows orgs/matrix.
    active_org_id = request.args.get("org_id", type=int) \
        or session.get("current_org_id") \
        or getattr(current_user, "organization_id", None)
    if active_org_id and not Organization.query.get(active_org_id):
        active_org_id = None
    visible_orgs = ([o for o in orgs if o.id == active_org_id]
                    if active_org_id else orgs)
    visible_teams = ([t for t in all_teams if t.organization_id == active_org_id]
                     if active_org_id else all_teams)

    # Assignment matrix (GM plan C-Phase 1): team ids per user id.
    assignments = {}
    team_gms = {}
    for ta in TeamAssignment.query.all():
        assignments.setdefault(ta.user_id, set()).add(ta.team_id)
        if ta.is_team_gm:
            team_gms.setdefault(ta.user_id, set()).add(ta.team_id)

    # Audit trail viewer (GM plan C-Phase 4): latest 100 entries.
    audit_entries = (AdminAudit.query
                     .order_by(AdminAudit.created_at.desc())
                     .limit(100).all())

    settings_data = db.session.query(SystemSetting).all()
    settings = {s.key: s.value for s in settings_data}

    return render_template(
        "auth/admin.html",
        users=users,
        players=players,
        seasons=seasons,
        orgs=orgs,
        visible_orgs=visible_orgs,
        all_teams=all_teams,
        visible_teams=visible_teams,
        active_org_id=active_org_id,
        assignments=assignments,
        team_gms=team_gms,
        audit_entries=audit_entries,
        is_auditor=bool(getattr(current_user, "is_auditor", False)),
        settings=settings,
        section=section,
    )


@main_bp.route("/seasons/create", methods=["POST"])
@login_required
@gm_required
def create_season():
    """Create a new season for the current team."""
    team_id = session.get("current_team_id")
    try:
        season = create_team_season(
            team_id,
            name=request.form.get("name", ""),
            start_date=request.form.get("start_date", ""),
            end_date=request.form.get("end_date", ""),
            set_active=bool(request.form.get("set_active")),
        )
        flash(f"Season '{season.name}' created.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("main.admin_panel", section="seasons"))


@main_bp.route("/seasons/<int:season_id>/activate", methods=["POST"])
@login_required
@gm_required
def activate_season(season_id):
    """Set a season as the active one."""
    try:
        season = activate_team_season(session.get("current_team_id"), season_id)
        session["current_season_id"] = season.id
        flash(f"Season '{season.name}' is now active.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("main.admin_panel", section="seasons"))


@main_bp.route("/seasons/<int:season_id>/delete", methods=["POST"])
@login_required
@gm_required
def delete_season(season_id):
    """Delete an empty season."""
    try:
        delete_team_season(session.get("current_team_id"), season_id)
        if session.get("current_season_id") == season_id:
            session.pop("current_season_id", None)
        flash("Season deleted.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    return redirect(url_for("main.admin_panel", section="seasons"))


@main_bp.route("/orgs/create", methods=["POST"])
@login_required
@gm_required
def create_org():
    """Create a new organization."""
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Organization name is required.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    slug = _slugify(name)
    if Organization.query.filter_by(slug=slug).first():
        flash(f"Organization '{name}' already exists.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    org = Organization(name=name, slug=slug)
    db.session.add(org)
    db.session.commit()
    log_admin_action(current_user, "org.create", f"created organization '{name}'",
                     target_type="org", target_id=org.id)
    flash(f"Organization '{name}' created.", "success")
    return redirect(url_for("main.admin_panel", section="orgs"))


@main_bp.route("/orgs/<int:org_id>/delete", methods=["POST"])
@login_required
@gm_required
def delete_org(org_id):
    """Delete an organization with no teams or members."""
    org = Organization.query.get_or_404(org_id)
    if Team.query.filter_by(organization_id=org.id).count():
        flash("Cannot delete an organization that has teams.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    if OrganizationMembership.query.filter_by(organization_id=org.id).count():
        flash("Cannot delete an organization that has members.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    db.session.delete(org)
    db.session.commit()
    log_admin_action(current_user, "org.delete", f"deleted organization '{org.name}'",
                     target_type="org", target_id=org_id)
    flash(f"Organization '{org.name}' deleted.", "success")
    return redirect(url_for("main.admin_panel", section="orgs"))


@main_bp.route("/orgs/<int:org_id>/rename", methods=["POST"])
@login_required
@gm_required
def rename_org(org_id):
    """Rename an organization (GM plan C-Phase 3). Slugs stay internal."""
    org = Organization.query.get_or_404(org_id)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Organization name is required.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    slug = _slugify(name)
    dup = Organization.query.filter(
        Organization.slug == slug, Organization.id != org.id).first()
    if dup:
        flash(f"Another organization already uses '{name}'.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    old = org.name
    org.name = name
    org.slug = slug
    db.session.commit()
    log_admin_action(current_user, "org.rename",
                     f"renamed organization '{old}' → '{name}'",
                     target_type="org", target_id=org.id)
    flash(f"Organization renamed to '{name}'.", "success")
    return redirect(url_for("main.admin_panel", section="orgs"))


@main_bp.route("/orgs/<int:org_id>/settings", methods=["POST"])
@login_required
@gm_required
def update_org_settings(org_id):
    """Per-org defaults inherited by teams (GM plan idea 2)."""
    org = Organization.query.get_or_404(org_id)
    timezone = (request.form.get("timezone") or "UTC").strip() or "UTC"
    sport = (request.form.get("sport") or "basketball").strip() or "basketball"
    convention = (request.form.get("season_convention") or "sept-june").strip()
    if convention not in ("sept-june", "calendar"):
        convention = "sept-june"
    org.timezone = timezone[:50]
    org.sport = sport[:50]
    org.season_convention = convention
    db.session.commit()
    log_admin_action(current_user, "org.settings",
                     f"updated defaults for '{org.name}' "
                     f"(tz={org.timezone}, sport={org.sport}, season={convention})",
                     target_type="org", target_id=org.id)
    flash(f"Defaults for '{org.name}' saved.", "success")
    return redirect(url_for("main.admin_panel", section="orgs"))


@main_bp.route("/teams/create", methods=["POST"])
@login_required
@gm_required
def create_team():
    """Create a new team inside an organization."""
    org_id = request.form.get("organization_id", type=int)
    name = (request.form.get("name") or "").strip()
    org = Organization.query.get(org_id) if org_id else None
    if org is None:
        flash("Valid organization is required.", "danger")
        return _safe_next("main.admin_panel", section="orgs")
    if not name:
        flash("Team name is required.", "danger")
        return _safe_next("main.admin_panel", section="orgs")
    slug = _slugify(name)
    if Team.query.filter_by(organization_id=org.id, slug=slug).first():
        flash(f"Team '{name}' already exists in {org.name}.", "danger")
        return _safe_next("main.admin_panel", section="orgs")
    team = Team(name=name, organization_id=org.id, slug=slug)
    db.session.add(team)
    db.session.commit()
    log_admin_action(current_user, "team.create",
                     f"created team '{name}' in {org.name}",
                     target_type="team", target_id=team.id,
                     organization_id=org.id)
    flash(f"Team '{name}' created in {org.name}.", "success")
    return _safe_next("main.admin_panel", section="orgs")


@main_bp.route("/teams/<int:team_id>/rename", methods=["POST"])
@login_required
@gm_required
def rename_team(team_id):
    """Rename a team (GM plan C-Phase 3)."""
    team = Team.query.get_or_404(team_id)
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Team name is required.", "danger")
        return _safe_next("main.admin_panel", section="orgs")
    slug = _slugify(name)
    dup = Team.query.filter(
        Team.organization_id == team.organization_id,
        Team.slug == slug, Team.id != team.id).first()
    if dup:
        flash(f"Team '{name}' already exists in this organization.", "danger")
        return _safe_next("main.admin_panel", section="orgs")
    old = team.name
    team.name = name
    team.slug = slug
    db.session.commit()
    log_admin_action(current_user, "team.rename",
                     f"renamed team '{old}' → '{name}'",
                     target_type="team", target_id=team.id,
                     organization_id=team.organization_id)
    flash(f"Team renamed to '{name}'.", "success")
    return _safe_next("main.admin_panel", section="orgs")


@main_bp.route("/teams/<int:team_id>/transfer", methods=["POST"])
@login_required
@gm_required
def transfer_team(team_id):
    """Move a team to another org, keeping games & seasons (C-Phase 3)."""
    team = Team.query.get_or_404(team_id)
    org_id = request.form.get("organization_id", type=int)
    org = Organization.query.get(org_id) if org_id else None
    if org is None:
        flash("Valid target organization is required.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    if org.id == team.organization_id:
        flash("Team is already in that organization.", "warning")
        return redirect(url_for("main.admin_panel", section="orgs"))
    if Team.query.filter_by(organization_id=org.id, slug=team.slug).first():
        flash(f"A team named '{team.name}' already exists there.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    old_org_id = team.organization_id
    team.organization_id = org.id
    db.session.commit()
    log_admin_action(current_user, "team.transfer",
                     f"transferred team '{team.name}' to {org.name}, "
                     f"kept games & seasons",
                     target_type="team", target_id=team.id,
                     organization_id=org.id)
    flash(f"Team '{team.name}' moved to {org.name}.", "success")
    return redirect(url_for("main.admin_panel", section="orgs"))


@main_bp.route("/teams/<int:team_id>/delete", methods=["POST"])
@login_required
@gm_required
def delete_team(team_id):
    """Delete a team with no games, players, seasons or assignments."""
    team = Team.query.get_or_404(team_id)
    blockers = {
        "games": Game.query.filter_by(team_id=team.id).count(),
        "players": Player.query.filter_by(team_id=team.id).count(),
        "seasons": Season.query.filter_by(team_id=team.id).count(),
        "assignments": TeamAssignment.query.filter_by(team_id=team.id).count(),
    }
    used = [k for k, v in blockers.items() if v]
    if used:
        flash(f"Cannot delete team '{team.name}': still has {', '.join(used)}.", "danger")
        return redirect(url_for("main.admin_panel", section="orgs"))
    # Drop the session reference if it pointed at the deleted team.
    if session.get("current_team_id") == team.id:
        session.pop("current_team_id", None)
        session.pop("current_team_name", None)
        session.pop("current_season_id", None)
    db.session.delete(team)
    db.session.commit()
    log_admin_action(current_user, "team.delete", f"deleted team '{team.name}'",
                     target_type="team", target_id=team_id,
                     organization_id=team.organization_id)
    flash(f"Team '{team.name}' deleted.", "success")
    return redirect(url_for("main.admin_panel", section="orgs"))


@main_bp.route("/season/switch")
@login_required
def switch_season():
    """Switch the session's season scope (id or ALL)."""
    raw = (request.args.get("season") or "ALL").strip()
    team_id = session.get("current_team_id")
    if raw == "ALL":
        session["current_season_id"] = "ALL"
    else:
        try:
            candidate = int(raw)
        except (TypeError, ValueError):
            candidate = None
        from core.services.season_service import get_season

        if candidate and get_season(candidate, team_id):
            session["current_season_id"] = candidate
        else:
            session["current_season_id"] = "ALL"
            flash("Unknown season.", "warning")
    next_url = request.args.get("next") or request.referrer or url_for("main.index")
    return redirect(next_url)
