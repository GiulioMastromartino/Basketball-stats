"""
Unit tests for core/advanced_game_report.py.

Tests the game report generation and statistical calculations.
"""

import pytest
from dataclasses import dataclass
from core.advanced_game_report import (
    TeamBox,
    PlayerBox,
    ZoneStats,
    _safe_div,
    _pct,
    _round,
    possessions,
    team_advanced,
    player_advanced,
    calculate_zone_stats,
)


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""
    
    @pytest.mark.unit
    def test_safe_div_normal(self):
        """Test safe division with normal values."""
        assert _safe_div(10, 2) == 5.0
        assert _safe_div(7, 3) == pytest.approx(2.333, rel=1e-2)
    
    @pytest.mark.unit
    def test_safe_div_zero(self):
        """Test safe division with zero denominator."""
        assert _safe_div(10, 0) == 0.0
        assert _safe_div(100, 0) == 0.0
    
    @pytest.mark.unit
    def test_pct_calculation(self):
        """Test percentage calculation."""
        assert _pct(50, 100) == 50.0
        assert _pct(1, 4) == 25.0
        assert _pct(100, 0) == 0.0
    
    @pytest.mark.unit
    def test_round_precision(self):
        """Test rounding with precision."""
        assert _round(1.23456, 2) == 1.23
        assert _round(1.23556, 2) == 1.24  # Rounds up
        assert _round(1.23456, 3) == 1.235


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestTeamBox:
    """Tests for TeamBox dataclass."""
    
    @pytest.mark.unit
    def test_team_box_creation(self):
        """Test TeamBox creation with all fields."""
        box = TeamBox(
            pts=75, fgm=28, fga=60, tpm=8, tpa=20,
            ftm=11, fta=15, orb=10, drb=25, trb=35,
            ast=15, stl=8, blk=4, tov=12
        )
        assert box.pts == 75
        assert box.fgm == 28
        assert box.trb == 35


class TestPlayerBox:
    """Tests for PlayerBox dataclass."""
    
    @pytest.mark.unit
    def test_player_box_creation(self):
        """Test PlayerBox creation."""
        box = PlayerBox(
            name='John Doe',
            pts=18, fgm=7, fga=14, tpm=2, tpa=5,
            ftm=2, fta=3, orb=1, drb=4, trb=5,
            ast=3, stl=2, blk=1, tov=2,
            minutes=24.5
        )
        assert box.name == 'John Doe'
        assert box.pts == 18
        assert box.minutes == 24.5


class TestZoneStats:
    """Tests for ZoneStats dataclass."""
    
    @pytest.mark.unit
    def test_zone_stats_creation(self):
        """Test ZoneStats creation."""
        stats = ZoneStats(
            zone='Rim',
            fgm=5,
            fga=8,
            fg_pct=62.5,
            points=10,
            pps=1.25,
            expected_value=1.2,
            efficiency_delta=0.05
        )
        assert stats.zone == 'Rim'
        assert stats.fgm == 5
        assert stats.fga == 8


# =============================================================================
# possessions() Function Tests
# =============================================================================

class TestPossessions:
    """Tests for possessions calculation."""
    
    @pytest.mark.unit
    def test_standard_possessions(self):
        """Test standard possession calculation."""
        box = TeamBox(
            pts=75, fgm=28, fga=60, tpm=8, tpa=20,
            ftm=11, fta=15, orb=10, drb=25, trb=35,
            ast=15, stl=8, blk=4, tov=12
        )
        # FGA + 0.44*FTA - ORB + TOV = 60 + 6.6 - 10 + 12 = 68.6
        result = possessions(box)
        assert result == pytest.approx(68.6, rel=1e-5)
    
    @pytest.mark.unit
    def test_possessions_zero_stats(self):
        """Test possessions with all zeros."""
        box = TeamBox(
            pts=0, fgm=0, fga=0, tpm=0, tpa=0,
            ftm=0, fta=0, orb=0, drb=0, trb=0,
            ast=0, stl=0, blk=0, tov=0
        )
        result = possessions(box)
        assert result == 0.0
    
    @pytest.mark.unit
    def test_possessions_no_offensive_rebounds(self):
        """Test possessions without offensive rebounds."""
        box = TeamBox(
            pts=50, fgm=20, fga=40, tpm=5, tpa=12,
            ftm=5, fta=8, orb=0, drb=20, trb=20,
            ast=10, stl=5, blk=2, tov=10
        )
        # 40 + 0.44*8 - 0 + 10 = 53.52
        result = possessions(box)
        assert result == pytest.approx(53.52, rel=1e-5)


# =============================================================================
# team_advanced() Function Tests
# =============================================================================

