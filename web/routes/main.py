import os
import statistics
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required
from sqlalchemy import case, func

from core.models import Game, PlayerStat, ShotEvent, db, Play
from core.csv_processor import CSVProcessor
from core.parser import parse_game_pdf
from core.services import create_game_from_live_data
from core.play_analytics import get_play_stats
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
ALLOWED_EXTENSIONS = {"csv", "pdf"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
                        plus_minus=int(player.get("plus_minus", 0) or 0),
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
                    plus_minus=int(player.get("plus_minus", 0) or 0),
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


@main_bp.route("/game/<int:game_id>")
@login_required
def game_detail(game_id):
    """Detailed stats for a specific game with Advanced Metrics"""
    game = Game.query.get_or_404(game_id)
    stats = (
        PlayerStat.query.filter_by(game_id=game.id)
        .order_by(PlayerStat.points.desc())
        .all()
    )

    # Fetch shot events for this game if available
    shot_events = ShotEvent.query.filter_by(game_id=game.id).all()

    # --- Plays analysis dashboard (offense only) ---
    plays_data = get_play_stats(game.id, play_type="Offense")

    team_possessions = sum(
        calculate_possessions(p.fga, p.fta, p.oreb, p.tov) for p in stats
    )

    for p in stats:
        p.min_decimal = parse_minutes(p.minutes)
        p.possessions = calculate_possessions(p.fga, p.fta, p.oreb, p.tov)
        p.ortg = calculate_ortg(p.points, p.possessions)
        p.ppp = calculate_ppp(p.points, p.possessions)
        p.usg_pct = safe_percentage(p.possessions, team_possessions)
        p.ast_tov_ratio = (p.ast / p.tov) if p.tov > 0 else p.ast
        p.eff = calculate_efficiency(
            p.points, p.reb, p.ast, p.stl, p.blk, p.fgm, p.fga, p.ftm, p.fta, p.tov
        )
        p.ts_pct = calculate_ts_percent(p.points, p.fga, p.fta)
        p.efg_pct = calculate_efg_percent(p.fgm, p.tpm, p.fga)

        # Calculate Game Score
        p.game_score = calculate_game_score(
            p.points,
            p.fgm,
            p.fga,
            p.ftm,
            p.fta,
            p.oreb,
            p.dreb,
            p.stl,
            p.ast,
            p.blk,
            p.pf,
            p.tov,
        )

        if p.min_decimal > 0:
            p.pts_100 = calculate_per_100_minutes(p.points, p.min_decimal)
            p.reb_100 = calculate_per_100_minutes(p.reb, p.min_decimal)
            p.ast_100 = calculate_per_100_minutes(p.ast, p.min_decimal)
            p.tov_100 = calculate_per_100_minutes(p.tov, p.min_decimal)
            p.stl_100 = calculate_per_100_minutes(p.stl, p.min_decimal)
            p.blk_100 = calculate_per_100_minutes(p.blk, p.min_decimal)
            p.pf_100 = calculate_per_100_minutes(p.pf, p.min_decimal)
        else:
            p.pts_100 = p.reb_100 = p.ast_100 = p.tov_100 = p.stl_100 = p.blk_100 = (
                p.pf_100
            ) = 0

        two_pt_stats = calculate_two_point_stats(p.fgm, p.fga, p.tpm, p.tpa)
        p.two_pt_att = two_pt_stats["two_pt_att"]
        p.two_pt_made = two_pt_stats["two_pt_made"]
        p.two_pt_pct = two_pt_stats["two_pt_pct"]

        p.fta_pct = safe_percentage(p.fta, p.fga)
        p.oreb_pct = safe_percentage(p.oreb, p.reb)
        p.foul_trouble = p.pf >= 3

    # --- Team totals + advanced ---
    team_stats = {
        "points": sum(p.points for p in stats),
        "fgm": sum(p.fgm for p in stats),
        "fga": sum(p.fga for p in stats),
        "tpm": sum(p.tpm for p in stats),
        "tpa": sum(p.tpa for p in stats),
        "ftm": sum(p.ftm for p in stats),
        "fta": sum(p.fta for p in stats),
        "oreb": sum(p.oreb for p in stats),
        "dreb": sum(p.dreb for p in stats),
        "reb": sum(p.reb for p in stats),
        "ast": sum(p.ast for p in stats),
        "tov": sum(p.tov for p in stats),
        "stl": sum(p.stl for p in stats),
        "blk": sum(p.blk for p in stats),
        "pf": sum(p.pf for p in stats),
    }

    team_poss = calculate_possessions(team_stats["fga"], team_stats["fta"], team_stats["oreb"], team_stats["tov"])
    if team_poss <= 0:
        # fallback to summed player possessions if the team formula yields 0
        team_poss = team_possessions

    efg = calculate_efg_percent(team_stats["fgm"], team_stats["tpm"], team_stats["fga"])
    ortg = calculate_ortg(game.team_score, team_poss)
    drtg = calculate_ortg(game.opponent_score, team_poss)

    advanced = {
        "possessions": round(team_poss, 1),
        "efg_pct": round(efg, 1),
        "ts_pct": round(calculate_ts_percent(team_stats["points"], team_stats["fga"], team_stats["fta"]), 1),
        "tov_pct": round(safe_percentage(team_stats["tov"], team_poss), 1),
        "ft_rate": round(safe_percentage(team_stats["fta"], team_stats["fga"]), 1),
        "oreb_pct": round(safe_percentage(team_stats["oreb"], team_stats["reb"]), 1),
        "ortg": round(ortg, 0),
        "drtg": round(drtg, 0),
    }

    return render_template(
        "game_detail.html",
        game=game,
        stats=stats,
        shot_events=shot_events,
        plays_data=plays_data,
        team_stats=team_stats,
        advanced=advanced,
    )


@main_bp.route("/game/<int:game_id>/delete", methods=["POST"])
@login_required
def delete_game(game_id):
    """Delete a game and all associated player stats."""
    game = Game.query.get_or_404(game_id)

    try:
        # Delete player stats first (avoid FK issues)
        PlayerStat.query.filter_by(game_id=game.id).delete()
        # Delete shot events
        ShotEvent.query.filter_by(game_id=game.id).delete()
        # Delete game events (future proof)
        from core.models import GameEvent
        GameEvent.query.filter_by(game_id=game.id).delete()

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
def player_detail(player_name):
    """Detailed player profile with comprehensive stats and charts"""
    game_type = request.args.get("game_type", "ALL")
    if game_type not in VALID_GAME_TYPES:
        game_type = "ALL"

    # Get all games for this player
    game_query = Game.query.order_by(Game.sort_date.desc())
    if game_type == "Season":
        game_query = game_query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        game_query = game_query.filter(Game.game_type == "Friendly")
    elif game_type == "Playoff":
        game_query = game_query.filter(Game.game_type == "Playoff")

    all_filtered_games = game_query.all()
    target_game_ids = [g.id for g in all_filtered_games]

    if not target_game_ids:
        flash(f"No games found for {player_name}", "warning")
        return redirect(url_for("main.players"))

    # Get player's game stats
    player_stats = (
        PlayerStat.query.filter(PlayerStat.player_name == player_name)
        .filter(PlayerStat.game_id.in_(target_game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .join(Game)
        .order_by(Game.sort_date.desc())
        .all()
    )

    if not player_stats:
        flash(f"No stats found for {player_name}", "warning")
        return redirect(url_for("main.players"))

    # Get shot events for this player in these games
    shot_events = (
        ShotEvent.query.filter(ShotEvent.player_name == player_name)
        .filter(ShotEvent.game_id.in_(target_game_ids))
        .all()
    )

    # Calculate aggregate stats
    gp = len(player_stats)
    total_minutes = sum(parse_minutes(s.minutes) for s in player_stats)

    totals = {
        "points": sum(s.points for s in player_stats),
        "reb": sum(s.reb for s in player_stats),
        "oreb": sum(s.oreb for s in player_stats),
        "dreb": sum(s.dreb for s in player_stats),
        "ast": sum(s.ast for s in player_stats),
        "stl": sum(s.stl for s in player_stats),
        "blk": sum(s.blk for s in player_stats),
        "tov": sum(s.tov for s in player_stats),
        "pf": sum(s.pf for s in player_stats),
        "fgm": sum(s.fgm for s in player_stats),
        "fga": sum(s.fga for s in player_stats),
        "tpm": sum(s.tpm for s in player_stats),
        "tpa": sum(s.tpa for s in player_stats),
        "ftm": sum(s.ftm for s in player_stats),
        "fta": sum(s.fta for s in player_stats),
        "plus_minus": sum((s.plus_minus or 0) for s in player_stats),
    }

    # Calculate advanced metrics
    total_poss = sum(
        calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in player_stats
    )

    two_pt_stats = calculate_two_point_stats(
        totals["fgm"], totals["fga"], totals["tpm"], totals["tpa"]
    )

    # Calculate consistency (coefficient of variation) for PPG
    game_ppgs = [s.points for s in player_stats]
    consistency_value = 0
    if len(game_ppgs) > 1 and statistics.mean(game_ppgs) > 0:
        std_dev = statistics.stdev(game_ppgs)
        mean_ppg = statistics.mean(game_ppgs)
        consistency_value = std_dev / mean_ppg

    averages = {
        "mpg": total_minutes / gp,
        "ppg": totals["points"] / gp,
        "rpg": totals["reb"] / gp,
        "orebpg": totals["oreb"] / gp,
        "drebpg": totals["dreb"] / gp,
        "apg": totals["ast"] / gp,
        "spg": totals["stl"] / gp,
        "bpg": totals["blk"] / gp,
        "topg": totals["tov"] / gp,
        "pfpg": totals["pf"] / gp,
        "pm": totals["plus_minus"] / gp if gp > 0 else 0,
        "eff": calculate_efficiency(
            totals["points"],
            totals["reb"],
            totals["ast"],
            totals["stl"],
            totals["blk"],
            totals["fgm"],
            totals["fga"],
            totals["ftm"],
            totals["fta"],
            totals["tov"],
        )
        / gp,
        "ortg": calculate_ortg(totals["points"], total_poss),
        "ppp": calculate_ppp(totals["points"], total_poss),
        "usg_pct": total_poss / gp,
        "fg_pct": (totals["fgm"] / totals["fga"] * 100) if totals["fga"] > 0 else 0,
        "two_pt_pct": two_pt_stats["two_pt_pct"],
        "tp_pct": (totals["tpm"] / totals["tpa"] * 100) if totals["tpa"] > 0 else 0,
        "ft_pct": (totals["ftm"] / totals["fta"] * 100) if totals["fta"] > 0 else 0,
        "ts_pct": calculate_ts_percent(totals["points"], totals["fga"], totals["fta"]),
        "efg_pct": calculate_efg_percent(totals["fgm"], totals["tpm"], totals["fga"]),
        "ast_tov": totals["ast"] / totals["tov"] if totals["tov"] > 0 else totals["ast"],
        "fta_pct": safe_percentage(totals["fta"], totals["fga"]),
        "oreb_pct": safe_percentage(totals["oreb"], totals["reb"]),
        "consistency": consistency_value,
    }

    career_highs = {
        "points": max(s.points for s in player_stats),
        "reb": max(s.reb for s in player_stats),
        "ast": max(s.ast for s in player_stats),
        "stl": max(s.stl for s in player_stats),
        "blk": max(s.blk for s in player_stats),
    }

    consistency_cv = consistency_value * 100

    game_logs = []
    for stat in player_stats:
        game = stat.game
        poss = calculate_possessions(stat.fga, stat.fta, stat.oreb, stat.tov)

        game_logs.append(
            {
                "game": game,
                "stat": stat,
                "ortg": calculate_ortg(stat.points, poss),
                "ppp": calculate_ppp(stat.points, poss),
                "eff": calculate_efficiency(
                    stat.points,
                    stat.reb,
                    stat.ast,
                    stat.stl,
                    stat.blk,
                    stat.fgm,
                    stat.fga,
                    stat.ftm,
                    stat.fta,
                    stat.tov,
                ),
                "ts_pct": calculate_ts_percent(stat.points, stat.fga, stat.fta),
                "efg_pct": calculate_efg_percent(stat.fgm, stat.tpm, stat.fga),
                "ast_tov": stat.ast / stat.tov if stat.tov > 0 else stat.ast,
            }
        )

    recent_games = game_logs[:10][::-1]
    chart_data = {
        "labels": [g["game"].opponent[:10] for g in recent_games],
        "points": [g["stat"].points for g in recent_games],
        "rebounds": [g["stat"].reb for g in recent_games],
        "assists": [g["stat"].ast for g in recent_games],
        "efficiency": [g["eff"] for g in recent_games],
        "fg_pct": [
            (g["stat"].fgm / g["stat"].fga * 100) if g["stat"].fga > 0 else 0
            for g in recent_games
        ],
        "tp_pct": [
            (g["stat"].tpm / g["stat"].tpa * 100) if g["stat"].tpa > 0 else 0
            for g in recent_games
        ],
    }

    return render_template(
        "player_detail.html",
        player_name=player_name,
        games_played=gp,
        totals=totals,
        averages=averages,
        career_highs=career_highs,
        consistency_cv=consistency_cv,
        game_logs=game_logs,
        chart_data=chart_data,
        game_type=game_type,
        two_pt_made=two_pt_stats["two_pt_made"],
        two_pt_att=two_pt_stats["two_pt_att"],
        shot_events=shot_events,
    )


@main_bp.route("/players")
@login_required
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

    game_query = Game.query.order_by(Game.sort_date.desc())
    if game_type == "Season":
        game_query = game_query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        game_query = game_query.filter(Game.game_type == "Friendly")
    elif game_type == "Playoff":
        game_query = game_query.filter(Game.game_type == "Playoff")

    all_filtered_games = game_query.all()

    if limit > 0:
        target_games = all_filtered_games[:limit]
    else:
        target_games = all_filtered_games

    target_game_ids = [g.id for g in target_games]

    if not target_game_ids:
        template = "players_table.html" if view == "table" else "players.html"
        return render_template(
            template,
            stats=[],
            filters={"type": game_type, "limit": limit, "sort": sort_by, "order": order},
        )

    stats_query = (
        db.session.query(
            PlayerStat.player_name,
            func.count(PlayerStat.id).label("games_played"),
            func.sum(PlayerStat.id).label("total_id"),
            func.sum(PlayerStat.points).label("total_points"),
            func.sum(PlayerStat.reb).label("total_reb"),
            func.sum(PlayerStat.oreb).label("total_oreb"),
            func.sum(PlayerStat.dreb).label("total_dreb"),
            func.sum(PlayerStat.ast).label("total_ast"),
            func.sum(PlayerStat.stl).label("total_stl"),
            func.sum(PlayerStat.blk).label("total_blk"),
            func.sum(PlayerStat.tov).label("total_tov"),
            func.sum(PlayerStat.pf).label("total_pf"),
            func.sum(PlayerStat.fgm).label("total_fgm"),
            func.sum(PlayerStat.fga).label("total_fga"),
            func.sum(PlayerStat.tpm).label("total_tpm"),
            func.sum(PlayerStat.tpa).label("total_tpa"),
            func.sum(PlayerStat.ftm).label("total_ftm"),
            func.sum(PlayerStat.fta).label("total_fta"),
            func.sum(PlayerStat.plus_minus).label("total_plus_minus"),
        )
        .filter(PlayerStat.game_id.in_(target_game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .group_by(PlayerStat.player_name)
        .all()
    )

    players_data = []

    for row in stats_query:
        gp = row.games_played

        player_stats = (
            PlayerStat.query.filter(PlayerStat.player_name == row.player_name)
            .filter(PlayerStat.game_id.in_(target_game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .all()
        )

        total_minutes = sum(parse_minutes(s.minutes) for s in player_stats)
        game_ppgs = [s.points for s in player_stats]

        total_poss = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in player_stats
        )

        ortg = calculate_ortg(row.total_points, total_poss)
        ppp = calculate_ppp(row.total_points, total_poss)

        eff = calculate_efficiency(
            row.total_points,
            row.total_reb,
            row.total_ast,
            row.total_stl,
            row.total_blk,
            row.total_fgm,
            row.total_fga,
            row.total_ftm,
            row.total_fta,
            row.total_tov,
        )

        ts_pct = calculate_ts_percent(row.total_points, row.total_fga, row.total_fta)
        efg_pct = calculate_efg_percent(row.total_fgm, row.total_tpm, row.total_fga)

        two_pt_stats = calculate_two_point_stats(
            row.total_fgm, row.total_fga, row.total_tpm, row.total_tpa
        )

        consistency = 0
        if len(game_ppgs) > 1:
            std_dev = statistics.stdev(game_ppgs)
            mean_ppg = statistics.mean(game_ppgs)
            consistency = (std_dev / mean_ppg) if mean_ppg > 0 else 0

        total_pm = row.total_plus_minus or 0

        players_data.append(
            {
                "player_name": row.player_name,
                "games_played": gp,
                "mpg": total_minutes / gp if gp > 0 else 0,
                "ppg": row.total_points / gp if gp > 0 else 0,
                "plus_minus_avg": (total_pm / gp) if gp > 0 else 0,
                "plus_minus_total": total_pm,
                "rpg": row.total_reb / gp if gp > 0 else 0,
                "orebpg": row.total_oreb / gp if gp > 0 else 0,
                "drebpg": row.total_dreb / gp if gp > 0 else 0,
                "apg": row.total_ast / gp if gp > 0 else 0,
                "spg": row.total_stl / gp if gp > 0 else 0,
                "bpg": row.total_blk / gp if gp > 0 else 0,
                "topg": row.total_tov / gp if gp > 0 else 0,
                "pfpg": row.total_pf / gp if gp > 0 else 0,
                "eff": eff / gp if gp > 0 else 0,
                "ortg": ortg,
                "ppp": ppp,
                "usg_pct": (total_poss / gp) if gp > 0 else 0,
                "fg_pct": row.total_fgm / row.total_fga if row.total_fga > 0 else 0,
                "two_pt_pct": two_pt_stats["two_pt_pct"],
                "tp_pct": row.total_tpm / row.total_tpa if row.total_tpa > 0 else 0,
                "ft_pct": row.total_ftm / row.total_fta if row.total_fta > 0 else 0,
                "ts_pct": ts_pct,
                "efg_pct": efg_pct,
                "ast_tov": row.total_ast / row.total_tov if row.total_tov > 0 else row.total_ast,
                "fta_pct": safe_percentage(row.total_fta, row.total_fga),
                "oreb_pct": safe_percentage(row.total_oreb, row.total_reb),
                "consistency": consistency,
                "fgm": row.total_fgm,
                "fga": row.total_fga,
                "two_pt_made": two_pt_stats["two_pt_made"],
                "two_pt_att": two_pt_stats["two_pt_att"],
                "tpm": row.total_tpm,
                "tpa": row.total_tpa,
                "ftm": row.total_ftm,
                "fta": row.total_fta,
            }
        )

    reverse = order == "desc"
    players_data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

    template = "players_table.html" if view == "table" else "players.html"

    return render_template(
        template,
        stats=players_data,
        filters={"type": game_type, "limit": limit, "sort": sort_by, "order": order},
    )


@main_bp.route("/games-list")
@login_required
def games():
    """Summary of performance against opponents (formerly teams)"""
    results = db.session.query(Game.opponent).distinct().all()

    team_stats = []
    for r in results:
        opp_name = r[0]
        games = Game.query.filter_by(opponent=opp_name).all()
        wins = sum(1 for g in games if g.result == "W")
        losses = len(games) - wins

        if len(games) > 0:
            avg_team_score = sum(g.team_score for g in games) / len(games)
            avg_opp_score = sum(g.opponent_score for g in games) / len(games)
            avg_score = f"{int(avg_team_score)}-{int(avg_opp_score)}"
        else:
            avg_score = "0-0"

        team_stats.append(
            {"name": opp_name, "games": len(games), "record": f"{wins}-{losses}", "avg_score": avg_score}
        )

    return render_template("teams.html", teams=team_stats)


@main_bp.route("/teams/<opponent_name>")
@login_required
def opponent_games(opponent_name):
    """List games against a specific opponent"""
    games = Game.query.filter_by(opponent=opponent_name).order_by(Game.sort_date.desc()).all()

    wins = sum(1 for g in games if g.result == "W")
    losses = len(games) - wins

    return render_template(
        "index.html",
        games=games,
        stats={"games": len(games), "players": 0, "wins": wins, "losses": losses},
    )
