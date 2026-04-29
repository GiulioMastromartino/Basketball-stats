from collections import defaultdict
from itertools import groupby
from sqlalchemy import func, desc
from core.models import PlayerStat, db
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
    get_player_stats_averages,
    normalize_per_100_possessions,
    safe_percentage,
    calculate_per_100_minutes,
    calculate_pace,
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
    def get_game_top_performers(stats):
        """Top 3 performers by efficiency"""
        valid_stats = [s for s in stats if hasattr(s, "eff") and s.eff is not None]
        sorted_by_eff = sorted(valid_stats, key=lambda x: x.eff, reverse=True)
        sorted_by_pts = sorted(stats, key=lambda x: x.points, reverse=True)
        sorted_by_reb = sorted(stats, key=lambda x: x.reb, reverse=True)

        return {
            "efficiency": sorted_by_eff[0] if sorted_by_eff else None,
            "points": sorted_by_pts[0] if sorted_by_pts else None,
            "rebounds": sorted_by_reb[0] if sorted_by_reb else None,
        }

    @staticmethod
    def get_game_alerts(stats):
        """Extract fouls and low efficiency alerts"""
        return {
            "foul_trouble": [s for s in stats if s.pf >= 4],
            "inefficient": [
                s for s in stats if s.fga > 5 and hasattr(s, "ppp") and s.ppp < 0.8
            ],
        }

    @staticmethod
    def get_team_aggregates(stats):
        """Team-level shooting and efficiency"""
        total_fgm = sum(s.fgm for s in stats)
        total_fga = sum(s.fga for s in stats)
        total_tpm = sum(s.tpm for s in stats)
        total_tpa = sum(s.tpa for s in stats)
        total_ftm = sum(s.ftm for s in stats)
        total_fta = sum(s.fta for s in stats)
        total_pts = sum(s.points for s in stats)

        total_2pm = total_fgm - total_tpm
        total_2pa = total_fga - total_tpa

        return {
            "fg_pct": safe_percentage(total_fgm, total_fga),
            "tp_pct": safe_percentage(total_tpm, total_tpa),
            "ft_pct": safe_percentage(total_ftm, total_fta),
            "two_pt_pct": safe_percentage(total_2pm, total_2pa),
            "ts_pct": calculate_ts_percent(total_pts, total_fga, total_fta),
        }

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
