import os
import statistics
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required
from sqlalchemy import func

from core.models import Game, PlayerStat, ShotEvent, db
from core.csv_processor import CSVProcessor
from core.parser import parse_game_pdf
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
)

main_bp = Blueprint("main", __name__)

VALID_GAME_TYPES = {"ALL", "Season", "Friendly", "Playoff"}
ALLOWED_EXTENSIONS = {"csv", "pdf"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_date_to_display(date_str: str) -> str:
    """Return DD/MM/YYYY."""
    if not date_str:
        return ""
    date_str = date_str.strip()
    date_str = date_str.replace("-", "/")
    parts = date_str.split("/")
    if len(parts) != 3:
        return ""
    day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    return f"{int(day):02d}/{int(month):02d}/{int(year):04d}"


def normalize_date_to_sort(date_str: str) -> str:
    """Return YYYY-MM-DD."""
    display = normalize_date_to_display(date_str)
    if not display:
        return ""
    day, month, year = display.split("/")
    return f"{year}-{month}-{day}"


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
    from datetime import datetime
    now_date = datetime.now().strftime("%Y-%m-%d")
    return render_template("live_game.html", existing_players=existing_players, now_date=now_date)


@main_bp.route("/live-game/save", methods=["POST"])
@login_required
def save_live_game():
    """Receive JSON data from live tracker and save to DB"""
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data received"}), 400

    try:
        # Create Game
        game = Game(
            date=normalize_date_to_display(data.get("date")),
            opponent=data.get("opponent"),
            team_score=int(data.get("team_score", 0)),
            opponent_score=int(data.get("opponent_score", 0)),
            result="W" if int(data.get("team_score", 0)) > int(data.get("opponent_score", 0)) else "L",
            game_type=data.get("game_type", "Season"),
            sort_date=data.get("date"), # Assuming front-end sends YYYY-MM-DD
            source="LIVE",
        )
        db.session.add(game)
        db.session.flush()

        # Create Player Stats
        for p_name, stats in data.get("player_stats", {}).items():
            if not p_name:
                continue
            
            # Calculate percentages
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
                # plus_minus will be calculated once we add event timeline logging
            )
            db.session.add(new_stat)

        # Create Shot Events (made shots only, from click-map)
        # NOTE: current frontend only logs location for made 2pt/3pt.
        for ev in data.get("shot_locations", []) or []:
            shooter = (ev.get("shooter") or "").strip()
            shot_type = (ev.get("type") or "").strip()   # 2pt / 3pt
            points = int(ev.get("points") or 0)

            # store the raw SVG coords (x,y) as floats; can be normalized later
            x = ev.get("x")
            y = ev.get("y")
            q = ev.get("quarter")

            shot = ShotEvent(
                game_id=game.id,
                player_name=shooter,
                shot_type=shot_type,
                result="made",
                points=points,
                x_loc=float(x) if x is not None else None,
                y_loc=float(y) if y is not None else None,
                quarter=int(q) if q is not None else None,
            )
            db.session.add(shot)

        db.session.commit()
        return jsonify({"success": True, "game_id": game.id})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Live game save error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@main_bp.route("/upload-game", methods=["GET", "POST"])
@login_required
def upload_game():
    """Upload a CSV or PDF file to add a game"""
    if request.method == "POST":
        import_type = request.form.get("import_type", "csv").lower().strip()
        if import_type not in {"csv", "pdf"}:
            import_type = "csv"

        upload_folder = current_app.config["UPLOAD_FOLDER"]
        os.makedirs(upload_folder, exist_ok=True)

        filepath = None

        try:
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
                    )
                    db.session.add(stat)

                db.session.commit()
                flash(f"Successfully imported game (CSV): {game.opponent} ({game.result})", "success")
                return redirect(url_for("main.game_detail", game_id=game.id))

            # --- PDF import ---
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
                )
                db.session.add(stat)

            db.session.commit()
            flash(f"Successfully imported game (PDF): {game.opponent} ({game.result})", "success")
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
