import statistics

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from core.models import Game, PlayerStat, db
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


@main_bp.route("/players")
@login_required
def players():
    """List of all players with Comprehensive Advanced Stats"""
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
                "two_pt_pct": two_pt_stats["two_pt_pct"] / 100,
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
            }
        )

    reverse = order == "desc"
    players_data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

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