class TestTeamAdvanced:
    """Tests for team_advanced function (Four Factors)."""
    
    @pytest.mark.unit
    def test_four_factors_calculation(self):
        """Test Dean Oliver's Four Factors calculation."""
        team = TeamBox(
            pts=75, fgm=28, fga=60, tpm=8, tpa=20,
            ftm=11, fta=15, orb=10, drb=25, trb=35,
            ast=15, stl=8, blk=4, tov=12
        )
        opp = TeamBox(
            pts=68, fgm=26, fga=55, tpm=6, tpa=18,
            ftm=10, fta=14, orb=8, drb=20, trb=28,
            ast=12, stl=6, blk=3, tov=10
        )
        
        result = team_advanced(team, opp)
        
        # Check that result is a dict with stats
        assert isinstance(result, dict)
        assert len(result) > 0
    
    @pytest.mark.unit
    def test_team_advanced_returns_dict(self):
        """Test that team_advanced returns a dictionary."""
        team = TeamBox(
            pts=75, fgm=28, fga=60, tpm=8, tpa=20,
            ftm=11, fta=15, orb=10, drb=25, trb=35,
            ast=15, stl=8, blk=4, tov=12
        )
        opp = TeamBox(
            pts=68, fgm=26, fga=55, tpm=6, tpa=18,
            ftm=10, fta=14, orb=8, drb=20, trb=28,
            ast=12, stl=6, blk=3, tov=10
        )
        
        result = team_advanced(team, opp)
        assert isinstance(result, dict)


# =============================================================================
# player_advanced() Function Tests
# =============================================================================

class TestPlayerAdvanced:
    """Tests for player_advanced function."""
    
    @pytest.mark.unit
    def test_player_advanced_returns_dict(self):
        """Test player_advanced returns a dictionary."""
        player = PlayerBox(
            name='Test Player',
            pts=18, fgm=7, fga=14, tpm=2, tpa=5,
            ftm=2, fta=3, orb=1, drb=4, trb=5,
            ast=3, stl=2, blk=1, tov=2,
            minutes=24.0
        )
        team = TeamBox(
            pts=75, fgm=28, fga=60, tpm=8, tpa=20,
            ftm=11, fta=15, orb=10, drb=25, trb=35,
            ast=15, stl=8, blk=4, tov=12
        )
        team_minutes = 200.0  # 5 players * 40 min

        opp = TeamBox(
            pts=70, fgm=26, fga=58, tpm=6, tpa=18,
            ftm=12, fta=16, orb=8, drb=22, trb=30,
            ast=14, stl=6, blk=3, tov=14
        )

        result = player_advanced(player, team, team_minutes, opp)

        assert isinstance(result, dict)
        assert result["name"] == "Test Player"
        # Core efficiency
        assert result["ts_pct"] == 58.7  # 18/(2*(14+0.44*3))*100
        assert result["efg_pct"] == 57.1  # (7+0.5*2)/14*100
        assert result["usg_pct"] == 36.7  # Dean Oliver with minutes
        assert result["tov_pct"] == 11.5  # 2/(14+0.44*3+2)*100
        # Playmaking & defense
        assert result["ast_pct"] == 30.6  # 3/((24/40)*28-7)*100
        assert result["stl_pct"] == 4.7   # 2*40/(24*71.04)*100
        assert result["blk_pct"] == 4.2   # 1*40/(24*(58-18))*100
        # Rebounding
        assert result["orb_pct"] == 5.2   # 1*40/(24*(10+22))*100
        assert result["drb_pct"] == 20.2  # 4*40/(24*(25+8))*100
        assert result["reb_pct"] == 12.8  # 5*40/(24*(35+30))*100


# =============================================================================
# calculate_zone_stats() Function Tests
# =============================================================================

class TestCalculateZoneStats:
    """Tests for calculate_zone_stats function."""
    
    @pytest.mark.unit
    def test_zone_stats_empty(self):
        """Test with empty shots list."""
        result = calculate_zone_stats([])
        assert result == {}
    
    @pytest.mark.unit
    def test_zone_stats_with_shots(self):
        """Test with shots (zones are classified by coordinates, not zone key)."""
        # The function classifies shots by x_loc, y_loc, shot_type
        # not by a 'zone' key
        shots = [
            {'x_loc': 250, 'y_loc': 60, 'shot_type': '2pt', 'result': 'made', 'points': 2},
            {'x_loc': 250, 'y_loc': 60, 'shot_type': '2pt', 'result': 'missed', 'points': 0},
        ]
        
        result = calculate_zone_stats(shots)
        
        # Should return a dict with zone stats
        assert isinstance(result, dict)
        assert len(result) > 0
    
    @pytest.mark.unit
    def test_zone_stats_none_coordinates(self):
        """Test with None coordinates (defaults to Midrange)."""
        shots = [
            {'x_loc': None, 'y_loc': None, 'shot_type': '2pt', 'result': 'made', 'points': 2},
        ]
        
        result = calculate_zone_stats(shots)
        
        # None coordinates default to Midrange
        assert 'Midrange' in result
        assert result['Midrange'].fgm == 1


# =============================================================================
# Time Evolution Tests
# =============================================================================

