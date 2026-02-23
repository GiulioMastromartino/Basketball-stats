"""
Unit tests for core/advanced_analytics.py.

Tests shot zone classification, clutch detection, and lineup analytics.
"""

import pytest
from core.advanced_analytics import (
    classify_shot_zone,
    DEFAULT_ZONE_VALUES,
    ClutchPerformance,
    LineupAnalytics,
)


# =============================================================================
# Shot Zone Classification Tests
# =============================================================================

class TestClassifyShotZone:
    """Tests for classify_shot_zone function."""
    
    @pytest.mark.unit
    def test_rim_shot(self):
        """Test shot at the rim (near basket)."""
        # Basket is at (250, 50), rim shots should be close
        zone = classify_shot_zone(250, 60, '2pt')
        assert zone in ['Rim', 'Paint']
    
    @pytest.mark.unit
    def test_paint_shot(self):
        """Test shot in the paint area."""
        zone = classify_shot_zone(230, 120, '2pt')
        assert zone in ['Rim', 'Paint', 'Midrange']
    
    @pytest.mark.unit
    def test_corner_three(self):
        """Test corner 3-pointer classification."""
        zone = classify_shot_zone(50, 50, '3pt')
        assert zone in ['Corner_3', 'Above_Break_3']
    
    @pytest.mark.unit
    def test_above_break_three(self):
        """Test above-the-break 3-pointer classification."""
        zone = classify_shot_zone(250, 300, '3pt')
        assert zone in ['Above_Break_3', 'Corner_3']
    
    @pytest.mark.unit
    def test_midrange_shot(self):
        """Test midrange shot classification."""
        zone = classify_shot_zone(250, 200, '2pt')
        assert zone in ['Midrange', 'Paint', 'Rim']
    
    @pytest.mark.unit
    def test_free_throw(self):
        """Test free throw classification."""
        zone = classify_shot_zone(250, 190, 'ft')
        assert zone == 'FT'
    
    @pytest.mark.unit
    def test_edge_coordinates(self):
        """Test with edge coordinates (0,0, 500,470)."""
        # Should not crash with extreme coordinates
        zone = classify_shot_zone(0, 0, '2pt')
        assert zone is not None
        
        zone = classify_shot_zone(500, 470, '2pt')
        assert zone is not None
    
    @pytest.mark.unit
    def test_none_coordinates(self):
        """Test with None coordinates returns default."""
        zone = classify_shot_zone(None, None, '2pt')
        assert zone == 'Midrange'
    
    @pytest.mark.unit
    def test_empty_shot_type(self):
        """Test with empty shot type returns default."""
        zone = classify_shot_zone(250, 100, '')
        assert zone == 'Midrange'


# =============================================================================
# Default Zone Values Tests
# =============================================================================

class TestDefaultZoneValues:
    """Tests for DEFAULT_ZONE_VALUES."""
    
    @pytest.mark.unit
    def test_zone_values_exist(self):
        """Test all expected zones have default values."""
        assert 'Rim' in DEFAULT_ZONE_VALUES
        assert 'Paint' in DEFAULT_ZONE_VALUES
        assert 'Midrange' in DEFAULT_ZONE_VALUES
        assert 'Corner_3' in DEFAULT_ZONE_VALUES
        assert 'Above_Break_3' in DEFAULT_ZONE_VALUES
        assert 'FT' in DEFAULT_ZONE_VALUES
    
    @pytest.mark.unit
    def test_rim_highest_value(self):
        """Test rim has highest expected value."""
        assert DEFAULT_ZONE_VALUES['Rim'] > DEFAULT_ZONE_VALUES['Midrange']
        assert DEFAULT_ZONE_VALUES['Rim'] > DEFAULT_ZONE_VALUES['Paint']


# =============================================================================
# Clutch Performance Tests
# =============================================================================

