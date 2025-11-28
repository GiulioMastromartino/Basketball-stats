from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from core.models import Game, PlayerStat, db

main_bp = Blueprint("main", __name__)


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

    # Add advanced metrics dynamically to object (temporary attributes)
    for p in stats:
        # EFF = (PTS + REB + AST + STL + BLK) - ((FGA - FGM) + (FTA - FTM) + TOV)
        p.eff = (p.points + p.reb + p.ast + p.stl + p.blk) - (
            (p.fga - p.fgm) + (p.fta - p.ftm) + p.tov
        )

        # TS% = PTS / (2 * (FGA + 0.44 * FTA))
        denom_ts = 2 * (p.fga + 0.44 * p.fta)
        p.ts_pct = (p.points / denom_ts * 100) if denom_ts > 0 else 0

        # eFG% = (FGM + 0.5 * 3PM) / FGA
        p.efg_pct = ((p.fgm + 0.5 * p.tpm) / p.fga * 100) if p.fga > 0 else 0

    return render_template("game_detail.html", game=game, stats=stats)


@main_bp.route("/players")
@login_required
def players():
    """List of all players with Comprehensive Advanced Stats & Filtering & Sorting"""

    # --- PARAMS ---
    game_type = request.args.get("game_type", "ALL")  # ALL, Season, Friendly
    limit = int(request.args.get("limit", 0))  # 0=All, 5=Last 5, etc.
    sort_by = request.args.get("sort", "ppg")  # Default sort by PPG
    order = request.args.get("order", "desc")  # Default order descending

    players_data = []
    all_names = db.session.query(PlayerStat.player_name).distinct().all()

    # Pre-fetch game IDs that match the filter to optimize loop
    game_query = Game.query.order_by(Game.sort_date.desc())

    if game_type == "Season":
        game_query = game_query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        game_query = game_query.filter(Game.game_type == "Friendly")

    all_filtered_games = game_query.all()

    # Apply Limit (e.g., Last 5 games of this type)
    if limit > 0:
        target_games = all_filtered_games[:limit]
    else:
        target_games = all_filtered_games

    target_game_ids = [g.id for g in target_games]

    # If filters result in no games, return empty list immediately
    if not target_game_ids:
        return render_template(
            "players.html",
            stats=[],
            filters={
                "type": game_type,
                "limit": limit,
                "sort": sort_by,
                "order": order,
            },
        )

    for name_tuple in all_names:
        name = name_tuple[0]

        # Filter stats by the target game IDs
        stats = (
            PlayerStat.query.filter_by(player_name=name)
            .filter(PlayerStat.game_id.in_(target_game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .all()
        )

        if not stats:
            continue

        gp = len(stats)

        # Calculate Totals (Safety for None values)
        totals = {
            "pts": sum((s.points or 0) for s in stats),
            "reb": sum((s.reb or 0) for s in stats),
            "ast": sum((s.ast or 0) for s in stats),
            "stl": sum((s.stl or 0) for s in stats),
            "blk": sum((s.blk or 0) for s in stats),
            "tov": sum((s.tov or 0) for s in stats),
            "fgm": sum((s.fgm or 0) for s in stats),
            "fga": sum((s.fga or 0) for s in stats),
            "tpm": sum((s.tpm or 0) for s in stats),
            "tpa": sum((s.tpa or 0) for s in stats),
            "ftm": sum((s.ftm or 0) for s in stats),
            "fta": sum((s.fta or 0) for s in stats),
        }

        # Efficiency
        eff = (
            totals["pts"]
            + totals["reb"]
            + totals["ast"]
            + totals["stl"]
            + totals["blk"]
        ) - (
            (totals["fga"] - totals["fgm"])
            + (totals["fta"] - totals["ftm"])
            + totals["tov"]
        )

        # TS%
        denom_ts = 2 * (totals["fga"] + 0.44 * totals["fta"])
        ts_pct = (totals["pts"] / denom_ts * 100) if denom_ts > 0 else 0

        # eFG%
        efg_pct = (
            ((totals["fgm"] + 0.5 * totals["tpm"]) / totals["fga"] * 100)
            if totals["fga"] > 0
            else 0
        )

        players_data.append(
            {
                "player_name": name,
                "games_played": gp,
                "ppg": totals["pts"] / gp,
                "rpg": totals["reb"] / gp,
                "apg": totals["ast"] / gp,
                "spg": totals["stl"] / gp,
                "bpg": totals["blk"] / gp,
                "topg": totals["tov"] / gp,
                "eff": eff / gp,
                "fg_pct": totals["fgm"] / totals["fga"] if totals["fga"] > 0 else 0,
                "tp_pct": totals["tpm"] / totals["tpa"] if totals["tpa"] > 0 else 0,
                "ft_pct": totals["ftm"] / totals["fta"] if totals["fta"] > 0 else 0,
                "ts_pct": ts_pct,
                "efg_pct": efg_pct,
                "ast_tov": totals["ast"] / totals["tov"]
                if totals["tov"] > 0
                else totals["ast"],
            }
        )

    # --- DYNAMIC SORTING ---
    reverse = order == "desc"
    # Use .get() to avoid crashes if key doesn't exist
    players_data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

    # Pass current filters back to template to keep dropdowns selected
    return render_template(
        "players.html",
        stats=players_data,
        filters={"type": game_type, "limit": limit, "sort": sort_by, "order": order},
    )


@main_bp.route("/teams")
@login_required
def teams():
    """Summary of performance against opponents"""
    results = db.session.query(Game.opponent).distinct().all()

    team_stats = []
    for r in results:
        opp_name = r[0]
        games = Game.query.filter_by(opponent=opp_name).all()
        wins = sum(1 for g in games if g.result == "W")
        losses = len(games) - wins

        if len(games) > 0:
            avg_score = f"{int(sum(g.team_score for g in games) / len(games))}-{int(sum(g.opponent_score for g in games) / len(games))}"
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
