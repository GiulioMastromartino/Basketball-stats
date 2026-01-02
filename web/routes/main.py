import os
import statistics
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from sqlalchemy import func

from core.models import Game, PlayerStat, db
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

    return render_template("game_detail.html", game=game, stats=stats)


@main_bp.route("/game/<int:game_id>/delete", methods=["POST"])
@login_required
def delete_game(game_id):
    """Delete a game and all associated player stats."""
    game = Game.query.get_or_404(game_id)

    try:
        # Delete player stats first (avoid FK issues)
        PlayerStat.query.filter_by(game_id=game.id).delete()
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
        mean_ppg = statistics.mean(game_ppg