class TestClutchPerformance:
    """Tests for ClutchPerformance class."""
    
    @pytest.mark.unit
    def test_is_clutch_situation_q4_close_game(self):
        """Test clutch situation in Q4 with close score."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=3, time_remaining_seconds=120
        )
        assert is_clutch is True
    
    @pytest.mark.unit
    def test_is_clutch_situation_q4_blowout(self):
        """Test not clutch in Q4 blowout."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=20, time_remaining_seconds=120
        )
        assert is_clutch is False
    
    @pytest.mark.unit
    def test_is_clutch_situation_early_game(self):
        """Test not clutch early (time > 5 min)."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=3, time_remaining_seconds=400
        )
        assert is_clutch is False
    
    @pytest.mark.unit
    def test_is_clutch_exact_margin_boundary(self):
        """Test clutch at exactly 5 points margin."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=5, time_remaining_seconds=120
        )
        assert is_clutch is True
    
    @pytest.mark.unit
    def test_is_clutch_margin_6(self):
        """Test not clutch at 6 points margin."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=6, time_remaining_seconds=120
        )
        assert is_clutch is False
    
    @pytest.mark.unit
    def test_is_clutch_time_boundary(self):
        """Test clutch at exactly 5 minutes (300 seconds)."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=3, time_remaining_seconds=300
        )
        assert is_clutch is True
    
    @pytest.mark.unit
    def test_is_clutch_time_301_seconds(self):
        """Test not clutch at 301 seconds."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=3, time_remaining_seconds=301
        )
        assert is_clutch is False
    
    @pytest.mark.unit
    def test_is_clutch_negative_margin(self):
        """Test clutch with negative margin (losing)."""
        is_clutch = ClutchPerformance.is_clutch_situation(
            score_margin=-3, time_remaining_seconds=120
        )
        assert is_clutch is True
    
    @pytest.mark.unit
    def test_clutch_constants(self):
        """Test clutch constants are defined."""
        assert ClutchPerformance.CLUTCH_MARGIN == 5
        assert ClutchPerformance.CLUTCH_TIME_SECONDS == 300


# =============================================================================
# Lineup Analytics Tests
# =============================================================================

class TestLineupAnalytics:
    """Tests for LineupAnalytics class."""
    
    @pytest.mark.unit
    def test_generate_lineup_hash(self):
        """Test lineup hash generation."""
        players = ['Player A', 'Player B', 'Player C', 'Player D', 'Player E']
        hash1 = LineupAnalytics.generate_lineup_hash(players)
        
        # Same players, different order should produce same hash
        players_reordered = ['Player E', 'Player D', 'Player C', 'Player B', 'Player A']
        hash2 = LineupAnalytics.generate_lineup_hash(players_reordered)
        
        assert hash1 == hash2
    
    @pytest.mark.unit
    def test_lineup_hash_different_lineups(self):
        """Test different lineups produce different hashes."""
        lineup1 = ['A', 'B', 'C', 'D', 'E']
        lineup2 = ['A', 'B', 'C', 'D', 'F']
        
        hash1 = LineupAnalytics.generate_lineup_hash(lineup1)
        hash2 = LineupAnalytics.generate_lineup_hash(lineup2)
        
        assert hash1 != hash2
    
    @pytest.mark.unit
    def test_lineup_hash_consistent_format(self):
        """Test hash is consistent format (hex string)."""
        players = ['P1', 'P2', 'P3', 'P4', 'P5']
        hash_result = LineupAnalytics.generate_lineup_hash(players)
        
        # Should be a string
        assert isinstance(hash_result, str)
        # Should be 32 characters (MD5 hex)
        assert len(hash_result) == 32
        # Should be hex characters only
        assert all(c in '0123456789abcdef' for c in hash_result.lower())


# =============================================================================
# Shot Zone Coordinate Tests
# =============================================================================

class TestShotZoneCoordinates:
    """Tests for shot zone coordinate boundaries."""
    
    @pytest.mark.unit
    def test_left_wing_three(self):
        """Test left wing 3-pointer."""
        zone = classify_shot_zone(100, 200, '3pt')
        assert zone in ['Corner_3', 'Above_Break_3']
    
    @pytest.mark.unit
    def test_right_wing_three(self):
        """Test right wing 3-pointer."""
        zone = classify_shot_zone(400, 200, '3pt')
        assert zone in ['Corner_3', 'Above_Break_3']
    
    @pytest.mark.unit
    def test_top_of_key(self):
        """Test top of key area."""
        zone = classify_shot_zone(250, 150, '2pt')
        assert zone in ['Paint', 'Midrange']
    
    @pytest.mark.unit
    def test_deep_three(self):
        """Test deep 3-pointer."""
        zone = classify_shot_zone(250, 400, '3pt')
        assert zone in ['Above_Break_3', 'Corner_3']


# =============================================================================
# Per-Game Lineup Rankings Tests
# =============================================================================


class TestGameLineupRankings:
    """Tests for LineupAnalytics.get_game_lineup_rankings() method."""
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_basic(self, db_session, sample_game, sample_game_events):
        """Test basic game lineup rankings retrieval."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        # Create lineup segments for the game
        players1 = ["John Doe", "Jane Smith", "Mike Johnson", "Tom Wilson", "Bob Brown"]
        segment1 = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=2000,
            quarter=1,
            players=players1,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players1),
            points_scored=10,
            points_allowed=6,
            possessions=8,
            duration_seconds=180,
        )
        db_session.add(segment1)
        
        # Different lineup (substitution)
        players2 = ["John Doe", "Jane Smith", "Mike Johnson", "Tom Wilson", "Sub Player"]
        segment2 = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=2000,
            end_timestamp=4000,
            quarter=1,
            players=players2,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players2),
            points_scored=5,
            points_allowed=4,
            possessions=5,
            duration_seconds=120,
        )
        db_session.add(segment2)
        db_session.commit()
        
        # Get rankings
        rankings = LineupAnalytics.get_game_lineup_rankings(sample_game.id, top_n=4)
        
        assert len(rankings) == 2
        # First should be the lineup with more minutes
        assert rankings[0]['total_seconds'] >= rankings[1]['total_seconds']
        # Check structure
        assert 'players' in rankings[0]
        assert 'total_minutes' in rankings[0]
        assert 'net_rating' in rankings[0]
        assert 'ortg' in rankings[0]
        assert 'drtg' in rankings[0]
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_aggregates_same_lineup(self, db_session, sample_game):
        """Test that multiple segments of same lineup are aggregated."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        # Same lineup plays in Q1 and Q3
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup_hash = LineupAnalytics.generate_lineup_hash(players)
        
        segment1 = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=1000,
            quarter=1,
            players=players,
            lineup_hash=lineup_hash,
            points_scored=8,
            points_allowed=6,
            possessions=6,
            duration_seconds=180,
        )
        segment2 = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=3000,
            end_timestamp=4000,
            quarter=3,
            players=players,
            lineup_hash=lineup_hash,
            points_scored=12,
            points_allowed=8,
            possessions=8,
            duration_seconds=240,
        )
        db_session.add_all([segment1, segment2])
        db_session.commit()
        
        rankings = LineupAnalytics.get_game_lineup_rankings(sample_game.id)
        
        # Should have 1 unique lineup
        assert len(rankings) == 1
        # Should aggregate stats
        assert rankings[0]['total_seconds'] == 420  # 180 + 240
        assert rankings[0]['points_scored'] == 20  # 8 + 12
        assert rankings[0]['segment_count'] == 2
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_ratings(self, db_session, sample_game):
        """Test offensive/defensive rating calculations."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=1000,
            quarter=1,
            players=players,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players),
            points_scored=20,
            points_allowed=10,
            possessions=10,
            duration_seconds=300,
        )
        db_session.add(segment)
        db_session.commit()
        
        rankings = LineupAnalytics.get_game_lineup_rankings(sample_game.id)
        
        assert len(rankings) == 1
        # ORTG = 20/10 * 100 = 200
        assert rankings[0]['ortg'] == 200.0
        # DRTG = 10/10 * 100 = 100
        assert rankings[0]['drtg'] == 100.0
        # Net = ORTG - DRTG = 100
        assert rankings[0]['net_rating'] == 100.0
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_top_n(self, db_session, sample_game):
        """Test that top_n parameter limits results."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        # Create 6 different lineups
        for i in range(6):
            players = [f"P{i}a", f"P{i}b", f"P{i}c", f"P{i}d", f"P{i}e"]
            segment = LineupSegment(
                game_id=sample_game.id,
                start_timestamp=i * 1000,
                end_timestamp=(i + 1) * 1000,
                quarter=1,
                players=players,
                lineup_hash=LineupAnalytics.generate_lineup_hash(players),
                points_scored=5,
                points_allowed=5,
                possessions=5,
                duration_seconds=60 * (i + 1),  # Different durations
            )
            db_session.add(segment)
        db_session.commit()
        
        # Request top 4
        rankings = LineupAnalytics.get_game_lineup_rankings(sample_game.id, top_n=4)
        
        assert len(rankings) == 4
        # Should be sorted by duration (descending)
        for i in range(len(rankings) - 1):
            assert rankings[i]['total_seconds'] >= rankings[i + 1]['total_seconds']
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_empty_game(self, db_session, sample_game):
        """Test with game that has no lineup segments."""
        from core.advanced_analytics import LineupAnalytics
        
        rankings = LineupAnalytics.get_game_lineup_rankings(sample_game.id)
        
        assert rankings == []
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_nonexistent_game(self, db_session):
        """Test with game ID that doesn't exist."""
        from core.advanced_analytics import LineupAnalytics
        
        rankings = LineupAnalytics.get_game_lineup_rankings(9999)
        
        assert rankings == []
    
    @pytest.mark.integration
    def test_get_game_lineup_rankings_zero_possessions(self, db_session, sample_game):
        """Test lineup with zero possessions (avoid division by zero)."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=1000,
            quarter=1,
            players=players,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players),
            points_scored=0,
            points_allowed=0,
            possessions=0,  # No possessions
            duration_seconds=60,
        )
        db_session.add(segment)
        db_session.commit()
        
        rankings = LineupAnalytics.get_game_lineup_rankings(sample_game.id)
        
        assert len(rankings) == 1
        # Should handle division by zero (possessions = 1 to avoid error)
        assert rankings[0]['ortg'] == 0.0
        assert rankings[0]['drtg'] == 0.0


# =============================================================================
# Game Lineup Rankings API Tests
# =============================================================================


class TestGameLineupRankingsAPI:
    """Tests for /api/advanced/lineup/game/<game_id>/rankings endpoint."""
    
    @pytest.mark.integration
    def test_api_get_game_lineup_rankings(self, auth_client, sample_game, sample_game_events):
        """Test API returns lineup rankings for a game."""
        from core.models import LineupSegment, db
        from core.advanced_analytics import LineupAnalytics
        
        # Create lineup segment
        players = ["John Doe", "Jane Smith", "Mike Johnson", "Tom Wilson", "Bob Brown"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=2000,
            quarter=1,
            players=players,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players),
            points_scored=10,
            points_allowed=6,
            possessions=8,
            duration_seconds=180,
        )
        db.session.add(segment)
        db.session.commit()
        
        response = auth_client.get(f'/api/advanced/lineup/game/{sample_game.id}/rankings')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['game_id'] == sample_game.id
        assert data['opponent'] == sample_game.opponent
        assert data['top_n'] == 4  # Default
        assert 'rankings' in data
        assert len(data['rankings']) >= 1
    
    @pytest.mark.integration
    def test_api_get_game_lineup_rankings_custom_top_n(self, auth_client, sample_game):
        """Test API with custom top_n parameter."""
        from core.models import LineupSegment, db
        from core.advanced_analytics import LineupAnalytics
        
        # Create multiple lineups
        for i in range(5):
            players = [f"P{i}a", f"P{i}b", f"P{i}c", f"P{i}d", f"P{i}e"]
            segment = LineupSegment(
                game_id=sample_game.id,
                start_timestamp=i * 1000,
                end_timestamp=(i + 1) * 1000,
                quarter=1,
                players=players,
                lineup_hash=LineupAnalytics.generate_lineup_hash(players),
                duration_seconds=60,
            )
            db.session.add(segment)
        db.session.commit()
        
        response = auth_client.get(f'/api/advanced/lineup/game/{sample_game.id}/rankings?top_n=2')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert data['top_n'] == 2
        assert len(data['rankings']) <= 2
    
    @pytest.mark.integration
    def test_api_get_game_lineup_rankings_nonexistent_game(self, auth_client):
        """Test API returns 404 for nonexistent game."""
        response = auth_client.get('/api/advanced/lineup/game/9999/rankings')
        
        assert response.status_code == 404
    
    @pytest.mark.integration
    def test_api_get_game_lineup_rankings_unauthenticated(self, client, sample_game):
        """Test API requires authentication."""
        response = client.get(f'/api/advanced/lineup/game/{sample_game.id}/rankings')
        
        # Should redirect to login or return 401
        assert response.status_code in [302, 401]
    
    @pytest.mark.integration
    def test_api_get_game_lineup_rankings_includes_game_info(self, auth_client, sample_game):
        """Test API response includes game metadata."""
        response = auth_client.get(f'/api/advanced/lineup/game/{sample_game.id}/rankings')
        
        assert response.status_code == 200
        data = response.get_json()
        
        assert 'opponent' in data
        assert 'date' in data
        assert 'team_score' in data
        assert 'opponent_score' in data
        assert 'result' in data
        assert data['opponent'] == sample_game.opponent
        assert data['team_score'] == sample_game.team_score


# =============================================================================
# Lineup Segment Duration Tests
# =============================================================================


class TestLineupSegmentDuration:
    """Tests for lineup segment duration calculation."""
    
    @pytest.mark.integration
    def test_segment_duration_field_exists(self, db_session, sample_game):
        """Test that duration_seconds field exists on LineupSegment."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=1000,
            quarter=1,
            players=players,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players),
            duration_seconds=300,
        )
        db_session.add(segment)
        db_session.commit()
        
        assert segment.duration_seconds == 300
    
    @pytest.mark.integration
    def test_segment_duration_default_zero(self, db_session, sample_game):
        """Test that duration_seconds defaults to 0."""
        from core.models import LineupSegment
        from core.advanced_analytics import LineupAnalytics
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=1000,
            quarter=1,
            players=players,
            lineup_hash=LineupAnalytics.generate_lineup_hash(players),
        )
        db_session.add(segment)
        db_session.commit()
        
        # Default should be 0
        assert segment.duration_seconds == 0


