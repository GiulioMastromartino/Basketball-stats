"""
Unit tests for core/services/game_service.py.

Tests the game creation and validation logic.
"""

import pytest
import json
from core.services.game_service import (
    validate_play_id,
    normalize_sort_date,
    get_nested_value,
    create_game_from_live_data,
)
from core.models import Game, PlayerStat, ShotEvent, GameEvent, Play, PlayType
from tests.factories import GameFactory, PlayFactory


# =============================================================================
# get_nested_value Tests
# =============================================================================

class TestGetNestedValue:
    """Tests for get_nested_value helper function."""
    
    @pytest.mark.unit
    def test_single_key_match(self):
        """Test finding value with first key."""
        data = {'name': 'John', 'player': 'Jane'}
        result = get_nested_value(data, 'name', 'player')
        assert result == 'John'
    
    @pytest.mark.unit
    def test_fallback_key_match(self):
        """Test finding value with fallback key."""
        data = {'player': 'Jane', 'username': 'Bob'}
        result = get_nested_value(data, 'name', 'player', 'username')
        assert result == 'Jane'
    
    @pytest.mark.unit
    def test_no_match_returns_default(self):
        """Test returning default when no key matches."""
        data = {'other': 'value'}
        result = get_nested_value(data, 'name', 'player', default='Unknown')
        assert result == 'Unknown'
    
    @pytest.mark.unit
    def test_none_value(self):
        """Test that None value is returned as valid."""
        data = {'name': None}
        result = get_nested_value(data, 'name', default='Default')
        assert result is None  # None is a valid value
    
    @pytest.mark.unit
    def test_empty_dict(self):
        """Test with empty dictionary."""
        result = get_nested_value({}, 'name', default='None')
        assert result == 'None'
    
    @pytest.mark.unit
    def test_nested_dict_access(self):
        """Test accessing nested dictionary."""
        data = {'game': {'date': '2024-02-17'}}
        result = get_nested_value(data, 'date')  # Should not find nested
        assert result is None


# =============================================================================
# normalize_sort_date Tests
# =============================================================================

class TestNormalizeSortDate:
    """Tests for normalize_sort_date function."""
    
    @pytest.mark.unit
    def test_yyyy_mm_dd_format(self):
        """Test YYYY-MM-DD format (already correct)."""
        result = normalize_sort_date('2024-02-17')
        assert result == '2024-02-17'
    
    @pytest.mark.unit
    def test_dd_mm_yyyy_format(self):
        """Test DD/MM/YYYY format conversion."""
        result = normalize_sort_date('17/02/2024')
        assert result == '2024-02-17'
    
    @pytest.mark.unit
    def test_dd_mm_yyyy_dashes(self):
        """Test DD-MM-YYYY format conversion."""
        result = normalize_sort_date('17-02-2024')
        assert result == '2024-02-17'
    
    @pytest.mark.unit
    def test_empty_string(self):
        """Test empty string returns empty."""
        result = normalize_sort_date('')
        assert result == ''
    
    @pytest.mark.unit
    def test_none_value(self):
        """Test None value."""
        result = normalize_sort_date(None)
        assert result == ''


# =============================================================================
# validate_play_id Tests
# =============================================================================

class TestValidatePlayId:
    """Tests for validate_play_id function."""
    
    @pytest.mark.unit
    def test_none_play_id(self):
        """Test validation with None."""
        result = validate_play_id(None)
        assert result is None


# =============================================================================
# create_game_from_live_data Tests
# =============================================================================

