import os
import statistics
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from sqlalchemy import func

from core.models import Game, PlayerStat, db
from core.csv_processor import CSVProcessor
from core.utils import (
    FT_ATTEMPT_WEIGHT,
    THREE_POINT_WEIGHT,
    calculate_efficiency,
    calculate_efg_percent,
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

VALID_GAME_TYPES = {"ALL", "Season", "Friendly"}
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


@main_bp.route("/upload-game", methods=["GET", "POST"])
@login_required
def upload_game():
    """Upload a CSV file to add a game"""
    if request.method == "POST":
        # Check if file was uploaded
        if 'csv_file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(request.url)
        
        file = request.files['csv_file']
        
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(request.url)
        
        if not allowed_file(file.filename):
            flash('Only CSV files are allowed', 'danger')
            return redirect(request.url)
        
        try:
            # Secure filename and save temporarily
            filename = secure_filename(file.filename)
            upload_folder = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_folder, exist_ok=True)
            
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            
            # Parse filename to extract game info
            info = CSVProcessor.parse_filename(filename)
            if not info:
                flash(f'Invalid filename format. Expected: Opponent_TeamScore-OppScore_DD-MM-YYYY_[F/S/P].csv', 'danger')
                os.remove(filepath)
                return redirect(request.url)
            
            # Check for duplicates
            existing = Game.query.filter_by(
                sort_date=info["sort_date"],
                opponent=info["opponent"]
            ).first()
            
            if existing:
                flash(f'Game already exists: {existing.opponent} on {existing.date}', 'warning')
                os.remove(filepath)
                return redirect(url_for('main.index'))
            
            # Process CSV file
            game_data = CSVProcessor.process_game(filepath, info)
            if not game_data:
                flash('Failed to process CSV content. Check file format.', 'danger')
                os.remove(filepath)
                return redirect(request.url)
            
            # Create Game record
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
            
            # Create PlayerStat records
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
            
            # Clean up uploaded file
            os.remove(filepath)
            
            flash(f'Successfully imported game: {game.opponent} ({game.result})', 'success')
            return redirect(url_for('main.game_detail', game_id=game.id))
            
        except Exception as e:
            db.session.rollback()
            if os.path.exists(filepath):
                os.remove(filepath)
            flash(f'Error importing game: {str(e)}', 'danger')
            current_app.logger.error(f'Upload error: {e}', exc_info=True)
            return redirect(request.url)
    
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

    all_filtered_games = game_query.all()
    target_game_ids = [g.id for g in all_filtered_games]

    if not target_game_ids:
        flash(f"No games found for {player_name}", "warning")
        return redirect(url_for('main.players'))

    # Get player's game stats
    player_stats = (
        PlayerStat.query
        .filter(PlayerStat.player_name == player_name)
        .filter(PlayerStat.game_id.in_(target_game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .join(Game)
        .order_by(Game.sort_date.desc())
        .all()
    )

    if not player_stats:
        flash(f"No stats found for {player_name}", "warning")
        return redirect(url_for('main.players'))

    # Calculate aggregate stats
    gp = len(player_stats)
    total_minutes = sum(parse_minutes(s.minutes) for s in player_stats)
    
    totals = {
        'points': sum(s.points for s in player_stats),
        'reb': sum(s.reb for s in player_stats),
        'oreb': sum(s.oreb for s in player_stats),
        'dreb': sum(s.dreb for s in player_stats),
        'ast': sum(s.ast for s in player_stats),
        'stl': sum(s.stl for s in player_stats),
        'blk': sum(s.blk for s in player_stats),
        'tov': sum(s.tov for s in player_stats),
        'pf': sum(s.pf for s in player_stats),
        'fgm': sum(s.fgm for s in player_stats),
        'fga': sum(s.fga for s in player_stats),
        'tpm': sum(s.tpm for s in player_stats),
        'tpa': sum(s.tpa for s in player_stats),
        'ftm': sum(s.ftm for s in player_stats),
        'fta': sum(s.fta for s in player_stats),
    }

    # Calculate advanced metrics
    total_poss = sum(
        calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in player_stats
    )
    
    two_pt_stats = calculate_two_point_stats(
        totals['fgm'], totals['fga'], totals['tpm'], totals['tpa']
    )

    # Calculate consistency (coefficient of variation) for PPG
    game_ppgs = [s.points for s in player_stats]
    consistency_value = 0
    if len(game_ppgs) > 1 and statistics.mean(game_ppgs) > 0:
        std_dev = statistics.stdev(game_ppgs)
        mean_ppg = statistics.mean(game_ppgs)
        consistency_value = (std_dev / mean_ppg)  # As decimal, not percentage

    averages = {
        'mpg': total_minutes / gp,
        'ppg': totals['points'] / gp,
        'rpg': totals['reb'] / gp,
        'orebpg': totals['oreb'] / gp,
        'drebpg': totals['dreb'] / gp,
        'apg': totals['ast'] / gp,
        'spg': totals['stl'] / gp,
        'bpg': totals['blk'] / gp,
        'topg': totals['tov'] / gp,
        'pfpg': totals['pf'] / gp,
        'eff': calculate_efficiency(
            totals['points'], totals['reb'], totals['ast'], totals['stl'], 
            totals['blk'], totals['fgm'], totals['fga'], totals['ftm'], 
            totals['fta'], totals['tov']
        ) / gp,
        'ortg': calculate_ortg(totals['points'], total_poss),
        'ppp': calculate_ppp(totals['points'], total_poss),
        'usg_pct': (total_poss / gp),
        'fg_pct': (totals['fgm'] / totals['fga'] * 100) if totals['fga'] > 0 else 0,
        'two_pt_pct': two_pt_stats['two_pt_pct'],
        'tp_pct': (totals['tpm'] / totals['tpa'] * 100) if totals['tpa'] > 0 else 0,
        'ft_pct': (totals['ftm'] / totals['fta'] * 100) if totals['fta'] > 0 else 0,
        'ts_pct': calculate_ts_percent(totals['points'], totals['fga'], totals['fta']),
        'efg_pct': calculate_efg_percent(totals['fgm'], totals['tpm'], totals['fga']),
        'ast_tov': totals['ast'] / totals['tov'] if totals['tov'] > 0 else totals['ast'],
        'fta_pct': safe_percentage(totals['fta'], totals['fga']),
        'oreb_pct': safe_percentage(totals['oreb'], totals['reb']),
        'consistency': consistency_value,  # Added this field
    }

    # Career highs
    career_highs = {
        'points': max(s.points for s in player_stats),
        'reb': max(s.reb for s in player_stats),
        'ast': max(s.ast for s in player_stats),
        'stl': max(s.stl for s in player_stats),
        'blk': max(s.blk for s in player_stats),
    }

    # Consistency CV for display (as percentage)
    consistency_cv = consistency_value * 100

    # Process game logs with advanced metrics
    game_logs = []
    for stat in player_stats:
        game = stat.game
        poss = calculate_possessions(stat.fga, stat.fta, stat.oreb, stat.tov)
        
        game_logs.append({
            'game': game,
            'stat': stat,
            'ortg': calculate_ortg(stat.points, poss),
            'ppp': calculate_ppp(stat.points, poss),
            'eff': calculate_efficiency(
                stat.points, stat.reb, stat.ast, stat.stl, stat.blk,
                stat.fgm, stat.fga, stat.ftm, stat.fta, stat.tov
            ),
            'ts_pct': calculate_ts_percent(stat.points, stat.fga, stat.fta),
            'efg_pct': calculate_efg_percent(stat.fgm, stat.tpm, stat.fga),
            'ast_tov': stat.ast / stat.tov if stat.tov > 0 else stat.ast,
        })

    # Prepare chart data (last 10 games for trends)
    recent_games = game_logs[:10][::-1]  # Reverse for chronological order
    chart_data = {
        'labels': [g['game'].opponent[:10] for g in recent_games],
        'points': [g['stat'].points for g in recent_games],
        'rebounds': [g['stat'].reb for g in recent_games],
        'assists': [g['stat'].ast for g in recent_games],
        'efficiency': [g['eff'] for g in recent_games],
        'fg_pct': [(g['stat'].fgm / g['stat'].fga * 100) if g['stat'].fga > 0 else 0 for g in recent_games],
        'tp_pct': [(g['stat'].tpm / g['stat'].tpa * 100) if g['stat'].tpa > 0 else 0 for g in recent_games],
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
        two_pt_made=two_pt_stats['two_pt_made'],
        two_pt_att=two_pt_stats['two_pt_att'],
    )


@main_bp.route("/players")
@login_required
def players():
    """List of all players with Comprehensive Advanced Stats"""
    view = request.args.get("view", "cards")  # Default to card view
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

    all_filtered_games = game_query.all()

    if limit > 0:
        target_games = all_filtered_games[:limit]
    else:
        target_games = all_filtered_games

    target_game_ids = [g.id for g in target_games]

    if not target_game_ids:
        # Pass view parameter to template so links persist the current view preference if needed, 
        # though usually empty state handles its own display.
        template = "players_table.html" if view == "table" else "players.html"
        return render_template(
            template,
            stats=[],
            filters={
                "type": game_type,
                "limit": limit,
                "sort": sort_by,
                "order": order,
            },
        )

    stats_query = (
        db.session.query(
            PlayerStat.player_name,
            func.count(PlayerStat.id).label("games_played"),
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

        players_data.append(
            {
                "player_name": row.player_name,
                "games_played": gp,
                "mpg": total_minutes / gp if gp > 0 else 0,
                "ppg": row.total_points / gp if gp > 0 else 0,
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
                "ast_tov": row.total_ast / row.total_tov
                if row.total_tov > 0
                else row.total_ast,
                "fta_pct": safe_percentage(row.total_fta, row.total_fga),
                "oreb_pct": safe_percentage(row.total_oreb, row.total_reb),
                "consistency": consistency,
                # SHOOTING TOTALS
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
            {
                "name": opp_name,
                "games": len(games),
                "record": f"{wins}-{losses}",
                "avg_score": avg_score,
            }
        )

    return render_template("teams.html", teams=team_stats)


@main_bp.route("/teams/<opponent_name>")
@login_required
def opponent_games(opponent_name):
    """List games against a specific opponent"""
    games = (
        Game.query.filter_by(opponent=opponent_name)
        .order_by(Game.sort_date.desc())
        .all()
    )

    wins = sum(1 for g in games if g.result == "W")
    losses = len(games) - wins

    return render_template(
        "index.html",
        games=games,
        stats={"games": len(games), "players": 0, "wins": wins, "losses": losses},
    )