# =============================================================================
# Lineup Model Tests
# =============================================================================


class TestLineupModel:
    """Tests for the Lineup model."""
    
    @pytest.mark.integration
    def test_lineup_creation(self, db_session):
        """Test basic lineup creation."""
        from core.models import Lineup
        from core.services.lineup_service import generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup = Lineup(
            lineup_hash=generate_lineup_hash(players),
            players=sorted(players),
            is_starting=True
        )
        db_session.add(lineup)
        db_session.commit()
        
        assert lineup.id is not None
        assert len(lineup.players) == 5
        assert lineup.is_starting is True
        assert lineup.total_seconds == 0
    
    @pytest.mark.integration
    def test_lineup_hash_unique(self, db_session):
        """Test lineup_hash must be unique."""
        from core.models import Lineup
        from core.services.lineup_service import generate_lineup_hash
        from sqlalchemy.exc import IntegrityError
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup_hash = generate_lineup_hash(players)
        
        lineup1 = Lineup(lineup_hash=lineup_hash, players=sorted(players))
        db_session.add(lineup1)
        db_session.commit()
        
        lineup2 = Lineup(lineup_hash=lineup_hash, players=sorted(players))
        db_session.add(lineup2)
        
        with pytest.raises(IntegrityError):
            db_session.commit()
    
    @pytest.mark.integration
    def test_lineup_display_name(self, db_session):
        """Test lineup can have a custom display name."""
        from core.models import Lineup
        from core.services.lineup_service import generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup = Lineup(
            lineup_hash=generate_lineup_hash(players),
            players=sorted(players),
            display_name="Starting Five"
        )
        db_session.add(lineup)
        db_session.commit()
        
        assert lineup.display_name == "Starting Five"