class TestCreateGameFromLiveData:
    """Tests for create_game_from_live_data function."""
    
    @pytest.mark.integration
    def test_basic_game_creation(self, db_session, live_game_payload):
        """Test basic game creation from live data."""
        game = create_game_from_live_data(live_game_payload)
        
        assert game is not None
        assert game.id is not None
        assert game.opponent == 'Test Team'
        assert game.team_score == 75
        assert game.opponent_score == 68
        assert game.result == 'W'
        assert game.source == 'LIVE'
    
    @pytest.mark.integration
    def test_player_stats_creation(self, db_session, live_game_payload):
        """Test player stats are created correctly."""
        game = create_game_from_live_data(live_game_payload)
        
        stats = PlayerStat.query.filter_by(game_id=game.id).all()
        assert len(stats) == 1
        assert stats[0].player_name == 'John Doe'
        assert stats[0].points == 18
        assert stats[0].fgm == 7
        assert stats[0].fga == 14
    
    @pytest.mark.integration
    def test_shot_events_creation(self, db_session, live_game_payload):
        """Test shot events are created correctly."""
        game = create_game_from_live_data(live_game_payload)
        
        shots = ShotEvent.query.filter_by(game_id=game.id).all()
        assert len(shots) == 1
        assert shots[0].player_name == 'John Doe'
        assert shots[0].shot_type == '2pt'
        assert shots[0].result == 'made'
    
    @pytest.mark.integration
    def test_game_events_creation(self, db_session, live_game_payload):
        """Test game events are created with timeline fields."""
        game = create_game_from_live_data(live_game_payload)
        
        events = GameEvent.query.filter_by(game_id=game.id).all()
        assert len(events) == 1
        assert events[0].event_type == 'SHOT_2PT'
        assert events[0].time_remaining == '8:30'
        assert events[0].score_margin == 2
        assert events[0].game_seconds == 90
        assert events[0].possession_number == 1
    
    @pytest.mark.integration
    def test_game_creation_invalid_play_id(self, db_session, live_game_payload):
        """Test game creation ignores invalid play IDs."""
        live_game_payload['shot_locations'][0]['play_id'] = 99999
        
        # Should not raise error, just skip invalid play_id
        game = create_game_from_live_data(live_game_payload)
        assert game is not None
        
        shots = ShotEvent.query.filter_by(game_id=game.id).all()
        assert shots[0].play_id is None
    
    @pytest.mark.integration
    def test_nested_import_format(self, db_session):
        """Test game creation with nested import format."""
        payload = {
            'game': {
                'date': '2024-02-17',
                'opponent': 'Import Team',
                'team_score': 80,
                'opponent_score': 70,
                'game_type': 'Tournament'
            },
            'player_stats': [
                {
                    'player_name': 'Player One',
                    'points': 20,
                    'fgm': 8,
                    'fga': 15,
                    'tpm': 2,
                    'tpa': 5,
                    'ftm': 2,
                    'fta': 3,
                    'oreb': 1,
                    'dreb': 4,
                    'ast': 3,
                    'stl': 2,
                    'blk': 1,
                    'tov': 2,
                    'pf': 3,
                    'minutes': '25:00'
                }
            ],
            'shot_events': [],
            'game_events': []
        }
        
        game = create_game_from_live_data(payload)
        
        assert game is not None
        assert game.source == 'IMPORT_JSON'
        assert game.opponent == 'Import Team'
    
    @pytest.mark.integration
    def test_empty_data_raises_error(self, db_session):
        """Test empty data raises ValueError."""
        with pytest.raises(ValueError, match="No data received"):
            create_game_from_live_data(None)
        
        with pytest.raises(ValueError, match="No data received"):
            create_game_from_live_data({})
    
    @pytest.mark.integration
    def test_ft_batch_event(self, db_session):
        """Test FT batch event creation."""
        payload = {
            'opponent': 'Team A',
            'team_score': 70,
            'opponent_score': 65,
            'date': '2024-02-17',
            'player_stats': {
                'FT Shooter': {'points': 2, 'fgm': 0, 'fga': 0, 'tpm': 0, 'tpa': 0, 'ftm': 2, 'fta': 3}
            },
            'game_events': [
                {
                    'type': 'FT',
                    'player': 'FT Shooter',
                    'detail': {'ftm': 2, 'fta': 3},
                    'quarter': 2,
                    'time_remaining': '5:30',
                    'score_margin': 5,
                    'game_seconds': 330,
                    'possession_number': 15,
                    'timestamp': 1708176000000
                }
            ]
        }
        
        game = create_game_from_live_data(payload)
        
        events = GameEvent.query.filter_by(game_id=game.id, event_type='FT').all()
        assert len(events) == 1
        
        # Check detail is stored as JSON
        detail = json.loads(events[0].detail) if events[0].detail else {}
        assert detail['ftm'] == 2
        assert detail['fta'] == 3
