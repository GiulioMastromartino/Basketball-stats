"""
Advanced PDF Report Generator
Generates comprehensive PDF reports with visualizations including:
- Visual Game Report (Score Worm, Quarterly Flow, Four Factors)
- Lineup Analysis Report
- Player Scouting Card
- Season Trend Report
- Clutch Time Report
"""

import io
import base64
from datetime import datetime
from collections import defaultdict
from statistics import mean, stdev
from typing import Dict, List, Any, Optional

from flask import render_template
from weasyprint import HTML
from sqlalchemy import func

from core.models import (
    db,
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    Play,
    LineupSegment,
    Possession,
)
from core.advanced_analytics import (
    AdvancedPlayerStats,
    ClutchPerformance,
    LineupAnalytics,
    AnalyticsEngine,
    ShotChartAnalytics,
    classify_shot_zone,
    get_expected_value,
)
from core.utils import safe_percentage, parse_minutes, calculate_possessions
from core.charts import generate_shot_chart, generate_team_shot_chart


class AdvancedPDFReports:
    """Advanced PDF report generation with visualizations."""

    @staticmethod
    def _filter_games_by_type(query, game_type: str):
        if game_type == "Season":
            return query.filter(Game.game_type == "Season")
        if game_type == "Friendly":
            return query.filter(Game.game_type == "Friendly")
        return query

    @staticmethod
    def generate_visual_game_report(game_id: int) -> tuple:
        """
        Generate a visual game report with:
        - Score Worm (lead changes over game)
        - Quarterly Flow (scoring by quarter)
        - Four Factors Dashboard

        Returns:
            Tuple of (filename, pdf_bytes)
        """
        game = Game.query.get_or_404(game_id)
        stats = PlayerStat.query.filter_by(game_id=game_id).all()

        if not stats:
            return None, None
        
        # Get game events for score worm
        events = (
            GameEvent.query.filter_by(game_id=game_id)
            .order_by(GameEvent.timestamp)
            .all()
        )

        # Build score worm data
        score_worm = AdvancedPDFReports._build_score_worm(events, game)

        # Build quarterly flow
        quarterly_flow = AdvancedPDFReports._build_quarterly_flow(events, stats, game)

        # Get four factors
        four_factors = AnalyticsEngine.get_four_factors(game_id=game_id)
        
        # Get team totals
        team_totals = {
            "points": sum(s.points for s in stats),
            "fgm": sum(s.fgm for s in stats),
            "fga": sum(s.fga for s in stats),
            "tpm": sum(s.tpm for s in stats),
            "tpa": sum(s.tpa for s in stats),
            "ftm": sum(s.ftm for s in stats),
            "fta": sum(s.fta for s in stats),
            "reb": sum(s.reb for s in stats),
            "ast": sum(s.ast for s in stats),
            "tov": sum(s.tov for s in stats),
            "stl": sum(s.stl for s in stats),
            "blk": sum(s.blk for s in stats),
        }

        # Top performers
        top_performers = sorted(stats, key=lambda s: s.points, reverse=True)[:3]

        # Shot chart
        shot_chart = generate_team_shot_chart([game_id], db.session)
        
        html = render_template(
            "reports/visual_game_report.html",
            game=game,
            stats=stats,
            team_totals=team_totals,
            score_worm=score_worm,
            quarterly_flow=quarterly_flow,
            four_factors=four_factors,
            top_performers=top_performers,
            shot_chart=shot_chart,
            generated_date=datetime.now().strftime("%B %d, %Y"),
        )

        pdf_doc = HTML(string=html)
        pdf_bytes = pdf_doc.write_pdf()
        filename = f"visual_game_report_{game.opponent}_{game.date}.pdf"

        return filename, pdf_bytes

    @staticmethod
    def _build_score_worm(events: List, game: Game) -> Dict:
        """Build score worm data showing lead changes."""
        team_score = 0
        opp_score = 0
        score_progression = []

        for event in events:
            if (
                event.event_type in ["SHOT_2PT", "SHOT_3PT", "FT_MADE"]
                and event.shot_attempt == "made"
            ):
                if event.event_type == "SHOT_2PT":
                    team_score += 2
                elif event.event_type == "SHOT_3PT":
                    team_score += 3
                elif event.event_type == "FT_MADE":
                    team_score += 1
            elif event.event_type == "OPP_SCORE":
                try:
                    opp_score += int(event.detail or 0)
                except (ValueError, TypeError):
                    pass

            score_progression.append(
                {
                    "timestamp": event.timestamp,
                    "team_score": team_score,
                    "opp_score": opp_score,
                    "margin": team_score - opp_score,
                }
            )

        # Add final score
        score_progression.append(
            {
                "timestamp": float("inf"),
                "team_score": game.team_score,
                "opp_score": game.opponent_score,
                "margin": game.team_score - game.opponent_score,
            }
        )

        return {
            "progression": score_progression,
            "final_margin": game.team_score - game.opponent_score,
        }

    @staticmethod
    def _build_quarterly_flow(events: List, stats: List, game: Game) -> Dict:
        """Build quarterly scoring breakdown."""
        quarters = {
            1: {"team": 0, "opp": 0},
            2: {"team": 0, "opp": 0},
            3: {"team": 0, "opp": 0},
            4: {"team": 0, "opp": 0},
        }

        for event in events:
            quarter = event.quarter or 1
            if quarter not in quarters:
                quarters[quarter] = {"team": 0, "opp": 0}

            if (
                event.event_type in ["SHOT_2PT", "SHOT_3PT"]
                and event.shot_attempt == "made"
            ):
                points = 2 if event.event_type == "SHOT_2PT" else 3
                quarters[quarter]["team"] += points
            elif event.event_type == "FT_MADE":
                quarters[quarter]["team"] += 1
            elif event.event_type == "OPP_SCORE":
                try:
                    quarters[quarter]["opp"] += int(event.detail or 0)
                except (ValueError, TypeError):
                    pass

        return {
            "quarters": quarters,
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "team_scores": [quarters[i]["team"] for i in range(1, 5)],
            "opp_scores": [quarters[i]["opp"] for i in range(1, 5)],
        }

    @staticmethod
    def generate_lineup_report(
        game_ids: List[int] = None, min_possessions: int = 5
    ) -> tuple:
        """
        Generate lineup analysis report with:
        - Top 5 Lineups ranked by Net Rating
        - Substitution Timeline (Gantt chart)
        - Duo Compatibility Matrix
        
        Returns:
            Tuple of (filename, pdf_bytes)
        """
        # Get lineup rankings
        rankings = LineupAnalytics.get_lineup_efficiency_rankings(
            game_ids, min_possessions
        )

        # Use ON/OFF differential so compatibility is centered around neutral (0.0).
        duo_impacts = LineupAnalytics.get_combination_net_differentials(
            combination_type="duo",
            game_ids=game_ids,
            min_possessions=min_possessions,
            top_n=200,
            require_positive=False,
        )
        duos = [
            {
                "player1": duo["players"][0],
                "player2": duo["players"][1],
                "segments": duo["segments"],
                "possessions": duo["on"]["possessions"],
                "minutes": duo["on"]["minutes"],
                "ortg": duo["on"]["ortg"],
                "drtg": duo["on"]["drtg"],
                "net_rating": duo["on"]["net"],
                "compatibility": duo["impact"]["net_differential"],
            }
            for duo in duo_impacts
        ]

        # Get trio compatibility
        trios = LineupAnalytics.calculate_trio_compatibility(game_ids)

        # Build duo matrix for visualization
        duo_matrix = AdvancedPDFReports._build_duo_matrix(duos)
        
        html = render_template(
            "reports/lineup_report.html",
            rankings=rankings[:10],
            duos=duos[:20],
            trios=trios[:10],
            duo_matrix=duo_matrix,
            generated_date=datetime.now().strftime("%B %d, %Y"),
        )

        pdf_doc = HTML(string=html)
        pdf_bytes = pdf_doc.write_pdf()
        filename = f"lineup_analysis_{datetime.now().strftime('%Y%m%d')}.pdf"

        return filename, pdf_bytes

    @staticmethod
    def _build_duo_matrix(duos: List[Dict]) -> Dict:
        """Build a matrix representation of duo compatibility."""
        # Get unique players
        players = set()
        for duo in duos:
            players.add(duo["player1"])
            players.add(duo["player2"])
        players = sorted(list(players))

        # Build matrix
        matrix = {}
        for p1 in players:
            matrix[p1] = {}
            for p2 in players:
                if p1 == p2:
                    matrix[p1][p2] = None
                else:
                    # Find the duo
                    for duo in duos:
                        if (duo["player1"] == p1 and duo["player2"] == p2) or (
                            duo["player1"] == p2 and duo["player2"] == p1
                        ):
                            matrix[p1][p2] = duo.get(
                                "compatibility", duo.get("net_rating")
                            )
                            break
                    else:
                        matrix[p1][p2] = None

        return {"players": players, "matrix": matrix}

    @staticmethod
    def generate_player_scouting_card(
        player_name: str, game_type: str = "ALL"
    ) -> tuple:
        """
        Generate a player scouting card with:
        - Shot Chart visualization
        - Hot Zones color-coded
        - Advanced metrics

        Returns:
            Tuple of (filename, pdf_bytes)
        """
        # Get player stats
        stats = AnalyticsEngine.get_player_season_stats(player_name, game_type)

        if not stats:
            return None, None

        game_query = AdvancedPDFReports._filter_games_by_type(
            Game.query.order_by(Game.sort_date.asc()), game_type
        )
        games = game_query.all()
        game_ids = [g.id for g in games]

        # Get shot data
        shots_query = ShotEvent.query.filter(ShotEvent.player_name == player_name)
        if game_ids:
            shots_query = shots_query.filter(ShotEvent.game_id.in_(game_ids))
        shots = shots_query.all()
        shot_data = [
            {
                "points": s.points or 0,
                "x_loc": s.x_loc,
                "y_loc": s.y_loc,
                "shot_type": s.shot_type,
                "result": s.result,
            }
            for s in shots
        ]

        # Calculate shot quality
        shot_quality = AdvancedPlayerStats.calculate_shot_quality_score(shot_data)

        # Get zone heatmap
        heatmap = ShotChartAnalytics.get_heatmap_data(
            game_ids=game_ids if game_ids else None, player_name=player_name
        )

        # Generate shot chart image
        shot_chart = generate_shot_chart(
            player_name, game_ids if game_ids else None, db.session
        )

        # Get games played
        query = PlayerStat.query.filter(PlayerStat.player_name == player_name)
        query = AdvancedPDFReports._filter_games_by_type(query.join(Game), game_type)

        player_stats = query.all()
        games_played = len({s.game_id for s in player_stats})

        # Calculate consistency
        points_values = [s.points for s in player_stats]
        consistency = {
            "std_dev": round(stdev(points_values), 1) if len(points_values) > 1 else 0,
            "mean": round(mean(points_values), 1) if points_values else 0,
            "cv": round(stdev(points_values) / mean(points_values) * 100, 1)
            if len(points_values) > 1 and mean(points_values) > 0
            else 0,
        }

        html = render_template(
            "reports/player_scouting_card.html",
            player_name=player_name,
            stats=stats,
            shot_quality=shot_quality,
            heatmap=heatmap,
            shot_chart=shot_chart,
            has_shot_data=bool(shots),
            games_played=games_played,
            consistency=consistency,
            game_type=game_type,
            generated_date=datetime.now().strftime("%B %d, %Y"),
        )

        pdf_doc = HTML(string=html)
        pdf_bytes = pdf_doc.write_pdf()
        filename = f"scouting_{player_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        return filename, pdf_bytes

    @staticmethod
    def generate_season_trend_report(
        player_name: str = None, game_type: str = "Season"
    ) -> tuple:
        """
        Generate season trend report with:
        - Rolling averages (5/10 games)
        - Consistency index
        - Performance variance visualization

        Returns:
            Tuple of (filename, pdf_bytes)
        """
        # Get games
        query = AdvancedPDFReports._filter_games_by_type(
            Game.query.order_by(Game.sort_date.asc()), game_type
        )

        games = query.all()
        game_ids = [g.id for g in games]

        # Always include all players in the filtered report.
        players = [
            p[0]
            for p in db.session.query(PlayerStat.player_name)
            .filter(PlayerStat.game_id.in_(game_ids))
            .distinct()
            .all()
        ]

        player_trends = {}
        for player in players:
            stats = (
                PlayerStat.query.filter(PlayerStat.player_name == player)
                .filter(PlayerStat.game_id.in_(game_ids))
                .join(Game)
                .order_by(Game.sort_date)
                .all()
            )

            if not stats:
                continue

            # Calculate rolling averages
            points_values = [s.points for s in stats]
            ts_values = []

            for s in stats:
                denom = 2 * (s.fga + 0.44 * s.fta)
                ts = (s.points / denom * 100) if denom > 0 else 0
                ts_values.append(ts)

            # 5-game rolling average
            rolling_5 = []
            for i in range(len(points_values)):
                if i < 4:
                    rolling_5.append(None)
                else:
                    rolling_5.append(round(mean(points_values[i - 4 : i + 1]), 1))

            # 10-game rolling average
            rolling_10 = []
            for i in range(len(points_values)):
                if i < 9:
                    rolling_10.append(None)
                else:
                    rolling_10.append(round(mean(points_values[i - 9 : i + 1]), 1))

            player_trends[player] = {
                "dates": [s.game.date for s in stats],
                "points": points_values,
                "ts_pct": ts_values,
                "rolling_5": rolling_5,
                "rolling_10": rolling_10,
                "mean": round(mean(points_values), 1),
                "std_dev": round(stdev(points_values), 1)
                if len(points_values) > 1
                else 0,
                "cv": round(stdev(points_values) / mean(points_values) * 100, 1)
                if len(points_values) > 1 and mean(points_values) > 0
                else 0,
                "games": len(stats),
            }

        player_trends = dict(
            sorted(
                player_trends.items(),
                key=lambda item: (item[1]["games"], item[1]["mean"]),
                reverse=True,
            )
        )

        consistency_leaders = sorted(
            player_trends.items(),
            key=lambda item: item[1]["cv"],
        )[:8]

        html = render_template(
            "reports/season_trend_report.html",
            player_trends=player_trends,
            consistency_leaders=consistency_leaders,
            total_games=len(games),
            game_type=game_type,
            generated_date=datetime.now().strftime("%B %d, %Y"),
        )

        pdf_doc = HTML(string=html)
        pdf_bytes = pdf_doc.write_pdf()
        filename = f"season_trends_{datetime.now().strftime('%Y%m%d')}.pdf"

        return filename, pdf_bytes

    @staticmethod
    def generate_clutch_report(game_type: str = "Season") -> tuple:
        """
        Generate clutch time performance report.

        Returns:
            Tuple of (filename, pdf_bytes)
        """
        # Get games
        query = Game.query
        if game_type == "Season":
            query = query.filter(Game.game_type == "Season")

        games = query.all()
        game_ids = [g.id for g in games]

        # Aggregate clutch stats per player
        player_clutch = defaultdict(
            lambda: {
                "clutch_plays": 0,
                "clutch_points": 0,
                "clutch_fga": 0,
                "clutch_fgm": 0,
                "clutch_tov": 0,
                "games_with_clutch": set(),
            }
        )

        for game_id in game_ids:
            events = GameEvent.query.filter(
                GameEvent.game_id == game_id, GameEvent.score_margin.isnot(None)
            ).all()

            for event in events:
                if not event.player_name:
                    continue

                # Check if clutch situation
                from core.advanced_analytics import parse_time_to_seconds

                time_secs = parse_time_to_seconds(event.time_remaining or "5:00")

                if ClutchPerformance.is_clutch_situation(
                    event.score_margin or 0, time_secs
                ):
                    player_clutch[event.player_name]["clutch_plays"] += 1
                    player_clutch[event.player_name]["games_with_clutch"].add(game_id)

                    if event.event_type in ["SHOT_2PT", "SHOT_3PT"]:
                        player_clutch[event.player_name]["clutch_fga"] += 1
                        if event.shot_attempt == "made":
                            player_clutch[event.player_name]["clutch_fgm"] += 1
                            pts = 2 if event.event_type == "SHOT_2PT" else 3
                            player_clutch[event.player_name]["clutch_points"] += pts
                    elif event.event_type == "FT_MADE":
                        player_clutch[event.player_name]["clutch_points"] += 1
                    elif event.event_type == "TURNOVER":
                        player_clutch[event.player_name]["clutch_tov"] += 1

        # Calculate percentages and format results
        results = []
        for player, stats in player_clutch.items():
            if stats["clutch_plays"] > 0:
                results.append(
                    {
                        "player": player,
                        "clutch_plays": stats["clutch_plays"],
                        "clutch_points": stats["clutch_points"],
                        "clutch_fga": stats["clutch_fga"],
                        "clutch_fgm": stats["clutch_fgm"],
                        "clutch_fg_pct": round(
                            stats["clutch_fgm"] / stats["clutch_fga"] * 100, 1
                        )
                        if stats["clutch_fga"] > 0
                        else 0,
                        "clutch_tov": stats["clutch_tov"],
                        "games_with_clutch": len(stats["games_with_clutch"]),
                    }
                )

        # Sort by clutch points
        results.sort(key=lambda x: x["clutch_points"], reverse=True)

        # Pagination setup
        players_per_page = 15
        total_pages = (len(results) + players_per_page - 1) // players_per_page

        html = render_template(
            "reports/clutch_report.html",
            clutch_stats=results,
            game_type=game_type,
            generated_date=datetime.now().strftime("%B %d, %Y"),
            players_per_page=players_per_page,
            total_pages=total_pages,
        )

        pdf_doc = HTML(string=html)
        pdf_bytes = pdf_doc.write_pdf()
        filename = f"clutch_report_{datetime.now().strftime('%Y%m%d')}.pdf"

        return filename, pdf_bytes


# Report generation functions for routes
def generate_visual_game_report_bytes(game_id: int):
    """Wrapper for visual game report generation."""
    return AdvancedPDFReports.generate_visual_game_report(game_id)


def generate_lineup_report_bytes(game_ids: List[int] = None, min_possessions: int = 5):
    """Wrapper for lineup report generation."""
    return AdvancedPDFReports.generate_lineup_report(game_ids, min_possessions)


def generate_player_scouting_card_bytes(player_name: str, game_type: str = "ALL"):
    """Wrapper for player scouting card generation."""
    return AdvancedPDFReports.generate_player_scouting_card(player_name, game_type)


def generate_season_trend_report_bytes(
    player_name: str = None, game_type: str = "Season"
):
    """Wrapper for season trend report generation."""
    return AdvancedPDFReports.generate_season_trend_report(player_name, game_type)


def generate_clutch_report_bytes(game_type: str = "Season"):
    """Wrapper for clutch report generation."""
    return AdvancedPDFReports.generate_clutch_report(game_type)