# =============================================================================
# Lineups API Tests
# =============================================================================


class TestLineupsAPI:
    """Tests for the lineups API endpoints."""
    
    @pytest.mark.integration
    def test_api_get_all_lineups(self, auth_client, sample_game):
        """Test API returns all lineups."""
        from core.models import Lineup, db
        from core.services.lineup_service import generate_lineup_hash
        
        # Create test lineups
        for i in range(3):
            players = [f"P{i}a", f"P{i}b", f"P{i}c", f"P{i}d", f"P{i}e"]
            lineup = Lineup(
                lineup_hash=generate_lineup_hash(players),
                players=sorted(players),
                total_seconds=60 * (i + 1)
            )
            db.session.add(lineup)
        db.session.commit()
        
        response = auth_client.get('/api/advanced/lineups')
        
        assert response.status_code == 200
        data = response.get_json()
        assert 'lineups' in data
        assert len(data['lineups']) >= 3
    
    @pytest.mark.integration
    def test_api_get_lineup_card(self, auth_client, sample_game):
        """Test API returns single lineup card."""
        from core.models import Lineup, LineupSegment, db
        from core.services.lineup_service import generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup = Lineup(
            lineup_hash=generate_lineup_hash(players),
            players=sorted(players),
            total_seconds=180,
            total_possessions=10,
            points_scored=15,
            points_allowed=10,
            ortg=150.0,
            drtg=100.0,
            net_rating=50.0
        )
        db.session.add(lineup)
        db.session.commit()
        
        response = auth_client.get(f'/api/advanced/lineup/{lineup.id}')
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['lineup']['id'] == lineup.id
        assert data['stats']['total_minutes'] == 3.0
        assert data['stats']['net_rating'] == 50.0
    
    @pytest.mark.integration
    def test_api_get_lineup_card_not_found(self, auth_client):
        """Test API returns 404 for nonexistent lineup."""
        response = auth_client.get('/api/advanced/lineup/9999')
        
        assert response.status_code == 404
    
    @pytest.mark.integration
    def test_api_update_lineup_name(self, auth_client):
        """Test API can update lineup display name."""
        from core.models import Lineup, db
        from core.services.lineup_service import generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup = Lineup(
            lineup_hash=generate_lineup_hash(players),
            players=sorted(players)
        )
        db.session.add(lineup)
        db.session.commit()
        
        response = auth_client.put(
            f'/api/advanced/lineup/{lineup.id}',
            json={'display_name': 'Bench Mob'},
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert data['lineup']['display_name'] == 'Bench Mob'


# =============================================================================
# Conceded Rebounds Tests
# =============================================================================


class TestConcededRebounds:
    """Tests for reb_conceded tracking."""
    
    @pytest.mark.integration
    def test_reb_conceded_field_exists(self, db_session, sample_game):
        """Test reb_conceded field exists on PlayerStat."""
        from core.models import PlayerStat
        
        stat = PlayerStat(
            game_id=sample_game.id,
            player_name="Test Player",
            reb_conceded=3
        )
        db_session.add(stat)
        db_session.commit()
        
        assert stat.reb_conceded == 3
    
    @pytest.mark.integration
    def test_reb_conceded_in_player_lineup_stats(self, db_session, sample_game):
        """Test reb_conceded field exists on PlayerLineupStats."""
        from core.models import LineupSegment, PlayerLineupStats
        from core.services.lineup_service import generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=players,
            lineup_hash=generate_lineup_hash(players)
        )
        db_session.add(segment)
        db_session.commit()
        
        pls = PlayerLineupStats(
            lineup_segment_id=segment.id,
            player_name="P1",
            reb_conceded=2
        )
        db_session.add(pls)
        db_session.commit()
        
        assert pls.reb_conceded == 2
    
    @pytest.mark.integration
    def test_opponent_oreb_increments_reb_conceded(self, db_session, sample_game):
        """Test OPP_OREB events increment reb_conceded in player lineup stats."""
        from core.models import LineupSegment, PlayerLineupStats, GameEvent
        from core.services.lineup_service import populate_player_lineup_stats, generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=players,
            lineup_hash=generate_lineup_hash(players)
        )
        db_session.add(segment)
        db_session.commit()
        
        # Add OPP_OREB event
        event = GameEvent(
            game_id=sample_game.id,
            event_type="OPP_OREB",
            timestamp=50,
            quarter=1,
            lineup_segment_id=segment.id
        )
        db_session.add(event)
        db_session.commit()
        
        # Populate stats
        populate_player_lineup_stats(segment.id)
        
        # Check all players have reb_conceded = 1
        stats = PlayerLineupStats.query.filter_by(lineup_segment_id=segment.id).all()
        assert len(stats) == 5
        for s in stats:
            assert s.reb_conceded == 1


