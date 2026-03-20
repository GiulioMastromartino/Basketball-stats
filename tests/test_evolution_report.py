"""
Tests for Evolution Report feature.

Covers domain models (core/evolution_report.py) and service layer
(core/services/evolution_report_service.py).
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from core.evolution_report import (
    TeamSnapshot,
    PlayerSnapshot,
    ScoringRun,
    QuarterSummary,
    EvolutionReport,
    safe_div,
    round_to,
    parse_time_to_seconds,
    seconds_to_time,
)
from core.services.game_service import create_game_from_live_data
from core.services.evolution_report_service import EvolutionReportService
from core.services.schema4_evolution_report_service import (
    Schema4EvolutionReportService,
)
from core.models import Game, GameEvent, PlayerStat


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def game_event_factory():
    """Factory for creating GameEvent instances without database."""

    def _create(**kwargs):
        defaults = {
            "id": 1,
            "game_id": 1,
            "event_type": "SHOT_2PT",
            "player_name": "Test Player",
            "detail": None,
            "timestamp": 1000,
            "shot_attempt": None,
            "quarter": 1,
            "time_remaining": "08:00",
            "score_margin": 0,
            "game_seconds": 120,
            "possession_number": 1,
        }
        defaults.update(kwargs)
        return Mock(**defaults)

    return _create


@pytest.fixture
def game_factory():
    """Factory for creating Game instances without database."""

    def _create(**kwargs):
        defaults = {
            "id": 1,
            "date": "17-02-2024",
            "opponent": "Test Opponent",
            "team_score": 75,
            "opponent_score": 68,
            "result": "W",
            "game_type": "Season",
            "sort_date": "2024-02-17",
            "source": "MANUAL",
        }
        defaults.update(kwargs)
        return Mock(**defaults)

    return _create


@pytest.fixture
def team_snapshot_factory():
    """Factory for creating TeamSnapshot instances."""

    def _create(**kwargs):
        defaults = {
            "game_seconds": 0,
            "quarter": 1,
            "time_remaining": "10:00",
            "team_score": 0,
            "opp_score": 0,
            "fgm": 0,
            "fga": 0,
            "tpm": 0,
            "tpa": 0,
            "ftm": 0,
            "fta": 0,
            "orb": 0,
            "drb": 0,
            "ast": 0,
            "stl": 0,
            "blk": 0,
            "tov": 0,
            "lineup": [],
        }
        defaults.update(kwargs)
        return TeamSnapshot(**defaults)

    return _create


@pytest.fixture
def player_snapshot_factory():
    """Factory for creating PlayerSnapshot instances."""

    def _create(**kwargs):
        defaults = {
            "player_name": "Test Player",
            "game_seconds": 0,
            "quarter": 1,
            "time_remaining": "10:00",
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
            "plus_minus": 0,
        }
        defaults.update(kwargs)
        return PlayerSnapshot(**defaults)

    return _create


@pytest.fixture
def sample_events(game_event_factory):
    """Create sample game events for testing."""
    return [
        game_event_factory(
            id=1,
            event_type="SHOT_2PT",
            player_name="Player A",
            quarter=1,
            game_seconds=30,
            time_remaining="09:30",
            shot_attempt="made",
        ),
        game_event_factory(
            id=2,
            event_type="SHOT_3PT",
            player_name="Player B",
            quarter=1,
            game_seconds=60,
            time_remaining="09:00",
            shot_attempt="made",
        ),
        game_event_factory(
            id=3,
            event_type="OPP_SCORE",
            player_name=None,
            quarter=1,
            game_seconds=90,
            time_remaining="08:30",
            detail=json.dumps({"points": 2}),
        ),
        game_event_factory(
            id=4,
            event_type="FT",
            player_name="Player A",
            quarter=1,
            game_seconds=120,
            time_remaining="08:00",
            detail=json.dumps({"ftm": 2, "fta": 2}),
        ),
        game_event_factory(
            id=5,
            event_type="TURNOVER",
            player_name="Player C",
            quarter=1,
            game_seconds=150,
            time_remaining="07:30",
        ),
        game_event_factory(
            id=6,
            event_type="OREB",
            player_name="Player A",
            quarter=1,
            game_seconds=180,
            time_remaining="07:00",
        ),
        game_event_factory(
            id=7,
            event_type="DREB",
            player_name="Player B",
            quarter=1,
            game_seconds=210,
            time_remaining="06:30",
        ),
        game_event_factory(
            id=8,
            event_type="AST",
            player_name="Player C",
            quarter=1,
            game_seconds=240,
            time_remaining="06:00",
        ),
        game_event_factory(
            id=9,
            event_type="STL",
            player_name="Player A",
            quarter=1,
            game_seconds=270,
            time_remaining="05:30",
        ),
        game_event_factory(
            id=10,
            event_type="BLK",
            player_name="Player B",
            quarter=1,
            game_seconds=300,
            time_remaining="05:00",
        ),
    ]


@pytest.fixture
def multi_quarter_events(game_event_factory):
    """Create events spanning multiple quarters."""
    events = []

    for q in range(1, 5):
        base_seconds = (q - 1) * 600
        for i in range(5):
            events.append(
                game_event_factory(
                    id=len(events) + 1,
                    event_type="SHOT_2PT",
                    player_name=f"Player {i + 1}",
                    quarter=q,
                    game_seconds=base_seconds + i * 60,
                    time_remaining=f"{9 - i}:00",
                    shot_attempt="made" if i % 2 == 0 else None,
                )
            )
            events.append(
                game_event_factory(
                    id=len(events) + 1,
                    event_type="OPP_SCORE",
                    player_name=None,
                    quarter=q,
                    game_seconds=base_seconds + i * 60 + 30,
                    time_remaining=f"{8 - i}:30",
                    detail=json.dumps({"points": 2}),
                )
            )

    return events


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestSafeDiv:
    """Tests for safe_div helper function."""

    def test_safe_div_normal_division_returns_result(self):
        assert safe_div(10, 2) == 5.0

    def test_safe_div_zero_denominator_returns_default(self):
        assert safe_div(10, 0) == 0.0

    def test_safe_div_zero_denominator_custom_default_returns_custom(self):
        assert safe_div(10, 0, default=100.0) == 100.0

    def test_safe_div_negative_numbers_returns_result(self):
        assert safe_div(-10, 2) == -5.0

    def test_safe_div_float_values_returns_result(self):
        result = safe_div(7.5, 2.5)
        assert result == 3.0


class TestRoundTo:
    """Tests for round_to helper function."""

    def test_round_to_default_one_decimal(self):
        assert round_to(3.14159) == 3.1

    def test_round_to_two_decimals(self):
        assert round_to(3.14159, decimals=2) == 3.14

    def test_round_to_zero_decimals(self):
        assert round_to(3.14159, decimals=0) == 3.0

    def test_round_to_negative_number(self):
        assert round_to(-3.14159) == -3.1


class TestParseTimeToSeconds:
    """Tests for parse_time_to_seconds helper function."""

    def test_parse_time_normal_format_returns_seconds(self):
        assert parse_time_to_seconds("05:30") == 330

    def test_parse_time_zero_returns_zero(self):
        assert parse_time_to_seconds("00:00") == 0

    def test_parse_time_large_minutes_returns_correct(self):
        assert parse_time_to_seconds("15:45") == 945

    def test_parse_time_invalid_format_returns_zero(self):
        assert parse_time_to_seconds("invalid") == 0

    def test_parse_time_none_returns_zero(self):
        assert parse_time_to_seconds(None) == 0

    def test_parse_time_single_part_returns_zero(self):
        assert parse_time_to_seconds("30") == 0


class TestSecondsToTime:
    """Tests for seconds_to_time helper function."""

    def test_seconds_to_time_normal_returns_formatted(self):
        assert seconds_to_time(330) == "05:30"

    def test_seconds_to_time_zero_returns_zero(self):
        assert seconds_to_time(0) == "00:00"

    def test_seconds_to_time_large_value_returns_formatted(self):
        assert seconds_to_time(945) == "15:45"

    def test_seconds_to_time_negative_returns_zero(self):
        assert seconds_to_time(-30) == "00:00"

    def test_seconds_to_time_pads_seconds(self):
        assert seconds_to_time(65) == "01:05"


# =============================================================================
# TeamSnapshot Tests
# =============================================================================


class TestTeamSnapshot:
    """Tests for TeamSnapshot dataclass and __post_init__ calculations."""

    def test_team_snapshot_margin_calculated_correctly(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(team_score=75, opp_score=68)
        assert snapshot.margin == 7

    def test_team_snapshot_negative_margin_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(team_score=68, opp_score=75)
        assert snapshot.margin == -7

    def test_team_snapshot_possessions_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(fga=50, fta=20, orb=10, tov=12)
        expected = round_to(50 + 0.44 * 20 - 10 + 12)
        assert snapshot.possessions == expected

    def test_team_snapshot_oer_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(team_score=75, fga=50, fta=20, orb=10, tov=12)
        possessions = 50 + 0.44 * 20 - 10 + 12
        expected_oer = round_to(safe_div(75, possessions) * 100)
        assert snapshot.oer == expected_oer

    def test_team_snapshot_oer_zero_possessions_returns_zero(
        self, team_snapshot_factory
    ):
        snapshot = team_snapshot_factory(team_score=75, fga=0, fta=0, orb=0, tov=0)
        assert snapshot.oer == 0.0

    def test_team_snapshot_der_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(opp_score=68, fga=50, fta=20, orb=10, tov=12)
        possessions = 50 + 0.44 * 20 - 10 + 12
        expected_der = round_to(safe_div(68, possessions) * 100)
        assert snapshot.der == expected_der

    def test_team_snapshot_efg_pct_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(fgm=25, tpm=8, fga=50)
        expected_efg = round_to(safe_div(25 + 0.5 * 8, 50) * 100)
        assert snapshot.efg_pct == expected_efg

    def test_team_snapshot_efg_pct_zero_fga_returns_zero(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(fgm=0, tpm=0, fga=0)
        assert snapshot.efg_pct == 0.0

    def test_team_snapshot_ts_pct_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(team_score=75, fga=50, fta=20)
        expected_ts = round_to(safe_div(75, 2 * (50 + 0.44 * 20)) * 100)
        assert snapshot.ts_pct == expected_ts

    def test_team_snapshot_tov_pct_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(tov=12, fga=50, fta=20)
        expected_tov_pct = round_to(safe_div(12, 50 + 0.44 * 20 + 12) * 100)
        assert snapshot.tov_pct == expected_tov_pct

    def test_team_snapshot_orb_pct_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(orb=10, drb=20)
        expected_orb_pct = round_to(safe_div(10, 10 + 20) * 100)
        assert snapshot.orb_pct == expected_orb_pct

    def test_team_snapshot_orb_pct_zero_rebounds_returns_zero(
        self, team_snapshot_factory
    ):
        snapshot = team_snapshot_factory(orb=0, drb=0)
        assert snapshot.orb_pct == 0.0

    def test_team_snapshot_ft_rate_calculated(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(ftm=15, fga=50)
        expected_ft_rate = round_to(safe_div(15, 50) * 100)
        assert snapshot.ft_rate == expected_ft_rate

    def test_team_snapshot_ft_rate_zero_fga_returns_zero(self, team_snapshot_factory):
        snapshot = team_snapshot_factory(ftm=15, fga=0)
        assert snapshot.ft_rate == 0.0

    def test_team_snapshot_lineup_stored(self, team_snapshot_factory):
        lineup = ["Player A", "Player B", "Player C", "Player D", "Player E"]
        snapshot = team_snapshot_factory(lineup=lineup)
        assert snapshot.lineup == lineup


# =============================================================================
# PlayerSnapshot Tests
# =============================================================================


class TestPlayerSnapshot:
    """Tests for PlayerSnapshot dataclass and __post_init__ calculations."""

    def test_player_snapshot_efg_pct_calculated(self, player_snapshot_factory):
        snapshot = player_snapshot_factory(fgm=5, tpm=2, fga=12)
        expected_efg = round_to(safe_div(5 + 0.5 * 2, 12) * 100)
        assert snapshot.efg_pct == expected_efg

    def test_player_snapshot_efg_pct_zero_fga_returns_zero(
        self, player_snapshot_factory
    ):
        snapshot = player_snapshot_factory(fgm=0, tpm=0, fga=0)
        assert snapshot.efg_pct == 0.0

    def test_player_snapshot_ts_pct_calculated(self, player_snapshot_factory):
        snapshot = player_snapshot_factory(pts=18, fga=14, fta=3)
        expected_ts = round_to(safe_div(18, 2 * (14 + 0.44 * 3)) * 100)
        assert snapshot.ts_pct == expected_ts

    def test_player_snapshot_ts_pct_zero_attempts_returns_zero(
        self, player_snapshot_factory
    ):
        snapshot = player_snapshot_factory(pts=0, fga=0, fta=0)
        assert snapshot.ts_pct == 0.0

    def test_player_snapshot_all_stats_stored(self, player_snapshot_factory):
        snapshot = player_snapshot_factory(
            player_name="John Doe",
            pts=18,
            fgm=7,
            fga=14,
            tpm=2,
            tpa=5,
            ftm=2,
            fta=3,
            oreb=1,
            dreb=4,
            ast=3,
            stl=2,
            blk=1,
            tov=2,
            pf=3,
            plus_minus=8,
        )
        assert snapshot.player_name == "John Doe"
        assert snapshot.pts == 18
        assert snapshot.fgm == 7
        assert snapshot.fga == 14
        assert snapshot.tpm == 2
        assert snapshot.tpa == 5
        assert snapshot.ftm == 2
        assert snapshot.fta == 3
        assert snapshot.oreb == 1
        assert snapshot.dreb == 4
        assert snapshot.ast == 3
        assert snapshot.stl == 2
        assert snapshot.blk == 1
        assert snapshot.tov == 2
        assert snapshot.pf == 3
        assert snapshot.plus_minus == 8


# =============================================================================
# ScoringRun Tests
# =============================================================================


class TestScoringRun:
    """Tests for ScoringRun dataclass."""

    def test_scoring_run_valid_team_created(self):
        run = ScoringRun(
            team="team",
            points=10,
            start_seconds=120,
            end_seconds=180,
            start_quarter=1,
            end_quarter=1,
            lineup=["Player A", "Player B"],
        )
        assert run.team == "team"
        assert run.points == 10

    def test_scoring_run_valid_opp_created(self):
        run = ScoringRun(
            team="opp",
            points=8,
            start_seconds=240,
            end_seconds=300,
            start_quarter=2,
            end_quarter=2,
        )
        assert run.team == "opp"
        assert run.points == 8

    def test_scoring_run_invalid_team_raises_error(self):
        with pytest.raises(ValueError, match="team must be 'team' or 'opp'"):
            ScoringRun(
                team="invalid",
                points=5,
                start_seconds=0,
                end_seconds=60,
                start_quarter=1,
                end_quarter=1,
            )

    def test_scoring_run_default_empty_lineup(self):
        run = ScoringRun(
            team="team",
            points=5,
            start_seconds=0,
            end_seconds=60,
            start_quarter=1,
            end_quarter=1,
        )
        assert run.lineup == []


# =============================================================================
# QuarterSummary Tests
# =============================================================================


class TestQuarterSummary:
    """Tests for QuarterSummary dataclass."""

    def test_quarter_summary_margin_calculated(self):
        summary = QuarterSummary(
            quarter=1,
            team_pts=22,
            opp_pts=18,
            team_fgm=9,
            team_fga=18,
            team_tpm=2,
            team_tpa=5,
            team_ftm=2,
            team_fta=3,
            team_tov=3,
        )
        assert summary.margin == 4

    def test_quarter_summary_negative_margin(self):
        summary = QuarterSummary(
            quarter=2,
            team_pts=15,
            opp_pts=25,
            team_fgm=6,
            team_fga=15,
            team_tpm=1,
            team_tpa=4,
            team_ftm=2,
            team_fta=2,
            team_tov=4,
        )
        assert summary.margin == -10


# =============================================================================
# EvolutionReport Tests
# =============================================================================


class TestEvolutionReport:
    """Tests for EvolutionReport dataclass."""

    def test_evolution_report_valid_result_win_created(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
        )
        assert report.result == "W"

    def test_evolution_report_valid_result_loss_created(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=68,
            final_opp_score=75,
            result="L",
        )
        assert report.result == "L"

    def test_evolution_report_invalid_result_raises_error(self):
        with pytest.raises(ValueError, match="result must be 'W' or 'L'"):
            EvolutionReport(
                game_id=1,
                opponent="Test Opponent",
                date="17-02-2024",
                final_team_score=75,
                final_opp_score=68,
                result="T",
            )

    def test_evolution_report_final_margin_property(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
        )
        assert report.final_margin == 7

    def test_evolution_report_is_win_property_true(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
        )
        assert report.is_win is True

    def test_evolution_report_is_win_property_false(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=68,
            final_opp_score=75,
            result="L",
        )
        assert report.is_win is False

    def test_evolution_report_total_possessions_from_snapshots(
        self, team_snapshot_factory
    ):
        snapshots = [
            team_snapshot_factory(game_seconds=0, fga=10, fta=4, orb=2, tov=3),
            team_snapshot_factory(game_seconds=60, fga=20, fta=8, orb=4, tov=6),
            team_snapshot_factory(game_seconds=120, fga=30, fta=12, orb=6, tov=9),
        ]
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            team_snapshots=snapshots,
        )
        assert report.total_possessions == snapshots[-1].possessions

    def test_evolution_report_total_possessions_empty_snapshots_returns_zero(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            team_snapshots=[],
        )
        assert report.total_possessions == 0.0

    def test_evolution_report_quarters_played(self):
        summaries = {
            1: QuarterSummary(1, 20, 18, 8, 16, 2, 4, 2, 3, 3),
            2: QuarterSummary(2, 18, 20, 7, 14, 1, 3, 3, 4, 4),
            3: QuarterSummary(3, 22, 15, 9, 17, 2, 5, 2, 2, 2),
            4: QuarterSummary(4, 15, 15, 6, 12, 1, 3, 2, 3, 3),
        }
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            quarter_summaries=summaries,
        )
        assert report.quarters_played == 4

    def test_evolution_report_get_snapshot_at_time(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=60),
            team_snapshot_factory(game_seconds=120),
            team_snapshot_factory(game_seconds=180),
        ]
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            team_snapshots=snapshots,
        )
        result = report.get_snapshot_at_time(130)
        assert result.game_seconds == 120

    def test_evolution_report_get_snapshot_at_time_empty_returns_none(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            team_snapshots=[],
        )
        assert report.get_snapshot_at_time(60) is None

    def test_evolution_report_get_player_final_stats(self, player_snapshot_factory):
        player_snapshots = {
            "Player A": [
                player_snapshot_factory(player_name="Player A", game_seconds=60, pts=5),
                player_snapshot_factory(
                    player_name="Player A", game_seconds=120, pts=10
                ),
                player_snapshot_factory(
                    player_name="Player A", game_seconds=180, pts=18
                ),
            ]
        }
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            player_snapshots=player_snapshots,
        )
        final = report.get_player_final_stats("Player A")
        assert final.pts == 18

    def test_evolution_report_get_player_final_stats_not_found_returns_none(self):
        report = EvolutionReport(
            game_id=1,
            opponent="Test Opponent",
            date="17-02-2024",
            final_team_score=75,
            final_opp_score=68,
            result="W",
            player_snapshots={},
        )
        assert report.get_player_final_stats("Unknown Player") is None


# =============================================================================
# EvolutionReportService._process_events Tests
# =============================================================================


class TestProcessEvents:
    """Tests for EvolutionReportService._process_events method."""

    def test_process_events_empty_events_returns_empty_snapshots(self):
        team_snaps, player_snaps = EvolutionReportService._process_events([], 60)
        assert team_snaps == []
        assert player_snaps == {}

    def test_process_events_shot_2pt_made_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
                time_remaining="09:30",
            )
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert len(team_snaps) >= 1
        assert team_snaps[-1].team_score == 2
        assert team_snaps[-1].fgm == 1
        assert team_snaps[-1].fga == 1
        assert "Player A" in player_snaps
        assert player_snaps["Player A"][-1].pts == 2

    def test_process_events_shot_2pt_missed_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="missed",
                quarter=1,
                time_remaining="09:30",
            )
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].team_score == 0
        assert team_snaps[-1].fgm == 0
        assert team_snaps[-1].fga == 1
        assert player_snaps["Player A"][-1].pts == 0

    def test_process_events_shot_3pt_made_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SHOT_3PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
                time_remaining="09:30",
            )
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].team_score == 3
        assert team_snaps[-1].fgm == 1
        assert team_snaps[-1].fga == 1
        assert team_snaps[-1].tpm == 1
        assert team_snaps[-1].tpa == 1
        assert player_snaps["Player A"][-1].pts == 3

    def test_process_events_ft_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="FT",
                player_name="Player A",
                game_seconds=30,
                detail=json.dumps({"ftm": 2, "fta": 2}),
                quarter=1,
                time_remaining="09:30",
            )
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].team_score == 2
        assert team_snaps[-1].ftm == 2
        assert team_snaps[-1].fta == 2
        assert player_snaps["Player A"][-1].pts == 2

    def test_process_events_ft_made_missed_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="FT_MADE",
                player_name="Player A",
                game_seconds=30,
                quarter=1,
            ),
            game_event_factory(
                event_type="FT_MISS",
                player_name="Player A",
                game_seconds=35,
                quarter=1,
            ),
        ]
        team_snaps, _ = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].team_score == 1
        assert team_snaps[-1].ftm == 1
        assert team_snaps[-1].fta == 2

    def test_process_events_opp_score_updates_score(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="OPP_SCORE",
                player_name=None,
                game_seconds=30,
                detail=json.dumps({"points": 3}),
                quarter=1,
            )
        ]
        team_snaps, _ = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].opp_score == 3

    def test_process_events_turnover_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="TURNOVER",
                player_name="Player A",
                game_seconds=30,
                quarter=1,
            )
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].tov == 1
        assert player_snaps["Player A"][-1].tov == 1

    def test_process_events_rebounds_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="OREB", player_name="Player A", game_seconds=30
            ),
            game_event_factory(
                event_type="DREB", player_name="Player B", game_seconds=60
            ),
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].orb == 1
        assert team_snaps[-1].drb == 1
        assert player_snaps["Player A"][-1].oreb == 1
        assert player_snaps["Player B"][-1].dreb == 1

    def test_process_events_ast_stl_blk_updates_stats(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="AST", player_name="Player A", game_seconds=30
            ),
            game_event_factory(
                event_type="STL", player_name="Player B", game_seconds=60
            ),
            game_event_factory(
                event_type="BLK", player_name="Player C", game_seconds=90
            ),
        ]
        team_snaps, player_snaps = EvolutionReportService._process_events(events, 60)

        assert team_snaps[-1].ast == 1
        assert team_snaps[-1].stl == 1
        assert team_snaps[-1].blk == 1
        assert player_snaps["Player A"][-1].ast == 1
        assert player_snaps["Player B"][-1].stl == 1
        assert player_snaps["Player C"][-1].blk == 1

    def test_process_events_substitution_updates_lineup(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SUB_IN",
                player_name="Player A",
                game_seconds=30,
                quarter=1,
            ),
            game_event_factory(
                event_type="SUB_IN",
                player_name="Player B",
                game_seconds=35,
                quarter=1,
            ),
            game_event_factory(
                event_type="SUB_OUT",
                player_name="Player A",
                game_seconds=120,
                quarter=1,
            ),
        ]
        team_snaps, _ = EvolutionReportService._process_events(events, 60)

        assert "Player A" in team_snaps[0].lineup
        assert "Player B" in team_snaps[-1].lineup
        assert "Player A" not in team_snaps[-1].lineup

    def test_process_events_snapshot_interval_respected(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=90,
                shot_attempt="made",
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=150,
                shot_attempt="made",
            ),
        ]
        team_snaps, _ = EvolutionReportService._process_events(events, 60)

        assert len(team_snaps) >= 2

    def test_process_events_multiple_quarters(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                quarter=1,
                shot_attempt="made",
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=630,
                quarter=2,
                shot_attempt="made",
            ),
        ]
        team_snaps, _ = EvolutionReportService._process_events(events, 60)

        quarters_in_snaps = {s.quarter for s in team_snaps}
        assert 1 in quarters_in_snaps or 2 in quarters_in_snaps


# =============================================================================
# EvolutionReportService._calculate_quarter_summaries Tests
# =============================================================================


class TestCalculateQuarterSummaries:
    """Tests for EvolutionReportService._calculate_quarter_summaries method."""

    def test_calculate_quarter_summaries_empty_snapshots_returns_empty(self):
        summaries = EvolutionReportService._calculate_quarter_summaries([])
        assert summaries == {}

    def test_calculate_quarter_summaries_single_quarter(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(
                game_seconds=0,
                quarter=1,
                team_score=0,
                opp_score=0,
                fgm=0,
                fga=0,
                tpm=0,
                tpa=0,
                ftm=0,
                fta=0,
                tov=0,
            ),
            team_snapshot_factory(
                game_seconds=300,
                quarter=1,
                team_score=22,
                opp_score=18,
                fgm=9,
                fga=18,
                tpm=2,
                tpa=5,
                ftm=2,
                fta=3,
                tov=3,
            ),
        ]
        summaries = EvolutionReportService._calculate_quarter_summaries(snapshots)

        assert 1 in summaries
        assert summaries[1].team_pts == 22
        assert summaries[1].opp_pts == 18
        assert summaries[1].margin == 4

    def test_calculate_quarter_summaries_multiple_quarters(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(
                game_seconds=0,
                quarter=1,
                team_score=0,
                opp_score=0,
                fgm=0,
                fga=0,
                tpm=0,
                tpa=0,
                ftm=0,
                fta=0,
                tov=0,
            ),
            team_snapshot_factory(
                game_seconds=600,
                quarter=1,
                team_score=20,
                opp_score=18,
                fgm=8,
                fga=16,
                tpm=2,
                tpa=4,
                ftm=2,
                fta=3,
                tov=3,
            ),
            team_snapshot_factory(
                game_seconds=610,
                quarter=2,
                team_score=20,
                opp_score=18,
                fgm=8,
                fga=16,
                tpm=2,
                tpa=4,
                ftm=2,
                fta=3,
                tov=3,
            ),
            team_snapshot_factory(
                game_seconds=1200,
                quarter=2,
                team_score=40,
                opp_score=36,
                fgm=16,
                fga=32,
                tpm=4,
                tpa=8,
                ftm=4,
                fta=6,
                tov=6,
            ),
        ]
        summaries = EvolutionReportService._calculate_quarter_summaries(snapshots)

        assert len(summaries) == 2
        assert summaries[1].team_pts == 20
        assert summaries[2].team_pts == 20

    def test_calculate_quarter_summaries_counts_stats(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(
                game_seconds=0,
                quarter=1,
                team_score=0,
                opp_score=0,
                fgm=0,
                fga=0,
                tpm=0,
                tpa=0,
                ftm=0,
                fta=0,
                tov=0,
            ),
            team_snapshot_factory(
                game_seconds=600,
                quarter=1,
                team_score=22,
                opp_score=18,
                fgm=9,
                fga=18,
                tpm=2,
                tpa=5,
                ftm=2,
                fta=3,
                tov=3,
            ),
        ]
        summaries = EvolutionReportService._calculate_quarter_summaries(snapshots)

        assert summaries[1].team_fgm == 9
        assert summaries[1].team_fga == 18
        assert summaries[1].team_tpm == 2
        assert summaries[1].team_tpa == 5
        assert summaries[1].team_ftm == 2
        assert summaries[1].team_fta == 3
        assert summaries[1].team_tov == 3


# =============================================================================
# EvolutionReportService._detect_scoring_runs Tests
# =============================================================================


class TestDetectScoringRuns:
    """Tests for EvolutionReportService._detect_scoring_runs method."""

    def test_detect_scoring_runs_empty_snapshots_returns_empty(self):
        runs = EvolutionReportService._detect_scoring_runs([])
        assert runs == []

    def test_detect_scoring_runs_single_snapshot_returns_empty(
        self, team_snapshot_factory
    ):
        runs = EvolutionReportService._detect_scoring_runs([team_snapshot_factory()])
        assert runs == []

    def test_detect_scoring_runs_no_significant_run_returns_empty(
        self, team_snapshot_factory
    ):
        snapshots = [
            team_snapshot_factory(game_seconds=0, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, team_score=2, opp_score=2),
            team_snapshot_factory(game_seconds=120, team_score=4, opp_score=4),
        ]
        runs = EvolutionReportService._detect_scoring_runs(snapshots)
        assert runs == []

    def test_detect_scoring_runs_team_5_point_run_detected(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, quarter=1, team_score=0, opp_score=0),
            team_snapshot_factory(
                game_seconds=60, quarter=1, team_score=2, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=120, quarter=1, team_score=5, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=180, quarter=1, team_score=7, opp_score=0
            ),
        ]
        runs = EvolutionReportService._detect_scoring_runs(snapshots)

        assert len(runs) >= 1
        assert runs[0].team == "team"
        assert runs[0].points >= 5

    def test_detect_scoring_runs_opp_5_point_run_detected(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, quarter=1, team_score=0, opp_score=0),
            team_snapshot_factory(
                game_seconds=60, quarter=1, team_score=0, opp_score=2
            ),
            team_snapshot_factory(
                game_seconds=120, quarter=1, team_score=0, opp_score=5
            ),
            team_snapshot_factory(
                game_seconds=180, quarter=1, team_score=0, opp_score=7
            ),
        ]
        runs = EvolutionReportService._detect_scoring_runs(snapshots)

        assert len(runs) >= 1
        assert runs[0].team == "opp"
        assert runs[0].points >= 5

    def test_detect_scoring_runs_large_run_detected(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, quarter=1, team_score=0, opp_score=0),
            team_snapshot_factory(
                game_seconds=60, quarter=1, team_score=5, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=120, quarter=1, team_score=10, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=180, quarter=1, team_score=15, opp_score=0
            ),
        ]
        runs = EvolutionReportService._detect_scoring_runs(snapshots)

        assert len(runs) >= 1
        assert any(r.points >= 10 for r in runs if r.team == "team")

    def test_detect_scoring_runs_emits_one_entry_per_streak(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, quarter=1, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, quarter=1, team_score=5, opp_score=0),
            team_snapshot_factory(game_seconds=120, quarter=1, team_score=10, opp_score=0),
            team_snapshot_factory(game_seconds=180, quarter=1, team_score=12, opp_score=0),
            team_snapshot_factory(game_seconds=240, quarter=1, team_score=12, opp_score=2),
        ]

        runs = EvolutionReportService._detect_scoring_runs(snapshots)

        assert len(runs) == 1
        assert runs[0].team == "team"
        assert runs[0].points == 12
        assert runs[0].start_seconds == 0
        assert runs[0].end_seconds == 180

    def test_detect_scoring_runs_min_run_threshold(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, quarter=1, team_score=0, opp_score=0),
            team_snapshot_factory(
                game_seconds=60, quarter=1, team_score=4, opp_score=0
            ),
        ]
        runs = EvolutionReportService._detect_scoring_runs(snapshots, min_run=5)
        assert runs == []

        runs = EvolutionReportService._detect_scoring_runs(snapshots, min_run=3)
        assert len(runs) >= 1

    def test_detect_scoring_runs_cross_quarter_run(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(
                game_seconds=590, quarter=1, team_score=2, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=600, quarter=1, team_score=5, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=610, quarter=2, team_score=7, opp_score=0
            ),
            team_snapshot_factory(
                game_seconds=660, quarter=2, team_score=10, opp_score=0
            ),
        ]
        runs = EvolutionReportService._detect_scoring_runs(snapshots)

        assert any(r.start_quarter == 1 and r.end_quarter == 2 for r in runs)


# =============================================================================
# EvolutionReportService._calculate_key_moments Tests
# =============================================================================


class TestCalculateKeyMoments:
    """Tests for EvolutionReportService._calculate_key_moments method."""

    def test_calculate_key_moments_empty_snapshots_returns_zeros(self):
        max_lead, max_deficit, lead_changes = (
            EvolutionReportService._calculate_key_moments([])
        )
        assert max_lead == 0
        assert max_deficit == 0
        assert lead_changes == 0

    def test_calculate_key_moments_max_lead_found(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, team_score=10, opp_score=5),
            team_snapshot_factory(game_seconds=120, team_score=20, opp_score=18),
            team_snapshot_factory(game_seconds=180, team_score=25, opp_score=20),
        ]
        max_lead, _, _ = EvolutionReportService._calculate_key_moments(snapshots)
        assert max_lead == 5

    def test_calculate_key_moments_max_deficit_found(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, team_score=5, opp_score=15),
            team_snapshot_factory(game_seconds=120, team_score=10, opp_score=18),
        ]
        _, max_deficit, _ = EvolutionReportService._calculate_key_moments(snapshots)
        assert max_deficit == 8

    def test_calculate_key_moments_lead_changes_counted(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, team_score=5, opp_score=10),
            team_snapshot_factory(game_seconds=120, team_score=15, opp_score=10),
            team_snapshot_factory(game_seconds=180, team_score=15, opp_score=20),
            team_snapshot_factory(game_seconds=240, team_score=25, opp_score=20),
        ]
        _, _, lead_changes = EvolutionReportService._calculate_key_moments(snapshots)
        assert lead_changes == 2

    def test_calculate_key_moments_no_lead_changes(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, team_score=5, opp_score=3),
            team_snapshot_factory(game_seconds=120, team_score=10, opp_score=6),
            team_snapshot_factory(game_seconds=180, team_score=15, opp_score=10),
        ]
        _, _, lead_changes = EvolutionReportService._calculate_key_moments(snapshots)
        assert lead_changes == 0

    def test_calculate_key_moments_tied_game_no_changes(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, team_score=0, opp_score=0),
            team_snapshot_factory(game_seconds=60, team_score=10, opp_score=10),
            team_snapshot_factory(game_seconds=120, team_score=20, opp_score=20),
        ]
        _, _, lead_changes = EvolutionReportService._calculate_key_moments(snapshots)
        assert lead_changes == 0


# =============================================================================
# EvolutionReportService._calculate_clutch_time Tests
# =============================================================================


class TestCalculateClutchTime:
    """Tests for EvolutionReportService._calculate_clutch_time method."""

    def test_calculate_clutch_time_empty_snapshots_returns_none(self):
        result = EvolutionReportService._calculate_clutch_time([])
        assert result is None

    def test_calculate_clutch_time_no_q4_returns_none(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(game_seconds=0, quarter=1, team_score=0, opp_score=0),
            team_snapshot_factory(
                game_seconds=600, quarter=2, team_score=30, opp_score=28
            ),
            team_snapshot_factory(
                game_seconds=1200, quarter=3, team_score=50, opp_score=48
            ),
        ]
        result = EvolutionReportService._calculate_clutch_time(snapshots)
        assert result is None

    def test_calculate_clutch_time_large_margin_returns_none(
        self, team_snapshot_factory
    ):
        snapshots = [
            team_snapshot_factory(
                game_seconds=1800, quarter=4, team_score=70, opp_score=50
            ),
            team_snapshot_factory(
                game_seconds=1920, quarter=4, team_score=75, opp_score=52
            ),
            team_snapshot_factory(
                game_seconds=2040, quarter=4, team_score=80, opp_score=55
            ),
        ]
        result = EvolutionReportService._calculate_clutch_time(snapshots)
        assert result is None

    def test_calculate_clutch_time_close_game_returns_clutch_data(
        self, team_snapshot_factory
    ):
        snapshots = [
            team_snapshot_factory(
                game_seconds=1800,
                quarter=4,
                team_score=60,
                opp_score=58,
                fgm=24,
                fga=48,
                tov=8,
            ),
            team_snapshot_factory(
                game_seconds=1920,
                quarter=4,
                team_score=62,
                opp_score=60,
                fgm=25,
                fga=49,
                tov=8,
            ),
            team_snapshot_factory(
                game_seconds=2040,
                quarter=4,
                team_score=65,
                opp_score=62,
                fgm=26,
                fga=50,
                tov=9,
            ),
            team_snapshot_factory(
                game_seconds=2160,
                quarter=4,
                team_score=68,
                opp_score=66,
                fgm=27,
                fga=51,
                tov=9,
            ),
        ]
        result = EvolutionReportService._calculate_clutch_time(snapshots)

        assert result is not None
        assert "start_seconds" in result
        assert "start_margin" in result
        assert "end_margin" in result
        assert "team_pts_in_clutch" in result
        assert "opp_pts_in_clutch" in result
        assert "margin_change" in result

    def test_calculate_clutch_time_margin_within_five(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(
                game_seconds=1800, quarter=4, team_score=60, opp_score=58
            ),
            team_snapshot_factory(
                game_seconds=1860, quarter=4, team_score=61, opp_score=62
            ),
            team_snapshot_factory(
                game_seconds=1920, quarter=4, team_score=63, opp_score=63
            ),
        ]
        result = EvolutionReportService._calculate_clutch_time(snapshots)

        assert result is not None
        assert abs(result["start_margin"]) <= 5

    def test_calculate_clutch_time_overtime_included(self, team_snapshot_factory):
        snapshots = [
            team_snapshot_factory(
                game_seconds=2400, quarter=5, team_score=70, opp_score=70
            ),
            team_snapshot_factory(
                game_seconds=2460, quarter=5, team_score=72, opp_score=71
            ),
            team_snapshot_factory(
                game_seconds=2520, quarter=5, team_score=74, opp_score=73
            ),
        ]
        result = EvolutionReportService._calculate_clutch_time(snapshots)

        assert result is not None
        assert result["quarter"] == 5


# =============================================================================
# EvolutionReportService.build_report Integration Tests
# =============================================================================


class TestBuildReport:
    """Integration tests for EvolutionReportService.build_report method."""

    def _schema4_payload(self):
        return {
            "schema_version": 4,
            "game": {
                "date": "2026-03-01",
                "opponent": "Schema Four Opponent",
                "team_score": 5,
                "opponent_score": 0,
                "game_type": "Season",
            },
            "player_stats": [],
            "shot_locations": [
                {
                    "shooter": "Alice",
                    "type": "2pt",
                    "result": "made",
                    "points": 2,
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                    "x": 240,
                    "y": 90,
                },
                {
                    "shooter": "Bob",
                    "type": "3pt",
                    "result": "made",
                    "points": 3,
                    "quarter": 1,
                    "clockSeconds": 20,
                    "timestamp": 1020,
                    "x": 120,
                    "y": 340,
                },
            ],
            "game_events": [
                {
                    "type": "TURNOVER",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 0,
                    "timestamp": 1000,
                },
                {
                    "type": "SHOT_2PT",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                },
                {
                    "type": "SHOT_3PT",
                    "player": "Bob",
                    "quarter": 1,
                    "clockSeconds": 20,
                    "timestamp": 1020,
                },
            ],
            "starting_lineup": ["Alice", "Bob", "Carol", "Diana", "Eve"],
        }

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_game_not_found_raises_error(self, mock_fetch):
        mock_fetch.return_value = (None, [], [])

        with pytest.raises(ValueError, match="Game with id 999 not found"):
            EvolutionReportService.build_report(999)

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_creates_report_with_valid_data(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1, team_score=75, opponent_score=68)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="OPP_SCORE",
                player_name=None,
                game_seconds=60,
                detail=json.dumps({"points": 2}),
                quarter=1,
            ),
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert report.game_id == 1
        assert report.opponent == "Test Opponent"
        assert report.final_team_score == 75
        assert report.final_opp_score == 68
        assert report.result == "W"

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_loss_result(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1, team_score=68, opponent_score=75)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            )
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert report.result == "L"
        assert report.is_win is False

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_includes_team_snapshots(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_3PT",
                player_name="Player B",
                game_seconds=90,
                shot_attempt="made",
                quarter=1,
            ),
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert len(report.team_snapshots) >= 1

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_includes_quarter_summaries(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=630,
                shot_attempt="made",
                quarter=2,
            ),
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert isinstance(report.quarter_summaries, dict)

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_includes_key_moments(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="OPP_SCORE",
                player_name=None,
                game_seconds=60,
                detail=json.dumps({"points": 2}),
                quarter=1,
            ),
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert isinstance(report.max_lead, int)
        assert isinstance(report.max_deficit, int)
        assert isinstance(report.lead_changes, int)

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_includes_scoring_runs(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_3PT",
                player_name="Player B",
                game_seconds=60,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=90,
                shot_attempt="made",
                quarter=1,
            ),
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert isinstance(report.scoring_runs, list)

    @pytest.mark.integration
    def test_build_report_detects_schema4_scoring_runs_after_import(self, db_session):
        game = create_game_from_live_data(self._schema4_payload())

        report = EvolutionReportService.build_report(game.id, snapshot_interval=1)

        assert len(report.scoring_runs) == 1
        assert report.scoring_runs[0].team == "team"
        assert report.scoring_runs[0].points == 5

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_custom_snapshot_interval(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1)
        events = [
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=30,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=60,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=90,
                shot_attempt="made",
                quarter=1,
            ),
            game_event_factory(
                event_type="SHOT_2PT",
                player_name="Player A",
                game_seconds=120,
                shot_attempt="made",
                quarter=1,
            ),
        ]
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1, snapshot_interval=30)

        assert report.game_id == 1

    @patch.object(EvolutionReportService, "_fetch_game_data")
    def test_build_report_generated_at_timestamp(
        self, mock_fetch, game_factory, game_event_factory
    ):
        game = game_factory(id=1)
        events = []
        mock_fetch.return_value = (game, events, [])

        report = EvolutionReportService.build_report(1)

        assert report.generated_at is not None


class TestSchema4EvolutionReportService:
    """Integration tests for Schema4EvolutionReportService.build_report."""

    def _schema4_payload(self):
        return {
            "schema_version": 4,
            "game": {
                "date": "2026-03-01",
                "opponent": "Schema Four Opponent",
                "team_score": 7,
                "opponent_score": 2,
                "game_type": "Season",
            },
            "player_stats": [],
            "shot_locations": [
                {
                    "shooter": "Alice",
                    "type": "2pt",
                    "result": "made",
                    "points": 2,
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                    "x": 240,
                    "y": 90,
                },
                {
                    "shooter": "Bob",
                    "type": "3pt",
                    "result": "made",
                    "points": 3,
                    "quarter": 1,
                    "clockSeconds": 20,
                    "timestamp": 1020,
                    "x": 120,
                    "y": 340,
                },
            ],
            "game_events": [
                {
                    "type": "TURNOVER",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 0,
                    "timestamp": 1000,
                },
                {
                    "type": "SHOT_2PT",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                },
                {
                    "type": "OPP_SCORE",
                    "quarter": 1,
                    "clockSeconds": 15,
                    "timestamp": 1015,
                    "detail": {"points": 2},
                    "score_margin": 0,
                },
                {
                    "type": "FT",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 18,
                    "timestamp": 1018,
                    "detail": {"ftm": 2, "fta": 2},
                    "score_margin": 2,
                },
                {
                    "type": "SHOT_3PT",
                    "player": "Bob",
                    "quarter": 1,
                    "clockSeconds": 20,
                    "timestamp": 1020,
                    "score_margin": 5,
                },
            ],
            "starting_lineup": ["Alice", "Bob", "Carol", "Diana", "Eve"],
        }

    @pytest.mark.integration
    def test_build_report_uses_score_margin_as_timeline_truth(self, db_session):
        game = create_game_from_live_data(self._schema4_payload())

        mismatch = GameEvent.query.filter_by(game_id=game.id, event_type="SHOT_2PT").first()
        mismatch.score_margin = 0
        db_session.commit()

        report = Schema4EvolutionReportService.build_report(game.id)

        snapshot = next(
            snap
            for snap in report.team_snapshots
            if snap.game_seconds == 10 and snap.quarter == 1 and snap.team_score == 2
        )

        assert snapshot.opp_score == 2
        assert snapshot.margin == 0

    @pytest.mark.integration
    def test_build_report_reconstructs_opponent_score_from_margin(self, db_session):
        game = create_game_from_live_data(self._schema4_payload())

        report = Schema4EvolutionReportService.build_report(game.id)

        snapshot = next(
            snap
            for snap in report.team_snapshots
            if snap.game_seconds == 20 and snap.quarter == 1 and snap.team_score == 7
        )
        assert snapshot.opp_score == 2
        assert snapshot.margin == 5

    @pytest.mark.integration
    def test_build_report_stably_orders_events_with_same_game_seconds(self, db_session):
        game = Game(
            date="02-03-2026",
            opponent="Stable Sort Opponent",
            team_score=2,
            opponent_score=0,
            result="W",
            game_type="Season",
            sort_date="2026-03-02",
            source="IMPORT_JSON",
            schema_version=4,
        )
        db_session.add(game)
        db_session.flush()

        turnover = GameEvent(
            game_id=game.id,
            event_type="TURNOVER",
            player_name="Alice",
            quarter=1,
            game_seconds=10,
            time_remaining="9:50",
            timestamp=1000,
        )
        shot = GameEvent(
            game_id=game.id,
            event_type="SHOT_2PT",
            player_name="Alice",
            quarter=1,
            game_seconds=10,
            time_remaining="9:50",
            timestamp=1001,
            shot_attempt="made",
            score_margin=2,
        )
        db_session.add_all([turnover, shot])
        db_session.commit()

        report = Schema4EvolutionReportService.build_report(game.id)

        same_second_snaps = [
            snap for snap in report.team_snapshots if snap.game_seconds == 10
        ]
        assert same_second_snaps[0].team_score == 0
        assert same_second_snaps[1].team_score == 2

    @pytest.mark.integration
    def test_build_report_backfills_missing_game_seconds(self, db_session):
        game = Game(
            date="03-03-2026",
            opponent="Derived Timeline Opponent",
            team_score=2,
            opponent_score=0,
            result="W",
            game_type="Season",
            sort_date="2026-03-03",
            source="IMPORT_JSON",
            schema_version=4,
        )
        db_session.add(game)
        db_session.flush()

        db_session.add(
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Alice",
                quarter=1,
                timestamp=1000,
                shot_attempt="made",
                score_margin=2,
                time_remaining="9:50",
            )
        )
        db_session.commit()

        report = Schema4EvolutionReportService.build_report(game.id)

        derived_snapshot = next(
            snap for snap in report.team_snapshots if snap.game_seconds == 10
        )
        assert derived_snapshot.time_remaining == "9:50"

    @pytest.mark.integration
    def test_build_report_includes_quarter_boundary_diffs(self, db_session):
        game = Game(
            date="04-03-2026",
            opponent="Quarter Split Opponent",
            team_score=4,
            opponent_score=2,
            result="W",
            game_type="Season",
            sort_date="2026-03-04",
            source="IMPORT_JSON",
            schema_version=4,
        )
        db_session.add(game)
        db_session.flush()

        db_session.add_all(
            [
                GameEvent(
                    game_id=game.id,
                    event_type="SHOT_2PT",
                    player_name="Alice",
                    quarter=1,
                    game_seconds=590,
                    time_remaining="0:10",
                    timestamp=1000,
                    shot_attempt="made",
                    score_margin=2,
                ),
                GameEvent(
                    game_id=game.id,
                    event_type="OPP_SCORE",
                    quarter=2,
                    game_seconds=610,
                    time_remaining="9:50",
                    timestamp=1010,
                    detail=json.dumps({"points": 2}),
                    score_margin=0,
                ),
                GameEvent(
                    game_id=game.id,
                    event_type="SHOT_2PT",
                    player_name="Bob",
                    quarter=2,
                    game_seconds=620,
                    time_remaining="9:40",
                    timestamp=1020,
                    shot_attempt="made",
                    score_margin=2,
                ),
            ]
        )
        db_session.commit()

        report = Schema4EvolutionReportService.build_report(game.id)

        assert report.quarter_summaries[1].team_pts == 2
        assert report.quarter_summaries[1].opp_pts == 0
        assert report.quarter_summaries[2].team_pts == 2
        assert report.quarter_summaries[2].opp_pts == 2

    @pytest.mark.integration
    def test_build_report_detects_schema4_scoring_runs(self, db_session):
        game = create_game_from_live_data(self._schema4_payload())

        report = Schema4EvolutionReportService.build_report(game.id)

        assert len(report.scoring_runs) == 1
        assert report.scoring_runs[0].team == "team"
        assert report.scoring_runs[0].points == 5


# =============================================================================
# EvolutionReportService._get_lineup_at_time Tests
# =============================================================================


class TestGetLineupAtTime:
    """Tests for EvolutionReportService._get_lineup_at_time method."""

    def test_get_lineup_at_time_empty_events_returns_empty(self):
        lineup = EvolutionReportService._get_lineup_at_time([], 60)
        assert lineup == []

    def test_get_lineup_at_time_sub_in_adds_player(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SUB_IN", player_name="Player A", game_seconds=30
            ),
            game_event_factory(
                event_type="SUB_IN", player_name="Player B", game_seconds=60
            ),
        ]
        lineup = EvolutionReportService._get_lineup_at_time(events, 120)
        assert "Player A" in lineup
        assert "Player B" in lineup

    def test_get_lineup_at_time_sub_out_removes_player(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SUB_IN", player_name="Player A", game_seconds=30
            ),
            game_event_factory(
                event_type="SUB_IN", player_name="Player B", game_seconds=60
            ),
            game_event_factory(
                event_type="SUB_OUT", player_name="Player A", game_seconds=90
            ),
        ]
        lineup = EvolutionReportService._get_lineup_at_time(events, 120)
        assert "Player A" not in lineup
        assert "Player B" in lineup

    def test_get_lineup_at_time_stops_at_target_time(self, game_event_factory):
        events = [
            game_event_factory(
                event_type="SUB_IN", player_name="Player A", game_seconds=30
            ),
            game_event_factory(
                event_type="SUB_IN", player_name="Player B", game_seconds=60
            ),
            game_event_factory(
                event_type="SUB_IN", player_name="Player C", game_seconds=120
            ),
        ]
        lineup = EvolutionReportService._get_lineup_at_time(events, 90)
        assert "Player A" in lineup
        assert "Player B" in lineup
        assert "Player C" not in lineup
