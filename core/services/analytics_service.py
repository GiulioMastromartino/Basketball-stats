import statistics
from collections import defaultdict
from itertools import groupby
from sqlalchemy import func, desc
from types import SimpleNamespace
from core.models import PlayerStat, db, Game, ShotEvent, LineupSegment, GameEvent
from core.utils import (
    calculate_possessions,
    calculate_efficiency,
    calculate_ortg,
    calculate_ppp,
    calculate_ts_percent,
    calculate_efg_percent,
    calculate_two_point_stats,
    calculate_game_score,
    parse_minutes,
    format_total_minutes,
    get_player_stats_averages,
    normalize_per_100_possessions,
    safe_percentage,
    calculate_per_100_minutes,
    calculate_pace,
    normalize_shot_events,
)

from core.charts import (
    generate_player_charts,
    generate_shot_chart,
    generate_shooting_trend_base64,
    generate_team_scoring_trend,
    generate_team_shot_chart,
    generate_quarter_scoring_base64,
)


class AnalyticsService:
    @staticmethod
    def supports_plus_minus(game):
        """Return True when a game source is expected to persist +/- values."""
        return bool(
            game and getattr(game, "source", None) in {"LIVE", "IMPORT", "IMPORT_JSON"}
        )

    @staticmethod
    def calculate_game_stats(stats):
        """Enrich player stats with calculated metrics"""
        for s in stats:
            poss = calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
            s.eff = calculate_efficiency(
                s.points, s.reb, s.ast, s.stl, s.blk, s.fgm, s.fga, s.ftm, s.fta, s.tov
            )
            s.ortg = calculate_ortg(s.points, poss) if poss > 0 else 0
            s.ppp = calculate_ppp(s.points, poss) if poss > 0 else 0
            s.ts_pct = calculate_ts_percent(s.points, s.fga, s.fta)
            s.efg_pct = calculate_efg_percent(s.fgm, s.tpm, s.fga)
            s.ast_tov_ratio = (s.ast / s.tov) if s.tov > 0 else s.ast
            s.poss_per_40 = (
                (poss / (parse_minutes(s.minutes) / 40))
                if parse_minutes(s.minutes) > 0
                else 0
            )

            # Game Score
            s.game_score = calculate_game_score(
                s.points,
                s.fgm,
                s.fga,
                s.ftm,
                s.fta,
                s.oreb,
                s.dreb,
                s.stl,
                s.ast,
                s.blk,
                s.pf,
                s.tov,
            )

            two_pt = calculate_two_point_stats(s.fgm, s.fga, s.tpm, s.tpa)
            s.two_pt_made = two_pt["two_pt_made"]
            s.two_pt_att = two_pt["two_pt_att"]
            s.two_pt_pct = two_pt["two_pt_pct"]
        return stats

    @staticmethod
    def calculate_team_averages(game_ids, db_session=None):
        """Calculate team-wide averages across all players"""
        session = db_session or db.session

        team_stats = (
            session.query(
                func.avg(PlayerStat.points).label("avg_ppg"),
                func.avg(PlayerStat.reb).label("avg_rpg"),
                func.avg(PlayerStat.ast).label("avg_apg"),
                func.sum(PlayerStat.points).label("total_pts"),
                func.sum(PlayerStat.fga).label("total_fga"),
                func.sum(PlayerStat.fta).label("total_fta"),
                func.sum(PlayerStat.fgm).label("total_fgm"),
                func.sum(PlayerStat.tpm).label("total_tpm"),
                func.sum(PlayerStat.ast).label("total_ast"),
                func.sum(PlayerStat.tov).label("total_tov"),
                func.count(PlayerStat.id).label("player_games"),
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .filter(PlayerStat.minutes.isnot(None))
            .filter(PlayerStat.minutes != "")
            .first()
        )

        if not team_stats or not team_stats.player_games:
            return {
                "ppg": 0,
                "rpg": 0,
                "apg": 0,
                "ts_pct": 0,
                "efg_pct": 0,
                "ast_tov": 0,
                "ortg": 0,
            }

        ts_pct = calculate_ts_percent(
            team_stats.total_pts, team_stats.total_fga, team_stats.total_fta
        )
        efg_pct = calculate_efg_percent(
            team_stats.total_fgm, team_stats.total_tpm, team_stats.total_fga
        )
        ast_tov = (
            (team_stats.total_ast / team_stats.total_tov)
            if team_stats.total_tov > 0
            else team_stats.total_ast
        )

        # Calculate total possessions (Optimized: single query)
        all_stats = (
            session.query(
                PlayerStat.fga, PlayerStat.fta, PlayerStat.oreb, PlayerStat.tov
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .all()
        )
        total_possessions = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in all_stats
        )
        ortg = calculate_ortg(team_stats.total_pts, total_possessions)

        return {
            "ppg": round(team_stats.avg_ppg or 0, 1),
            "rpg": round(team_stats.avg_rpg or 0, 1),
            "apg": round(team_stats.avg_apg or 0, 1),
            "ts_pct": round(ts_pct, 1),
            "efg_pct": round(efg_pct, 1),
            "ast_tov": round(ast_tov, 2),
            "ortg": round(ortg, 1),
        }

    @staticmethod
    def calculate_team_rankings(player_name, game_ids, report_data, db_session=None):
        """Calculate player's rank and percentile within the team"""
        session = db_session or db.session

        # 1. Get aggregated stats
        all_players_stats = (
            session.query(
                PlayerStat.player_name,
                func.avg(PlayerStat.points).label("ppg"),
                func.avg(PlayerStat.reb).label("rpg"),
                func.avg(PlayerStat.ast).label("apg"),
                func.sum(PlayerStat.points).label("total_pts"),
                func.sum(PlayerStat.fga).label("total_fga"),
                func.sum(PlayerStat.fta).label("total_fta"),
                func.sum(PlayerStat.fgm).label("total_fgm"),
                func.sum(PlayerStat.tpm).label("total_tpm"),
                func.sum(PlayerStat.ast).label("total_ast"),
                func.sum(PlayerStat.tov).label("total_tov"),
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .group_by(PlayerStat.player_name)
            .all()
        )

        if not all_players_stats:
            return {}

        # 2. Get raw stats for ORTG calculation (N+1 Optimization)
        # Fetch all required fields to calculate possessions for ALL players in ONE query
        raw_stats = (
            session.query(
                PlayerStat.player_name,
                PlayerStat.fga,
                PlayerStat.fta,
                PlayerStat.oreb,
                PlayerStat.tov,
            )
            .filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .order_by(PlayerStat.player_name)
            .all()
        )

        # Group by player name
        player_possessions = defaultdict(float)
        for name, group in groupby(raw_stats, key=lambda x: x[0]):
            poss = sum(
                calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in group
            )
            player_possessions[name] = poss

        # 3. Build Metrics List
        players_data = []
        current_player_values = {}

        for p in all_players_stats:
            ts_pct = calculate_ts_percent(p.total_pts, p.total_fga, p.total_fta)
            efg_pct = calculate_efg_percent(p.total_fgm, p.total_tpm, p.total_fga)
            ast_tov = (p.total_ast / p.total_tov) if p.total_tov > 0 else p.total_ast

            poss = player_possessions.get(p.player_name, 0)
            ortg = calculate_ortg(p.total_pts, poss)

            metrics = {
                "name": p.player_name,
                "ppg": round(p.ppg, 1),
                "rpg": round(p.rpg, 1),
                "apg": round(p.apg, 1),
                "ts_pct": round(ts_pct, 1),
                "efg_pct": round(efg_pct, 1),
                "ast_tov": round(ast_tov, 2),
                "ortg": round(ortg, 1),
            }
            players_data.append(metrics)

            if p.player_name == player_name:
                current_player_values = metrics

        # 4. Calculate Rankings
        rankings = {}
        num_players = len(players_data)

        for metric in ["ppg", "rpg", "apg", "ts_pct", "efg_pct", "ast_tov", "ortg"]:
            sorted_players = sorted(players_data, key=lambda x: x[metric], reverse=True)

            rank = next(
                (
                    i
                    for i, p in enumerate(sorted_players, 1)
                    if p["name"] == player_name
                ),
                None,
            )
            percentile = ((num_players - rank + 1) / num_players * 100) if rank else 0

            rankings[metric] = {
                "rank": rank,
                "total": num_players,
                "percentile": round(percentile, 0),
                "is_leader": (rank == 1) if rank else False,
                "leader_name": sorted_players[0]["name"] if sorted_players else "",
                "distribution": sorted([p[metric] for p in players_data]),
                "player_value": current_player_values.get(metric, 0),
            }

        return rankings

    @staticmethod
    def calculate_player_metrics(stats, game_map, games_played):
        """Calculate comprehensive player metrics"""
        avg_stats = get_player_stats_averages(stats)

        pm_game_stats = [
            s
            for s in stats
            if AnalyticsService.supports_plus_minus(game_map.get(s.game_id))
        ]
        if pm_game_stats:
            avg_plus_minus = sum((s.plus_minus or 0) for s in pm_game_stats) / len(
                pm_game_stats
            )
        else:
            avg_plus_minus = None

        # Per 100
        total_poss = 0
        for s in stats:
            total_poss += calculate_possessions(s.fga, s.fta, s.oreb, s.tov)

        per_100_stats = {
            "points": normalize_per_100_possessions(
                avg_stats["points"] * games_played, total_poss
            )
            if total_poss
            else 0,
            "reb": normalize_per_100_possessions(
                avg_stats["reb"] * games_played, total_poss
            )
            if total_poss
            else 0,
            "ast": normalize_per_100_possessions(
                avg_stats["ast"] * games_played, total_poss
            )
            if total_poss
            else 0,
            "stl": normalize_per_100_possessions(
                avg_stats["stl"] * games_played, total_poss
            )
            if total_poss
            else 0,
            "blk": normalize_per_100_possessions(
                avg_stats["blk"] * games_played, total_poss
            )
            if total_poss
            else 0,
        }

        # Shooting
        two_pt_made = avg_stats["fgm"] - avg_stats["tpm"]
        two_pt_att = avg_stats["fga"] - avg_stats["tpa"]
        shooting_data = {
            "fg": {
                "made": avg_stats["fgm"],
                "att": avg_stats["fga"],
                "pct": avg_stats["fg_percent"],
            },
            "three_pt": {
                "made": avg_stats["tpm"],
                "att": avg_stats["tpa"],
                "pct": avg_stats["tp_percent"],
            },
            "ft": {
                "made": avg_stats["ftm"],
                "att": avg_stats["fta"],
                "pct": avg_stats["ft_percent"],
            },
            "two_pt": {
                "made": round(two_pt_made, 1),
                "att": round(two_pt_att, 1),
                "pct": safe_percentage(two_pt_made, two_pt_att),
            },
        }

        # Advanced
        total_pts = avg_stats["points"] * games_played
        total_fga = avg_stats["fga"] * games_played
        total_fta = avg_stats["fta"] * games_played
        total_fgm = avg_stats["fgm"] * games_played
        total_tpm = avg_stats["tpm"] * games_played

        advanced_stats = {
            "ts_pct": calculate_ts_percent(total_pts, total_fga, total_fta),
            "efg_pct": calculate_efg_percent(total_fgm, total_tpm, total_fga),
            "ortg": calculate_ortg(total_pts, total_poss),
            "ppp": calculate_ppp(total_pts, total_poss) if total_poss else 0,
            "ast_tov": avg_stats["ast"] / avg_stats["tov"]
            if avg_stats["tov"] > 0
            else avg_stats["ast"],
            "avg_plus_minus": round(avg_plus_minus, 1)
            if avg_plus_minus is not None
            else None,
            "has_live_plus_minus": len(pm_game_stats) > 0,
            "oreb_pct": safe_percentage(avg_stats["oreb"], avg_stats["reb"])
            if avg_stats["reb"]
            else 0,
            "dreb_pct": safe_percentage(avg_stats["dreb"], avg_stats["reb"])
            if avg_stats["reb"]
            else 0,
        }

        # Game Logs
        game_logs = []
        for s in stats:
            game = game_map.get(s.game_id)
            if not game:
                continue

            poss = calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
            ortg = calculate_ortg(s.points, poss)
            gmsc = (
                s.points
                + 0.4 * s.fgm
                - 0.7 * s.fga
                - 0.4 * (s.fta - s.ftm)
                + 0.7 * s.oreb
                + 0.3 * s.dreb
                + s.stl
                + 0.7 * s.ast
                + 0.7 * s.blk
                - 0.4 * s.pf
                - s.tov
            )

            game_logs.append(
                {
                    "date": game.date,
                    "opponent": game.opponent,
                    "result": game.result,
                    "minutes": s.minutes,
                    "pts": s.points,
                    "reb": s.reb,
                    "oreb": s.oreb,
                    "dreb": s.dreb,
                    "ast": s.ast,
                    "stl": s.stl,
                    "blk": s.blk,
                    "tov": s.tov,
                    "pf": s.pf,
                    "plus_minus": s.plus_minus
                    if AnalyticsService.supports_plus_minus(game)
                    else None,
                    "is_live": game.source == "LIVE",
                    "fgm": s.fgm,
                    "fga": s.fga,
                    "fg_pct": round(s.fg_percent * 100, 1),
                    "tpm": s.tpm,
                    "tpa": s.tpa,
                    "tp_percent": round(s.tp_percent * 100, 1),
                    "ftm": s.ftm,
                    "fta": s.fta,
                    "ft_percent": round(s.ft_percent * 100, 1),
                    "ortg": round(ortg, 1),
                    "gmsc": round(gmsc, 1),
                }
            )

        return {
            "avg_stats": avg_stats,
            "per_100": per_100_stats,
            "shooting": shooting_data,
            "advanced": advanced_stats,
            "games_played": games_played,
            "game_logs": game_logs,
            "live_games_count": len(pm_game_stats),
        }

    @staticmethod
    def calculate_enhanced_team_metrics(games, game_ids, db_session=None):
        """Calculate comprehensive team-level metrics"""
        total_games = len(games)
        wins = sum(1 for g in games if g.result == "W")
        losses = total_games - wins
        win_pct = (wins / total_games * 100) if total_games > 0 else 0

        total_team = sum(g.team_score for g in games)
        total_opp = sum(g.opponent_score for g in games)

        return {
            "total_games": total_games,
            "wins": wins,
            "losses": losses,
            "win_pct": round(win_pct, 1),
            "ppg": round(total_team / total_games if total_games else 0, 1),
            "opp_ppg": round(total_opp / total_games if total_games else 0, 1),
            "games": games,
            "top_contributors": AnalyticsService.get_top_contributors(
                game_ids, db_session
            ),
            "opponent_stats": AnalyticsService.analyze_opponents(games),
            "team_shooting": AnalyticsService.calculate_team_shooting(
                game_ids, db_session
            ),
            "plus_minus_leaders": AnalyticsService.calculate_plus_minus_leaders(
                games, db_session
            ),
        }

    @staticmethod
    def get_top_contributors(game_ids, db_session=None):
        """Find top contributors across all games"""
        session = db_session or db.session

        def get_leaders(field):
            return (
                session.query(
                    PlayerStat.player_name,
                    func.sum(field).label("total"),
                    func.avg(field).label("avg"),
                    func.count(PlayerStat.id).label("games"),
                )
                .filter(PlayerStat.game_id.in_(game_ids))
                .filter(PlayerStat.minutes != "00:00")
                .filter(PlayerStat.minutes != "0")
                .group_by(PlayerStat.player_name)
                .order_by(desc("total"))
                .limit(5)
                .all()
            )

        pts = get_leaders(PlayerStat.points)
        reb = get_leaders(PlayerStat.reb)
        ast = get_leaders(PlayerStat.ast)

        return {
            "points": [
                {
                    "player": p.player_name,
                    "total": int(p.total),
                    "avg": round(p.avg, 1),
                    "games": p.games,
                }
                for p in pts
            ],
            "rebounds": [
                {
                    "player": p.player_name,
                    "total": int(p.total),
                    "avg": round(p.avg, 1),
                    "games": p.games,
                }
                for p in reb
            ],
            "assists": [
                {
                    "player": p.player_name,
                    "total": int(p.total),
                    "avg": round(p.avg, 1),
                    "games": p.games,
                }
                for p in ast
            ],
        }

    @staticmethod
    def analyze_opponents(games):
        """Analyze performance against different opponents"""
        stats = defaultdict(
            lambda: {"wins": 0, "losses": 0, "pf": 0, "pa": 0, "games": 0}
        )
        for g in games:
            opp = g.opponent
            stats[opp]["games"] += 1
            stats[opp]["pf"] += g.team_score
            stats[opp]["pa"] += g.opponent_score
            if g.result == "W":
                stats[opp]["wins"] += 1
            else:
                stats[opp]["losses"] += 1

        results = []
        for opp, s in stats.items():
            s["diff"] = s["pf"] - s["pa"]
            s["opponent"] = opp
            results.append(s)
        return sorted(results, key=lambda x: x["diff"], reverse=True)

    @staticmethod
    def calculate_team_shooting(game_ids, db_session=None):
        """Calculate team-wide shooting statistics"""
        session = db_session or db.session
        stats = session.query(PlayerStat).filter(PlayerStat.game_id.in_(game_ids)).all()

        if not stats:
            return None

        num_games = len(set(s.game_id for s in stats))

        t_fgm = sum(s.fgm for s in stats)
        t_fga = sum(s.fga for s in stats)
        t_tpm = sum(s.tpm for s in stats)
        t_tpa = sum(s.tpa for s in stats)
        t_ftm = sum(s.ftm for s in stats)
        t_fta = sum(s.fta for s in stats)
        t_pts = sum(s.points for s in stats)

        t_2pm = t_fgm - t_tpm
        t_2pa = t_fga - t_tpa

        return {
            "fgm": round(t_fgm / num_games, 1),
            "fga": round(t_fga / num_games, 1),
            "fg_pct": safe_percentage(t_fgm, t_fga),
            "two_pt_made": round(t_2pm / num_games, 1),
            "two_pt_att": round(t_2pa / num_games, 1),
            "two_pt_pct": safe_percentage(t_2pm, t_2pa),
            "tpm": round(t_tpm / num_games, 1),
            "tpa": round(t_tpa / num_games, 1),
            "three_pt_pct": safe_percentage(t_tpm, t_tpa),
            "ftm": round(t_ftm / num_games, 1),
            "fta": round(t_fta / num_games, 1),
            "ft_pct": safe_percentage(t_ftm, t_fta),
            "ts_pct": calculate_ts_percent(t_pts, t_fga, t_fta),
            "efg_pct": calculate_efg_percent(t_fgm, t_tpm, t_fga),
        }

    @staticmethod
    def calculate_plus_minus_leaders(games, db_session=None):
        """Calculate plus/minus leaders for sources that persist +/- values."""
        session = db_session or db.session
        live_ids = [g.id for g in games if AnalyticsService.supports_plus_minus(g)]
        if not live_ids:
            return []

        data = (
            session.query(
                PlayerStat.player_name,
                func.count(PlayerStat.id).label("games"),
                func.sum(PlayerStat.plus_minus).label("total_pm"),
                func.avg(PlayerStat.plus_minus).label("avg_pm"),
            )
            .filter(PlayerStat.game_id.in_(live_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .group_by(PlayerStat.player_name)
            .order_by(desc("avg_pm"))
            .limit(10)
            .all()
        )

        return [
            {
                "player": p.player_name,
                "games": p.games,
                "total_pm": int(p.total_pm or 0),
                "avg_pm": round(p.avg_pm or 0, 1),
            }
            for p in data
        ]

    @staticmethod
    def build_player_detail(player_name: str, game_type: str = "ALL") -> dict:
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
            raise ValueError("No games found")

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
            raise ValueError("No stats found")

        shot_events = (
            ShotEvent.query.filter(ShotEvent.player_name == player_name)
            .filter(ShotEvent.game_id.in_(target_game_ids))
            .all()
        )
        shot_events = normalize_shot_events(shot_events)

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
        total_poss = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in player_stats
        )
        two_pt_stats = calculate_two_point_stats(
            totals["fgm"], totals["fga"], totals["tpm"], totals["tpa"]
        )
        game_ppgs = [s.points for s in player_stats]
        consistency_value = 0
        if len(game_ppgs) > 1 and statistics.mean(game_ppgs) > 0:
            consistency_value = statistics.stdev(game_ppgs) / statistics.mean(game_ppgs)

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
            "poss_per_40": (total_poss / (total_minutes / 40))
            if total_minutes > 0
            else 0,
            "usg_pct": total_poss / gp,
            "fg_pct": safe_percentage(totals["fgm"], totals["fga"]),
            "two_pt_pct": two_pt_stats["two_pt_pct"],
            "tp_pct": safe_percentage(totals["tpm"], totals["tpa"]),
            "ft_pct": safe_percentage(totals["ftm"], totals["fta"]),
            "ts_pct": calculate_ts_percent(
                totals["points"], totals["fga"], totals["fta"]
            ),
            "efg_pct": calculate_efg_percent(
                totals["fgm"], totals["tpm"], totals["fga"]
            ),
            "ast_tov": totals["ast"] / totals["tov"]
            if totals["tov"] > 0
            else totals["ast"],
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
        game_logs = []
        for stat in player_stats:
            poss = calculate_possessions(stat.fga, stat.fta, stat.oreb, stat.tov)
            game_logs.append(
                {
                    "game": stat.game,
                    "stat": stat,
                    "ortg": calculate_ortg(stat.points, poss),
                    "ppp": calculate_ppp(stat.points, poss),
                    "poss_per_40": (poss / (parse_minutes(stat.minutes) / 40))
                    if parse_minutes(stat.minutes) > 0
                    else 0,
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
                safe_percentage(g["stat"].fgm, g["stat"].fga) for g in recent_games
            ],
            "tp_pct": [
                safe_percentage(g["stat"].tpm, g["stat"].tpa) for g in recent_games
            ],
        }
        game_map = {g.id: g for g in all_filtered_games}
        # Fetch the Player model instance to get the ID
        from core.models import Player
        player = Player.query.filter_by(name=player_name).first()
        player_id = player.id if player else None

        return {
            "player_name": player_name,
            "player_id": player_id,
            "games_played": gp,
            "totals": totals,
            "averages": averages,
            "career_highs": career_highs,
            "consistency_cv": consistency_value * 100,
            "game_logs": game_logs,
            "chart_data": chart_data,
            "game_type": game_type,
            "two_pt_made": two_pt_stats["two_pt_made"],
            "two_pt_att": two_pt_stats["two_pt_att"],
            "shot_events": shot_events,
            "pdf_chart_scoring": chart_images.get("chart_scoring", ""),
            "pdf_chart_shooting": generate_shooting_trend_base64(
                chart_data, f"{player_name} - Shooting Efficiency"
            ),
            "pdf_shot_chart": generate_shot_chart(player_name, target_game_ids),
        }

    @staticmethod
    def build_player_game_detail(
        player_name: str, game_type: str = "ALL", game_id: int = None
    ) -> dict:
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
            raise ValueError("No games found")

        # Single-game mode
        if game_id is not None:
            if game_id not in target_game_ids:
                raise ValueError("Game not in filtered set")
            target_game_ids = [game_id]
            game = Game.query.get(game_id)
            if not game:
                raise ValueError("Game not found")
            is_single_game = True
        else:
            game = None
            is_single_game = False

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
            raise ValueError("No stats found")

        shot_events = (
            ShotEvent.query.filter(ShotEvent.player_name == player_name)
            .filter(ShotEvent.game_id.in_(target_game_ids))
            .all()
        )
        shot_events = normalize_shot_events(shot_events)

        gp = len(player_stats)
        if is_single_game:
            gp = 1  # Force 1 for display
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
        total_poss = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in player_stats
        )
        two_pt_stats = calculate_two_point_stats(
            totals["fgm"], totals["fga"], totals["tpm"], totals["tpa"]
        )

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
            "poss_per_40": (total_poss / (total_minutes / 40))
            if total_minutes > 0
            else 0,
            "usg_pct": total_poss / gp,
            "fg_pct": safe_percentage(totals["fgm"], totals["fga"]),
            "two_pt_pct": two_pt_stats["two_pt_pct"],
            "tp_pct": safe_percentage(totals["tpm"], totals["tpa"]),
            "ft_pct": safe_percentage(totals["ftm"], totals["fta"]),
            "ts_pct": calculate_ts_percent(
                totals["points"], totals["fga"], totals["fta"]
            ),
            "efg_pct": calculate_efg_percent(
                totals["fgm"], totals["tpm"], totals["fga"]
            ),
            "ast_tov": totals["ast"] / totals["tov"]
            if totals["tov"] > 0
            else totals["ast"],
            "fta_pct": safe_percentage(totals["fta"], totals["fga"]),
            "oreb_pct": safe_percentage(totals["oreb"], totals["reb"]),
            "consistency": 0,
        }

        # Compute quarterly stats
        quarterly_stats = {
            "Q1": {
                "pts": 0,
                "fgm": 0,
                "fga": 0,
                "tpm": 0,
                "tpa": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "tov": 0,
                "pf": 0,
            },
            "Q2": {
                "pts": 0,
                "fgm": 0,
                "fga": 0,
                "tpm": 0,
                "tpa": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "tov": 0,
                "pf": 0,
            },
            "Q3": {
                "pts": 0,
                "fgm": 0,
                "fga": 0,
                "tpm": 0,
                "tpa": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "tov": 0,
                "pf": 0,
            },
            "Q4": {
                "pts": 0,
                "fgm": 0,
                "fga": 0,
                "tpm": 0,
                "tpa": 0,
                "ftm": 0,
                "fta": 0,
                "oreb": 0,
                "dreb": 0,
                "ast": 0,
                "stl": 0,
                "blk": 0,
                "tov": 0,
                "pf": 0,
            },
        }

        # ShotEvent contributions
        player_shots = ShotEvent.query.filter(
            ShotEvent.player_name == player_name,
            ShotEvent.game_id.in_(target_game_ids),
            ShotEvent.quarter.isnot(None),
            ShotEvent.quarter.between(1, 4),
        ).all()

        for shot in player_shots:
            qkey = f"Q{shot.quarter}"
            if qkey not in quarterly_stats:
                continue
            qs = quarterly_stats[qkey]
            qs["fga"] += 1
            if shot.result == "made":
                qs["fgm"] += 1
                qs["pts"] += shot.points
                if shot.shot_type == "2pt":
                    qs["tpm"] += 0
                elif shot.shot_type == "3pt":
                    qs["tpm"] += 1
                    qs["tpa"] += 1
                else:
                    qs["ftm"] += 1
                    qs["fta"] += 1
            else:
                if shot.shot_type == "3pt":
                    qs["tpa"] += 1
                elif shot.shot_type == "ft":
                    qs["fta"] += 1

        # GameEvent contributions (non-shot events)
        player_events = GameEvent.query.filter(
            GameEvent.player_name == player_name,
            GameEvent.game_id.in_(target_game_ids),
            GameEvent.quarter.isnot(None),
            GameEvent.quarter.between(1, 4),
        ).all()

        for event in player_events:
            qkey = f"Q{event.quarter}"
            if qkey not in quarterly_stats:
                continue
            qs = quarterly_stats[qkey]
            etype = event.event_type
            if etype in ("AST",):
                qs["ast"] += 1
            elif etype in ("STL", "BLK"):
                if etype == "STL":
                    qs["stl"] += 1
                else:
                    qs["blk"] += 1
            elif etype == "TURNOVER":
                qs["tov"] += 1
            elif etype in ("OREB", "DREB"):
                if etype == "OREB":
                    qs["oreb"] += 1
                else:
                    qs["dreb"] += 1
            elif etype == "FOUL":
                qs["pf"] += 1

        # Calculate per-game averages for quarterly stats
        quarter_chart_data = {
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "points": [],
            "fg_pct": [],
            "tp_pct": [],
        }
        for qkey in ["Q1", "Q2", "Q3", "Q4"]:
            qs = quarterly_stats[qkey]
            q_pts_avg = qs["pts"] / gp if gp > 0 else 0
            quarter_chart_data["points"].append(round(q_pts_avg, 1))
            quarter_chart_data["fg_pct"].append(safe_percentage(qs["fgm"], qs["fga"]))
            quarter_chart_data["tp_pct"].append(safe_percentage(qs["tpm"], qs["tpa"]))

        # Generate PDF charts
        pdf_chart_scoring = generate_quarter_scoring_base64(
            quarter_chart_data, f"{player_name} - Quarter Scoring"
        )
        pdf_chart_shooting = generate_shooting_trend_base64(
            quarter_chart_data, f"{player_name} - Quarter Shooting"
        )
        pdf_shot_chart = generate_shot_chart(player_name, target_game_ids)

        # Game logs
        game_logs = []
        game_map = {g.id: g for g in all_filtered_games}
        for stat in player_stats:
            poss = calculate_possessions(stat.fga, stat.fta, stat.oreb, stat.tov)
            game_logs.append(
                {
                    "game": stat.game,
                    "stat": stat,
                    "ortg": calculate_ortg(stat.points, poss),
                    "ppp": calculate_ppp(stat.points, poss),
                    "poss_per_40": (poss / (parse_minutes(stat.minutes) / 40))
                    if parse_minutes(stat.minutes) > 0
                    else 0,
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
                }
            )

        # Consistency
        game_ppgs = [s.points for s in player_stats]
        consistency_value = 0
        if is_single_game:
            consistency_value = 0
        else:
            if len(game_ppgs) > 1 and statistics.mean(game_ppgs) > 0:
                consistency_value = statistics.stdev(game_ppgs) / statistics.mean(
                    game_ppgs
                )
        averages["consistency"] = consistency_value

        # Career highs (True season/all-time bests)
        # We query the database for true maximums across all games (optionally filtered by game_type)
        career_highs_query = (
            db.session.query(
                func.max(PlayerStat.points).label("points"),
                func.max(PlayerStat.reb).label("reb"),
                func.max(PlayerStat.ast).label("ast"),
                func.max(PlayerStat.stl).label("stl"),
                func.max(PlayerStat.blk).label("blk"),
            )
            .filter(PlayerStat.player_name == player_name)
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .join(Game)
        )
        
        if game_type == "Season":
            career_highs_query = career_highs_query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            career_highs_query = career_highs_query.filter(Game.game_type == "Friendly")
        elif game_type == "Playoff":
            career_highs_query = career_highs_query.filter(Game.game_type == "Playoff")
            
        highs_result = career_highs_query.first()
        
        career_highs = {
            "points": highs_result.points or 0,
            "reb": highs_result.reb or 0,
            "ast": highs_result.ast or 0,
            "stl": highs_result.stl or 0,
            "blk": highs_result.blk or 0,
        }

        # Chart data for last 10 games
        chart_data = {
            "labels": [],
            "points": [],
            "rebounds": [],
            "assists": [],
            "efficiency": [],
            "fg_pct": [],
            "tp_pct": [],
        }

        return {
            "player_name": player_name,
            "games_played": gp,
            "totals": totals,
            "averages": averages,
            "career_highs": career_highs,
            "consistency_cv": consistency_value * 100,
            "game_logs": game_logs,
            "chart_data": chart_data,
            "game_type": game_type,
            "two_pt_made": two_pt_stats["two_pt_made"],
            "two_pt_att": two_pt_stats["two_pt_att"],
            "shot_events": shot_events,
            "quarterly_stats": quarterly_stats,
            "quarter_chart_data": quarter_chart_data,
            "pdf_chart_scoring": pdf_chart_scoring,
            "pdf_chart_shooting": pdf_chart_shooting,
            "pdf_shot_chart": pdf_shot_chart,
            "is_single_game": is_single_game,
            "game": game,
        }

    @staticmethod
    def build_team_detail_context(game_type: str, excluded_player: str = None) -> dict:
        game_query = Game.query.order_by(Game.sort_date.desc())
        if game_type == "Season":
            game_query = game_query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            game_query = game_query.filter(Game.game_type == "Friendly")
        elif game_type == "Playoff":
            game_query = game_query.filter(Game.game_type == "Playoff")

        games = game_query.all()
        game_ids = [g.id for g in games]
        if not game_ids:
            raise ValueError("No team games found")

        stats_query = (
            PlayerStat.query.filter(PlayerStat.game_id.in_(game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
        )
        if excluded_player:
            stats_query = stats_query.filter(PlayerStat.player_name != excluded_player)
        team_stats = stats_query.all()
        shot_query = ShotEvent.query.filter(ShotEvent.game_id.in_(game_ids))
        if excluded_player:
            shot_query = shot_query.filter(ShotEvent.player_name != excluded_player)
        shot_events = shot_query.all()
        shot_events = normalize_shot_events(shot_events)

        games_played = len(games)
        total_point_diff = sum(
            (game.team_score or 0) - (game.opponent_score or 0) for game in games
        )
        total_minutes = sum(parse_minutes(s.minutes) for s in team_stats)
        totals = {
            "points": sum((s.points or 0) for s in team_stats),
            "reb": sum((s.reb or 0) for s in team_stats),
            "oreb": sum((s.oreb or 0) for s in team_stats),
            "dreb": sum((s.dreb or 0) for s in team_stats),
            "ast": sum((s.ast or 0) for s in team_stats),
            "stl": sum((s.stl or 0) for s in team_stats),
            "blk": sum((s.blk or 0) for s in team_stats),
            "tov": sum((s.tov or 0) for s in team_stats),
            "pf": sum((s.pf or 0) for s in team_stats),
            "fgm": sum((s.fgm or 0) for s in team_stats),
            "fga": sum((s.fga or 0) for s in team_stats),
            "tpm": sum((s.tpm or 0) for s in team_stats),
            "tpa": sum((s.tpa or 0) for s in team_stats),
            "ftm": sum((s.ftm or 0) for s in team_stats),
            "fta": sum((s.fta or 0) for s in team_stats),
            "plus_minus": total_point_diff,
        }
        total_poss = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in team_stats
        )
        two_pt_stats = calculate_two_point_stats(
            totals["fgm"], totals["fga"], totals["tpm"], totals["tpa"]
        )
        game_logs = []
        for game in games:
            game_player_stats = [s for s in team_stats if s.game_id == game.id]
            if not game_player_stats:
                continue
            game_minutes = sum(parse_minutes(s.minutes) for s in game_player_stats)
            poss = sum(
                calculate_possessions(s.fga, s.fta, s.oreb, s.tov)
                for s in game_player_stats
            )
            aggregate_stat = SimpleNamespace(
                minutes=format_total_minutes(game_minutes),
                points=sum((s.points or 0) for s in game_player_stats),
                reb=sum((s.reb or 0) for s in game_player_stats),
                oreb=sum((s.oreb or 0) for s in game_player_stats),
                dreb=sum((s.dreb or 0) for s in game_player_stats),
                ast=sum((s.ast or 0) for s in game_player_stats),
                stl=sum((s.stl or 0) for s in game_player_stats),
                blk=sum((s.blk or 0) for s in game_player_stats),
                tov=sum((s.tov or 0) for s in game_player_stats),
                pf=sum((s.pf or 0) for s in game_player_stats),
                fgm=sum((s.fgm or 0) for s in game_player_stats),
                fga=sum((s.fga or 0) for s in game_player_stats),
                tpm=sum((s.tpm or 0) for s in game_player_stats),
                tpa=sum((s.tpa or 0) for s in game_player_stats),
                ftm=sum((s.ftm or 0) for s in game_player_stats),
                fta=sum((s.fta or 0) for s in game_player_stats),
                plus_minus=(game.team_score or 0) - (game.opponent_score or 0),
            )
            game_logs.append(
                {
                    "game": game,
                    "stat": aggregate_stat,
                    "ortg": calculate_ortg(aggregate_stat.points, poss),
                    "ppp": calculate_ppp(aggregate_stat.points, poss),
                    "poss_per_40": (poss / (game_minutes / 40))
                    if game_minutes > 0
                    else 0,
                    "eff": calculate_efficiency(
                        aggregate_stat.points,
                        aggregate_stat.reb,
                        aggregate_stat.ast,
                        aggregate_stat.stl,
                        aggregate_stat.blk,
                        aggregate_stat.fgm,
                        aggregate_stat.fga,
                        aggregate_stat.ftm,
                        aggregate_stat.fta,
                        aggregate_stat.tov,
                    ),
                }
            )

        game_ppgs = [item["stat"].points for item in game_logs]
        consistency_value = 0
        if len(game_ppgs) > 1 and statistics.mean(game_ppgs) > 0:
            consistency_value = statistics.stdev(game_ppgs) / statistics.mean(game_ppgs)
        fg_pct_val = safe_percentage(totals["fgm"], totals["fga"])
        tp_pct_val = safe_percentage(totals["tpm"], totals["tpa"])
        averages = {
            "mpg": total_minutes / games_played if games_played > 0 else 0,
            "ppg": totals["points"] / games_played if games_played > 0 else 0,
            "rpg": totals["reb"] / games_played if games_played > 0 else 0,
            "orebpg": totals["oreb"] / games_played if games_played > 0 else 0,
            "drebpg": totals["dreb"] / games_played if games_played > 0 else 0,
            "apg": totals["ast"] / games_played if games_played > 0 else 0,
            "spg": totals["stl"] / games_played if games_played > 0 else 0,
            "bpg": totals["blk"] / games_played if games_played > 0 else 0,
            "topg": totals["tov"] / games_played if games_played > 0 else 0,
            "pfpg": totals["pf"] / games_played if games_played > 0 else 0,
            "pm": total_point_diff / games_played if games_played > 0 else 0,
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
            / games_played
            if games_played > 0
            else 0,
            "ortg": calculate_ortg(totals["points"], total_poss),
            "ppp": calculate_ppp(totals["points"], total_poss),
            "poss_per_40": (total_poss / (total_minutes / 40))
            if total_minutes > 0
            else 0,
            "usg_pct": total_poss / games_played if games_played > 0 else 0,
            "fg_pct": fg_pct_val,
            "two_pt_pct": two_pt_stats["two_pt_pct"],
            "tp_pct": tp_pct_val,
            "ft_pct": safe_percentage(totals["ftm"], totals["fta"]),
            "ts_pct": calculate_ts_percent(
                totals["points"], totals["fga"], totals["fta"]
            ),
            "efg_pct": calculate_efg_percent(
                totals["fgm"], totals["tpm"], totals["fga"]
            ),
            "ast_tov": totals["ast"] / totals["tov"]
            if totals["tov"] > 0
            else totals["ast"],
            "fta_pct": safe_percentage(totals["fta"], totals["fga"]),
            "oreb_pct": safe_percentage(totals["oreb"], totals["reb"]),
            "consistency": consistency_value,
        }
        career_highs = {
            "points": max((item["stat"].points for item in game_logs), default=0),
            "reb": max((item["stat"].reb for item in game_logs), default=0),
            "ast": max((item["stat"].ast for item in game_logs), default=0),
            "stl": max((item["stat"].stl for item in game_logs), default=0),
            "blk": max((item["stat"].blk for item in game_logs), default=0),
        }
        recent_games = game_logs[:10][::-1]
        chart_data = {
            "labels": [g["game"].opponent[:10] for g in recent_games],
            "points": [g["stat"].points for g in recent_games],
            "rebounds": [g["stat"].reb for g in recent_games],
            "assists": [g["stat"].ast for g in recent_games],
            "efficiency": [g["eff"] for g in recent_games],
            "fg_pct": [
                safe_percentage(g["stat"].fgm, g["stat"].fga) for g in recent_games
            ],
            "tp_pct": [
                safe_percentage(g["stat"].tpm, g["stat"].tpa) for g in recent_games
            ],
        }
        team_name = "Team Total"
        if excluded_player:
            team_name = f"Team Total (without {excluded_player})"
        return {
            "player_name": team_name,
            "games_played": games_played,
            "totals": totals,
            "averages": averages,
            "career_highs": career_highs,
            "consistency_cv": consistency_value * 100,
            "game_logs": game_logs,
            "chart_data": chart_data,
            "game_type": game_type,
            "two_pt_made": two_pt_stats["two_pt_made"],
            "two_pt_att": two_pt_stats["two_pt_att"],
            "shot_events": shot_events,
            "pdf_chart_scoring": generate_team_scoring_trend(games),
            "pdf_chart_shooting": generate_shooting_trend_base64(
                chart_data, "Team Shooting Efficiency"
            ),
            "pdf_shot_chart": generate_team_shot_chart(game_ids),
        }

    @staticmethod
    def sum_team_stat_rows(stat_rows):
        totals = {
            "points": 0,
            "fgm": 0,
            "fga": 0,
            "tpm": 0,
            "tpa": 0,
            "ftm": 0,
            "fta": 0,
            "oreb": 0,
            "dreb": 0,
            "reb": 0,
            "ast": 0,
            "tov": 0,
            "stl": 0,
            "blk": 0,
            "pf": 0,
            "reb_conceded": 0,
        }
        for stat in stat_rows:
            for key in totals:
                totals[key] += getattr(stat, key, 0) or 0
        totals["fg_pct"] = safe_percentage(totals["fgm"], totals["fga"])
        totals["tp_pct"] = safe_percentage(totals["tpm"], totals["tpa"])
        totals["ft_pct"] = safe_percentage(totals["ftm"], totals["fta"])
        totals["two_pt_made"] = max(totals["fgm"] - totals["tpm"], 0)
        totals["two_pt_att"] = max(totals["fga"] - totals["tpa"], 0)
        totals["two_pt_pct"] = safe_percentage(
            totals["two_pt_made"], totals["two_pt_att"]
        )
        return totals

    @staticmethod
    def get_stat_leader(stat_rows, field):
        if not stat_rows:
            return None
        leader = max(
            stat_rows, key=lambda s: (getattr(s, field, 0) or 0, s.player_name or "")
        )
        value = getattr(leader, field, 0) or 0
        if value <= 0:
            return None
        return {"player": leader.player_name, "value": value}

    @staticmethod
    def get_top_players_by_gamescore(stat_rows, limit=10):
        ranked_players = []
        for stat in stat_rows:
            possessions = calculate_possessions(
                stat.fga or 0,
                stat.fta or 0,
                stat.oreb or 0,
                stat.tov or 0,
            )
            game_score = calculate_game_score(
                stat.points or 0,
                stat.fgm or 0,
                stat.fga or 0,
                stat.ftm or 0,
                stat.fta or 0,
                stat.oreb or 0,
                stat.dreb or 0,
                stat.stl or 0,
                stat.ast or 0,
                stat.blk or 0,
                stat.pf or 0,
                stat.tov or 0,
            )
            ts_pct = calculate_ts_percent(
                stat.points or 0, stat.fga or 0, stat.fta or 0
            )
            ortg = calculate_ortg(stat.points or 0, possessions)
            ranked_players.append(
                {
                    "player": stat.player_name,
                    "game_score": round(game_score, 1),
                    "points": stat.points or 0,
                    "reb": stat.reb or 0,
                    "ast": stat.ast or 0,
                    "minutes": stat.minutes or "00:00",
                    "fgm": stat.fgm or 0,
                    "fga": stat.fga or 0,
                    "tpm": stat.tpm or 0,
                    "tpa": stat.tpa or 0,
                    "ftm": stat.ftm or 0,
                    "fta": stat.fta or 0,
                    "oreb": stat.oreb or 0,
                    "dreb": stat.dreb or 0,
                    "stl": stat.stl or 0,
                    "blk": stat.blk or 0,
                    "tov": stat.tov or 0,
                    "pf": stat.pf or 0,
                    "ts_pct": ts_pct,
                    "ortg": ortg,
                }
            )
        ranked_players.sort(key=lambda x: x["game_score"], reverse=True)
        return ranked_players[:limit]

    @staticmethod
    def calculate_team_advanced_from_stats(game, stat_rows):
        if not stat_rows:
            return None
        team_totals = AnalyticsService.sum_team_stat_rows(stat_rows)
        team_poss = calculate_possessions(
            team_totals["fga"],
            team_totals["fta"],
            team_totals["oreb"],
            team_totals["tov"],
        )
        segment_poss = (
            db.session.query(func.sum(LineupSegment.possessions))
            .filter_by(game_id=game.id)
            .scalar()
            or 0
        )
        if segment_poss > 0:
            team_poss = float(segment_poss)
        if team_poss <= 0:
            return None
        total_minutes = sum(parse_minutes(s.minutes) for s in stat_rows)
        total_game_min = total_minutes / 5.0 if total_minutes > 0 else 0
        pace = calculate_pace(team_poss, total_game_min) if total_game_min > 0 else 0
        ortg = calculate_ortg(game.team_score or 0, team_poss)
        drtg = calculate_ortg(game.opponent_score or 0, team_poss)
        net_rating = ortg - drtg
        return {
            "possessions": round(team_poss, 1),
            "pace": round(pace, 1) if total_game_min > 0 else None,
            "efg_pct": round(
                calculate_efg_percent(
                    team_totals["fgm"], team_totals["tpm"], team_totals["fga"]
                ),
                1,
            ),
            "ts_pct": round(
                calculate_ts_percent(
                    team_totals["points"], team_totals["fga"], team_totals["fta"]
                ),
                1,
            ),
            "tov_pct": round(safe_percentage(team_totals["tov"], team_poss), 1),
            "ft_rate": round(
                safe_percentage(team_totals["fta"], team_totals["fga"]), 1
            ),
            "oreb_pct": round(
                safe_percentage(team_totals["oreb"], team_totals["reb"]), 1
            ),
            "ortg": round(ortg, 1),
            "drtg": round(drtg, 1),
            "net_rating": round(net_rating, 1),
        }

    @staticmethod
    def build_opponent_game_card(game):
        stat_rows = list(game.stats or [])
        team_totals = (
            AnalyticsService.sum_team_stat_rows(stat_rows) if stat_rows else None
        )
        advanced = AnalyticsService.calculate_team_advanced_from_stats(game, stat_rows)
        margin = (game.team_score or 0) - (game.opponent_score or 0)
        return {
            "id": game.id,
            "date": game.date,
            "sort_date": game.sort_date,
            "game_type": game.game_type,
            "result": game.result,
            "team_score": game.team_score,
            "opponent_score": game.opponent_score,
            "margin": margin,
            "has_stats": bool(stat_rows),
            "team_stats": team_totals,
            "advanced": advanced,
            "top_players_by_gamescore": AnalyticsService.get_top_players_by_gamescore(
                stat_rows
            ),
            "leaders": {
                "points": AnalyticsService.get_stat_leader(stat_rows, "points"),
                "reb": AnalyticsService.get_stat_leader(stat_rows, "reb"),
                "ast": AnalyticsService.get_stat_leader(stat_rows, "ast"),
            },
        }

    @staticmethod
    def build_opponent_detail_context(opponent_name, games):
        wins = sum(1 for game in games if game.result == "W")
        losses = len(games) - wins
        avg_team_score = (
            round(sum((g.team_score or 0) for g in games) / len(games), 1)
            if games
            else 0
        )
        avg_opponent_score = (
            round(sum((g.opponent_score or 0) for g in games) / len(games), 1)
            if games
            else 0
        )
        avg_margin = (
            round(
                sum(((g.team_score or 0) - (g.opponent_score or 0)) for g in games)
                / len(games),
                1,
            )
            if games
            else 0
        )
        all_stat_rows = [stat for game in games for stat in (game.stats or [])]
        aggregate_totals = (
            AnalyticsService.sum_team_stat_rows(all_stat_rows)
            if all_stat_rows
            else None
        )
        aggregate_advanced = None
        if games and all_stat_rows:
            aggregate_game = SimpleNamespace(
                id=-1,
                team_score=sum((g.team_score or 0) for g in games),
                opponent_score=sum((g.opponent_score or 0) for g in games),
            )
            aggregate_advanced = AnalyticsService.calculate_team_advanced_from_stats(
                aggregate_game, all_stat_rows
            )
        matchup_cards = [AnalyticsService.build_opponent_game_card(g) for g in games]
        trend_data = {
            "labels": [game.date for game in reversed(games)],
            "team_scores": [game.team_score or 0 for game in reversed(games)],
            "opponent_scores": [game.opponent_score or 0 for game in reversed(games)],
            "margins": [
                (game.team_score or 0) - (game.opponent_score or 0)
                for game in reversed(games)
            ],
            "fg_pct": [
                (
                    card["team_stats"]["fg_pct"]
                    if card["team_stats"] is not None
                    else None
                )
                for card in reversed(matchup_cards)
            ],
            "ortg": [
                card["advanced"]["ortg"] if card["advanced"] else None
                for card in reversed(matchup_cards)
            ],
            "drtg": [
                card["advanced"]["drtg"] if card["advanced"] else None
                for card in reversed(matchup_cards)
            ],
        }
        return {
            "opponent_name": opponent_name,
            "games": games,
            "summary": {
                "games": len(games),
                "wins": wins,
                "losses": losses,
                "win_rate": round((wins / len(games)) * 100, 1) if games else 0,
                "avg_team_score": avg_team_score,
                "avg_opponent_score": avg_opponent_score,
                "avg_margin": avg_margin,
                "record": f"{wins}-{losses}",
            },
            "aggregate_totals": aggregate_totals,
            "aggregate_advanced": aggregate_advanced,
            "trend_data": trend_data,
            "matchup_cards": matchup_cards,
        }

    @staticmethod
    def build_player_summary_dict(
        player_name, gp, stat_totals, total_minutes, game_ppgs, total_plus_minus
    ):
        total_poss = sum(
            calculate_possessions(s.fga, s.fta, s.oreb, s.tov) for s in stat_totals
        )

        total_points = sum((s.points or 0) for s in stat_totals)
        total_reb = sum((s.reb or 0) for s in stat_totals)
        total_oreb = sum((s.oreb or 0) for s in stat_totals)
        total_dreb = sum((s.dreb or 0) for s in stat_totals)
        total_ast = sum((s.ast or 0) for s in stat_totals)
        total_stl = sum((s.stl or 0) for s in stat_totals)
        total_blk = sum((s.blk or 0) for s in stat_totals)
        total_tov = sum((s.tov or 0) for s in stat_totals)
        total_pf = sum((s.pf or 0) for s in stat_totals)
        total_fgm = sum((s.fgm or 0) for s in stat_totals)
        total_fga = sum((s.fga or 0) for s in stat_totals)
        total_tpm = sum((s.tpm or 0) for s in stat_totals)
        total_tpa = sum((s.tpa or 0) for s in stat_totals)
        total_ftm = sum((s.ftm or 0) for s in stat_totals)
        total_fta = sum((s.fta or 0) for s in stat_totals)

        ortg = calculate_ortg(total_points, total_poss)
        ppp = calculate_ppp(total_points, total_poss)
        poss_per_40 = (total_poss / (total_minutes / 40)) if total_minutes > 0 else 0

        eff = calculate_efficiency(
            total_points,
            total_reb,
            total_ast,
            total_stl,
            total_blk,
            total_fgm,
            total_fga,
            total_ftm,
            total_fta,
            total_tov,
        )

        ts_pct = calculate_ts_percent(total_points, total_fga, total_fta)
        efg_pct = calculate_efg_percent(total_fgm, total_tpm, total_fga)
        two_pt_stats = calculate_two_point_stats(
            total_fgm, total_fga, total_tpm, total_tpa
        )

        consistency = 0
        if len(game_ppgs) > 1:
            std_dev = statistics.stdev(game_ppgs)
            mean_ppg = statistics.mean(game_ppgs)
            consistency = (std_dev / mean_ppg) if mean_ppg > 0 else 0

        return {
            "player_name": player_name,
            "games_played": gp,
            "mpg": total_minutes / gp if gp > 0 else 0,
            "ppg": total_points / gp if gp > 0 else 0,
            "plus_minus_avg": (total_plus_minus / gp) if gp > 0 else 0,
            "plus_minus_total": total_plus_minus,
            "rpg": total_reb / gp if gp > 0 else 0,
            "orebpg": total_oreb / gp if gp > 0 else 0,
            "drebpg": total_dreb / gp if gp > 0 else 0,
            "apg": total_ast / gp if gp > 0 else 0,
            "spg": total_stl / gp if gp > 0 else 0,
            "bpg": total_blk / gp if gp > 0 else 0,
            "topg": total_tov / gp if gp > 0 else 0,
            "pfpg": total_pf / gp if gp > 0 else 0,
            "eff": eff / gp if gp > 0 else 0,
            "ortg": ortg,
            "ppp": ppp,
            "poss_per_40": poss_per_40,
            "usg_pct": (total_poss / gp) if gp > 0 else 0,
            "fg_pct": total_fgm / total_fga if total_fga > 0 else 0,
            "two_pt_pct": two_pt_stats["two_pt_pct"],
            "tp_pct": total_tpm / total_tpa if total_tpa > 0 else 0,
            "ft_pct": total_ftm / total_fta if total_fta > 0 else 0,
            "ts_pct": ts_pct,
            "efg_pct": efg_pct,
            "ast_tov": total_ast / total_tov if total_tov > 0 else total_ast,
            "fta_pct": safe_percentage(total_fta, total_fga),
            "oreb_pct": safe_percentage(total_oreb, total_reb),
            "consistency": consistency,
            "fgm": total_fgm,
            "fga": total_fga,
            "two_pt_made": two_pt_stats["two_pt_made"],
            "two_pt_att": two_pt_stats["two_pt_att"],
            "tpm": total_tpm,
            "tpa": total_tpa,
            "ftm": total_ftm,
            "fta": total_fta,
        }

    @staticmethod
    def build_players_listing_context(
        game_type, limit, sort_by, order, excluded_player
    ):
        game_query = Game.query.order_by(Game.sort_date.desc())
        if game_type == "Season":
            game_query = game_query.filter(Game.game_type == "Season")
        elif game_type == "Friendly":
            game_query = game_query.filter(Game.game_type == "Friendly")
        elif game_type == "Playoff":
            game_query = game_query.filter(Game.game_type == "Playoff")

        all_filtered_games = game_query.all()
        target_games = all_filtered_games[:limit] if limit > 0 else all_filtered_games
        target_game_ids = [g.id for g in target_games]

        if not target_game_ids:
            return {
                "stats": [],
                "total_row": None,
                "all_player_names": [],
                "filters": {
                    "type": game_type,
                    "limit": limit,
                    "sort": sort_by,
                    "order": order,
                    "exclude_player": excluded_player,
                },
            }

        stats_query = (
            db.session.query(
                PlayerStat.player_name,
                func.count(PlayerStat.id).label("games_played"),
                func.sum(PlayerStat.plus_minus).label("total_plus_minus"),
            )
            .filter(PlayerStat.game_id.in_(target_game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .group_by(PlayerStat.player_name)
            .all()
        )

        players_data = []
        all_player_names = []

        for row in stats_query:
            gp = row.games_played
            all_player_names.append(row.player_name)
            player_stats = (
                PlayerStat.query.filter(PlayerStat.player_name == row.player_name)
                .filter(PlayerStat.game_id.in_(target_game_ids))
                .filter(PlayerStat.minutes != "00:00")
                .filter(PlayerStat.minutes != "0")
                .all()
            )

            players_data.append(
                AnalyticsService.build_player_summary_dict(
                    row.player_name,
                    gp,
                    player_stats,
                    sum(parse_minutes(s.minutes) for s in player_stats),
                    [s.points for s in player_stats],
                    row.total_plus_minus or 0,
                )
            )

        all_player_names.sort()
        excluded_player = excluded_player if excluded_player in all_player_names else ""

        included_team_stats = (
            PlayerStat.query.filter(PlayerStat.game_id.in_(target_game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .filter(PlayerStat.player_name != excluded_player)
            .all()
            if excluded_player
            else PlayerStat.query.filter(PlayerStat.game_id.in_(target_game_ids))
            .filter(PlayerStat.minutes != "00:00")
            .filter(PlayerStat.minutes != "0")
            .all()
        )

        team_game_points = {}
        for stat in included_team_stats:
            team_game_points.setdefault(stat.game_id, 0)
            team_game_points[stat.game_id] += stat.points or 0

        team_point_diff_total = sum(
            (game.team_score or 0) - (game.opponent_score or 0) for game in target_games
        )
        team_row = AnalyticsService.build_player_summary_dict(
            "TEAM TOTAL",
            len(target_games),
            included_team_stats,
            sum(parse_minutes(s.minutes) for s in included_team_stats),
            list(team_game_points.values()),
            team_point_diff_total,
        )
        team_row["excluded_player"] = excluded_player

        reverse = order == "desc"
        players_data.sort(key=lambda x: x.get(sort_by, 0), reverse=reverse)

        return {
            "stats": players_data,
            "total_row": team_row,
            "all_player_names": all_player_names,
            "filters": {
                "type": game_type,
                "limit": limit,
                "sort": sort_by,
                "order": order,
                "exclude_player": excluded_player,
            },
        }

    @staticmethod
    def build_game_detail(game_id):
        """Build context dictionary for game detail template (extracted from route)"""
        from core.models import Game, PlayerStat, ShotEvent, LineupSegment, GameEvent
        from sqlalchemy import func
        import json
        from core.play_analytics import (
            get_play_stats,
            get_play_player_stats,
            get_player_play_stats,
            get_untracked_percentages,
        )
        from core.advanced_analytics import LineupAnalytics

        game = Game.query.get_or_404(game_id)

        stats = (
            PlayerStat.query.filter_by(game_id=game.id)
            .order_by(PlayerStat.points.desc())
            .all()
        )

        shot_events = ShotEvent.query.filter_by(game_id=game.id).all()

        plays_data = get_play_stats(game.id, play_type="Offense")
        plays_players_data = get_play_player_stats(game.id, play_type="Offense")
        players_plays_data = get_player_play_stats(game.id, play_type="Offense")
        untracked = get_untracked_percentages(game.id)

        team_possessions = sum(
            calculate_possessions(p.fga, p.fta, p.oreb, p.tov) for p in stats
        )

        for p in stats:
            p.min_decimal = parse_minutes(p.minutes)
            p.possessions = calculate_possessions(p.fga, p.fta, p.oreb, p.tov)
            p.ortg = calculate_ortg(p.points, p.possessions)
            p.ppp = calculate_ppp(p.points, p.possessions)
            p.poss_per_40 = (
                p.possessions / (p.min_decimal / 40) if p.min_decimal > 0 else 0
            )
            p.usg_pct = safe_percentage(p.possessions, team_possessions)
            p.ast_tov_ratio = (p.ast / p.tov) if p.tov > 0 else p.ast
            p.eff = calculate_efficiency(
                p.points, p.reb, p.ast, p.stl, p.blk, p.fgm, p.fga, p.ftm, p.fta, p.tov
            )
            p.ts_pct = calculate_ts_percent(p.points, p.fga, p.fta)
            p.efg_pct = calculate_efg_percent(p.fgm, p.tpm, p.fga)

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
                p.pts_100 = p.reb_100 = p.ast_100 = p.tov_100 = p.stl_100 = (
                    p.blk_100
                ) = p.pf_100 = 0

            two_pt_stats = calculate_two_point_stats(p.fgm, p.fga, p.tpm, p.tpa)
            p.two_pt_att = two_pt_stats["two_pt_att"]
            p.two_pt_made = two_pt_stats["two_pt_made"]
            p.two_pt_pct = two_pt_stats["two_pt_pct"]

            p.fta_pct = safe_percentage(p.fta, p.fga)
            p.oreb_pct = safe_percentage(p.oreb, p.reb)
            p.foul_trouble = p.pf >= 3

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
            "reb_conceded": sum(p.reb_conceded or 0 for p in stats),
        }

        team_poss = calculate_possessions(
            team_stats["fga"], team_stats["fta"], team_stats["oreb"], team_stats["tov"]
        )

        segment_poss = (
            db.session.query(func.sum(LineupSegment.possessions))
            .filter_by(game_id=game.id)
            .scalar()
            or 0
        )
        if segment_poss > 0:
            team_poss = float(segment_poss)
        team_poss = max(team_poss, 1.0)

        total_game_min = sum(p.min_decimal for p in stats) / 5.0
        pace = calculate_pace(team_poss, total_game_min)

        efg = calculate_efg_percent(
            team_stats["fgm"], team_stats["tpm"], team_stats["fga"]
        )
        ortg = calculate_ortg(game.team_score, team_poss)
        drtg = calculate_ortg(game.opponent_score, team_poss)

        advanced = {
            "possessions": round(team_poss, 1),
            "pace": round(pace, 1),
            "efg_pct": round(efg, 1),
            "ts_pct": round(
                calculate_ts_percent(
                    team_stats["points"], team_stats["fga"], team_stats["fta"]
                ),
                1,
            ),
            "tov_pct": round(safe_percentage(team_stats["tov"], team_poss), 1),
            "ft_rate": round(safe_percentage(team_stats["fta"], team_stats["fga"]), 1),
            "oreb_pct": round(
                safe_percentage(team_stats["oreb"], team_stats["reb"]), 1
            ),
            "ortg": round(ortg, 0),
            "drtg": round(drtg, 0),
        }

        two_pt_att = max(team_stats["fga"] - team_stats["tpa"], 0)
        two_pt_made = max(team_stats["fgm"] - team_stats["tpm"], 0)

        shot_summary = {
            "fgm": team_stats["fgm"],
            "fga": team_stats["fga"],
            "tpm": team_stats["tpm"],
            "tpa": team_stats["tpa"],
            "ftm": team_stats["ftm"],
            "fta": team_stats["fta"],
            "two_pt_made": two_pt_made,
            "two_pt_att": two_pt_att,
            "fg_pct": safe_percentage(team_stats["fgm"], team_stats["fga"]),
            "two_pt_pct": safe_percentage(two_pt_made, two_pt_att),
            "tp_pct": safe_percentage(team_stats["tpm"], team_stats["tpa"]),
            "ft_pct": safe_percentage(team_stats["ftm"], team_stats["fta"]),
            "efg_pct": calculate_efg_percent(
                team_stats["fgm"], team_stats["tpm"], team_stats["fga"]
            ),
            "ts_pct": calculate_ts_percent(
                team_stats["points"], team_stats["fga"], team_stats["fta"]
            ),
        }

        opponent_shots = GameEvent.query.filter(
            GameEvent.game_id == game.id,
            GameEvent.event_type == "OPP_SCORE",
            GameEvent.x_loc.isnot(None),
        ).all()

        opponent_shot_data = [
            {
                "x": s.x_loc,
                "y": s.y_loc,
                "result": "made",
                "quarter": s.quarter,
                "zone": s.zone if hasattr(s, "zone") else None,
                "points": json.loads(s.detail).get("points", 0)
                if s.detail and s.event_type == "OPP_SCORE"
                else 0,
            }
            for s in opponent_shots
            if s.x_loc is not None and s.y_loc is not None
        ]

        try:
            top_game_lineups_off = LineupAnalytics.get_game_lineup_rankings(
                game.id,
                top_n=3,
                rank_by="offensive",
                min_possessions=10,
                total_pts_scored_override=game.team_score,
                total_pts_allowed_override=game.opponent_score,
                total_possessions_override=team_poss,
            )
            top_game_lineups_def = LineupAnalytics.get_game_lineup_rankings(
                game.id,
                top_n=3,
                rank_by="defensive",
                min_possessions=10,
                total_pts_scored_override=game.team_score,
                total_pts_allowed_override=game.opponent_score,
                total_possessions_override=team_poss,
            )
        except Exception as e:
            print(f"[GameDetail] Error fetching lineups: {e}")
            top_game_lineups_off = []
            top_game_lineups_def = []

        try:
            top_game_duos_off = LineupAnalytics.get_combination_net_differentials(
                combination_type="duo",
                game_ids=[game.id],
                min_possessions=10,
                top_n=3,
                require_positive=False,
                total_pts_scored_override=game.team_score,
                total_pts_allowed_override=game.opponent_score,
                total_possessions_override=team_poss,
                rank_by="offensive",
            )
            top_game_duos_def = LineupAnalytics.get_combination_net_differentials(
                combination_type="duo",
                game_ids=[game.id],
                min_possessions=10,
                top_n=3,
                require_positive=False,
                total_pts_scored_override=game.team_score,
                total_pts_allowed_override=game.opponent_score,
                total_possessions_override=team_poss,
                rank_by="defensive",
            )
        except Exception as e:
            print(f"[GameDetail] Error fetching duos: {e}")
            top_game_duos_off = []
            top_game_duos_def = []

        try:
            top_game_trios_off = LineupAnalytics.get_combination_net_differentials(
                combination_type="trio",
                game_ids=[game.id],
                min_possessions=10,
                top_n=3,
                require_positive=False,
                total_pts_scored_override=game.team_score,
                total_pts_allowed_override=game.opponent_score,
                total_possessions_override=team_poss,
                rank_by="offensive",
            )
            top_game_trios_def = LineupAnalytics.get_combination_net_differentials(
                combination_type="trio",
                game_ids=[game.id],
                min_possessions=10,
                top_n=3,
                require_positive=False,
                total_pts_scored_override=game.team_score,
                total_pts_allowed_override=game.opponent_score,
                total_possessions_override=team_poss,
                rank_by="defensive",
            )
        except Exception as e:
            print(f"[GameDetail] Error fetching trios: {e}")
            top_game_trios_off = []
            top_game_trios_def = []

        return {
            "game": game,
            "stats": stats,
            "shot_events": shot_events,
            "opponent_shots": opponent_shot_data,
            "plays_data": plays_data,
            "plays_players_data": plays_players_data,
            "players_plays_data": players_plays_data,
            "untracked": untracked,
            "team_stats": team_stats,
            "advanced": advanced,
            "shot_summary": shot_summary,
            "top_game_lineups_off": top_game_lineups_off,
            "top_game_lineups_def": top_game_lineups_def,
            "top_game_duos_off": top_game_duos_off,
            "top_game_duos_def": top_game_duos_def,
            "top_game_trios_off": top_game_trios_off,
            "top_game_trios_def": top_game_trios_def,
        }

    @staticmethod
    def get_game_top_performers(stats_with_metrics):
        """Return top performers for points, efficiency, and rebounds as dicts."""
        if not stats_with_metrics:
            return {
                "points": {"player": None, "value": 0},
                "efficiency": {"player": None, "value": 0},
                "rebounds": {"player": None, "value": 0},
            }
        points_leader = max(stats_with_metrics, key=lambda s: getattr(s, "points", 0))
        eff_leader = max(stats_with_metrics, key=lambda s: getattr(s, "eff", 0))
        reb_leader = max(stats_with_metrics, key=lambda s: getattr(s, "reb", 0))
        return {
            "points": {
                "player": points_leader.player_name,
                "value": points_leader.points,
            },
            "efficiency": {"player": eff_leader.player_name, "value": eff_leader.eff},
            "rebounds": {"player": reb_leader.player_name, "value": reb_leader.reb},
        }

    @staticmethod
    def get_team_aggregates(stats_with_metrics):
        """Compute team-level aggregates and advanced metrics."""
        if not stats_with_metrics:
            return {}
        total_fgm = sum(getattr(s, "fgm", 0) or 0 for s in stats_with_metrics)
        total_fga = sum(getattr(s, "fga", 0) or 0 for s in stats_with_metrics)
        total_tpm = sum(getattr(s, "tpm", 0) or 0 for s in stats_with_metrics)
        total_tpa = sum(getattr(s, "tpa", 0) or 0 for s in stats_with_metrics)
        total_ftm = sum(getattr(s, "ftm", 0) or 0 for s in stats_with_metrics)
        total_fta = sum(getattr(s, "fta", 0) or 0 for s in stats_with_metrics)
        total_pts = sum(getattr(s, "points", 0) or 0 for s in stats_with_metrics)
        total_oreb = sum(getattr(s, "oreb", 0) or 0 for s in stats_with_metrics)
        total_dreb = sum(getattr(s, "dreb", 0) or 0 for s in stats_with_metrics)
        total_reb = sum(getattr(s, "reb", 0) or 0 for s in stats_with_metrics)
        total_ast = sum(getattr(s, "ast", 0) or 0 for s in stats_with_metrics)
        total_tov = sum(getattr(s, "tov", 0) or 0 for s in stats_with_metrics)
        total_pf = sum(getattr(s, "pf", 0) or 0 for s in stats_with_metrics)
        total_blk = sum(getattr(s, "blk", 0) or 0 for s in stats_with_metrics)
        total_stl = sum(getattr(s, "stl", 0) or 0 for s in stats_with_metrics)

        two_pt_made = total_fgm - total_tpm
        two_pt_att = total_fga - total_tpa
        fg_pct = safe_percentage(total_fgm, total_fga)
        tp_pct = safe_percentage(total_tpm, total_tpa)
        ft_pct = safe_percentage(total_ftm, total_fta)
        two_pt_pct = safe_percentage(two_pt_made, two_pt_att)
        ts_pct = calculate_ts_percent(total_pts, total_fga, total_fta)
        efg_pct = calculate_efg_percent(total_fgm, total_tpm, total_fga)
        ast_tov = (total_ast / total_tov) if total_tov > 0 else total_ast

        return {
            "fgm": total_fgm,
            "fga": total_fga,
            "tpm": total_tpm,
            "tpa": total_tpa,
            "ftm": total_ftm,
            "fta": total_fta,
            "points": total_pts,
            "oreb": total_oreb,
            "dreb": total_dreb,
            "reb": total_reb,
            "ast": total_ast,
            "tov": total_tov,
            "pf": total_pf,
            "blk": total_blk,
            "stl": total_stl,
            "fg_pct": fg_pct,
            "tp_pct": tp_pct,
            "ft_pct": ft_pct,
            "two_pt_pct": two_pt_pct,
            "ts_pct": ts_pct,
            "efg_pct": efg_pct,
            "ast_tov": ast_tov,
        }

    @staticmethod
    def get_game_alerts(stats_with_metrics):
        """Placeholder for game alerts."""
        return []