# =============================================================================
# Lineup Service Tests
# =============================================================================


class TestLineupService:
    """Tests for lineup_service functions."""
    
    @pytest.mark.integration
    def test_get_or_create_lineup_creates_new(self, db_session):
        """Test get_or_create_lineup creates a new lineup."""
        from core.models import Lineup
        from core.services.lineup_service import get_or_create_lineup
        
        players = ["A", "B", "C", "D", "E"]
        
        # Should create new lineup
        lineup = get_or_create_lineup(players, is_starting=True)
        db_session.commit()
        
        assert lineup is not None
        assert lineup.id is not None
        assert lineup.is_starting is True
        assert len(lineup.players) == 5
    
    @pytest.mark.integration
    def test_get_or_create_lineup_returns_existing(self, db_session):
        """Test get_or_create_lineup returns existing lineup for same players."""
        from core.models import Lineup
        from core.services.lineup_service import get_or_create_lineup, generate_lineup_hash
        
        players = ["A", "B", "C", "D", "E"]
        
        # Create first
        lineup1 = get_or_create_lineup(players)
        db_session.commit()
        
        # Get existing
        lineup2 = get_or_create_lineup(players)
        db_session.commit()
        
        assert lineup1.id == lineup2.id
    
    @pytest.mark.integration
    def test_update_lineup_cached_stats(self, db_session, sample_game):
        """Test update_lineup_cached_stats calculates correct values."""
        from core.models import Lineup, LineupSegment
        from core.services.lineup_service import update_lineup_cached_stats, generate_lineup_hash
        
        players = ["P1", "P2", "P3", "P4", "P5"]
        lineup = Lineup(
            lineup_hash=generate_lineup_hash(players),
            players=sorted(players)
        )
        db_session.add(lineup)
        db_session.commit()
        
        # Create segments for this lineup
        segment1 = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=players,
            lineup_hash=generate_lineup_hash(players),
            lineup_id=lineup.id,
            duration_seconds=120,
            points_scored=10,
            points_allowed=6,
            possessions=8
        )
        segment2 = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=200,
            end_timestamp=300,
            quarter=2,
            players=players,
            lineup_hash=generate_lineup_hash(players),
            lineup_id=lineup.id,
            duration_seconds=180,
            points_scored=15,
            points_allowed=12,
            possessions=10
        )
        db_session.add_all([segment1, segment2])
        db_session.commit()
        
        # Update cached stats
        update_lineup_cached_stats(lineup.id)
        
        # Refresh lineup
        db_session.refresh(lineup)
        
        assert lineup.total_seconds == 300
        assert lineup.points_scored == 25
        assert lineup.points_allowed == 18
        assert lineup.total_possessions == 18
        assert lineup.segment_count == 2
        # ORTG = 25/18 * 100 = 138.9
        assert lineup.ortg == 138.9
        # DRTG = 18/18 * 100 = 100.0
        assert lineup.drtg == 100.0
        # Net = 138.9 - 100 = 38.9
        assert lineup.net_rating == 38.9