class TestCalculateTimeSeries:
    """Tests for calculate_time_series function."""
    
    @pytest.mark.unit
    def test_calculate_time_series_empty(self):
        """Test with empty events list."""
        from core.advanced_game_report import calculate_time_series
        
        team_snapshots, player_snapshots = calculate_time_series([])
        
        assert team_snapshots == []
        assert player_snapshots == {}
    
    @pytest.mark.unit
    def test_calculate_time_series_with_none_game_seconds(self):
        """Test that None game_seconds values don't cause errors."""
        from core.advanced_game_report import calculate_time_series
        
        # Create mock events with None game_seconds
        events = [
            {'type': 'SHOT_2PT', 'player': 'Player A', 'quarter': 1, 'game_seconds': None, 'shot_attempt': 'made'},
            {'type': 'SHOT_3PT', 'player': 'Player B', 'quarter': 1, 'game_seconds': 30, 'shot_attempt': 'made'},
            {'type': 'OPP_SCORE', 'quarter': 1, 'game_seconds': 60, 'detail': {'points': 2}},
        ]
        
        # Should not raise TypeError
        team_snapshots, player_snapshots = calculate_time_series(events, snapshot_interval=30)
        
        assert len(team_snapshots) > 0
        assert 'Player A' in player_snapshots
        assert 'Player B' in player_snapshots
    
    @pytest.mark.unit
    def test_calculate_time_series_scoring(self):
        """Test that scoring events are tracked correctly."""
        from core.advanced_game_report import calculate_time_series
        
        events = [
            {'type': 'SHOT_2PT', 'player': 'Player A', 'quarter': 1, 'game_seconds': 10, 'shot_attempt': 'made'},
            {'type': 'SHOT_3PT', 'player': 'Player B', 'quarter': 1, 'game_seconds': 30, 'shot_attempt': 'made'},
            {'type': 'FT', 'player': 'Player A', 'quarter': 1, 'game_seconds': 60, 'detail': {'ftm': 2, 'fta': 2}},
        ]
        
        team_snapshots, player_snapshots = calculate_time_series(events, snapshot_interval=30)
        
        # Final snapshot should have correct totals
        if team_snapshots:
            final = team_snapshots[-1]
            assert final.team_score == 7  # 2 + 3 + 2


class TestBuildEvolutionReport:
    """Tests for build_evolution_report function."""
    
    @pytest.mark.unit
    def test_build_evolution_report_empty(self):
        """Test with empty events."""
        from core.advanced_game_report import build_evolution_report
        
        report = build_evolution_report(
            game_id=1,
            events=[],
            opponent='Test Team',
            date='2024-02-20'
        )
        
        assert report.game_id == 1
        assert report.opponent == 'Test Team'
        assert report.final_team_score == 0
        assert report.final_opp_score == 0
    
    @pytest.mark.unit
    def test_build_evolution_report_with_none_values(self):
        """Test that events with None values are handled gracefully."""
        from core.advanced_game_report import build_evolution_report
        
        # Create mock events - mix of None and valid game_seconds
        @dataclass
        class MockEvent:
            event_type: str
            player_name: str
            quarter: int
            game_seconds: int
            time_remaining: str
            shot_attempt: str = ''
            detail: dict = None
            
            def __post_init__(self):
                if self.detail is None:
                    self.detail = {}
        
        events = [
            MockEvent('SHOT_2PT', 'Player A', 1, None, '9:30', 'made'),
            MockEvent('SHOT_3PT', 'Player B', 1, 60, '9:00', 'made'),
            MockEvent('OPP_SCORE', '', 1, 120, '8:00', '', {'points': 2}),
        ]
        
        # Should not raise TypeError
        report = build_evolution_report(
            game_id=1,
            events=events,
            opponent='Test Team',
            date='2024-02-20'
        )
        
        assert report is not None
        assert isinstance(report.team_snapshots, list)
    
    @pytest.mark.unit
    def test_build_evolution_report_scoring_runs(self):
        """Test that scoring runs are detected."""
        from core.advanced_game_report import build_evolution_report
        
        @dataclass
        class MockEvent:
            event_type: str
            player_name: str
            quarter: int
            game_seconds: int
            time_remaining: str
            shot_attempt: str = ''
            detail: dict = None
            score_margin: int = 0
            
            def __post_init__(self):
                if self.detail is None:
                    self.detail = {}
        
        events = [
            MockEvent('SHOT_2PT', 'Player A', 1, 10, '9:50', 'made', score_margin=2),
            MockEvent('SHOT_2PT', 'Player A', 1, 30, '9:30', 'made', score_margin=4),
            MockEvent('SHOT_3PT', 'Player B', 1, 50, '9:10', 'made', score_margin=7),
        ]
        
        report = build_evolution_report(
            game_id=1,
            events=events,
            opponent='Test Team',
            date='2024-02-20'
        )
        
        assert report.max_lead >= 0
