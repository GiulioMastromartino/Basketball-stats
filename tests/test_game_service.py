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
from core.models import (
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    Play,
    PlayType,
    LineupSegment,
)
from tests.factories import GameFactory, PlayFactory


# =============================================================================
# get_nested_value Tests
# =============================================================================


class TestGetNestedValue:
    """Tests for get_nested_value helper function."""

    @pytest.mark.unit
    def test_single_key_match(self):
        """Test finding value with first key."""
        data = {"name": "John", "player": "Jane"}
        result = get_nested_value(data, "name", "player")
        assert result == "John"

    @pytest.mark.unit
    def test_fallback_key_match(self):
        """Test finding value with fallback key."""
        data = {"player": "Jane", "username": "Bob"}
        result = get_nested_value(data, "name", "player", "username")
        assert result == "Jane"

    @pytest.mark.unit
    def test_no_match_returns_default(self):
        """Test returning default when no key matches."""
        data = {"other": "value"}
        result = get_nested_value(data, "name", "player", default="Unknown")
        assert result == "Unknown"

    @pytest.mark.unit
    def test_none_value(self):
        """Test that None value is returned as valid."""
        data = {"name": None}
        result = get_nested_value(data, "name", default="Default")
        assert result is None  # None is a valid value

    @pytest.mark.unit
    def test_empty_dict(self):
        """Test with empty dictionary."""
        result = get_nested_value({}, "name", default="None")
        assert result == "None"

    @pytest.mark.unit
    def test_nested_dict_access(self):
        """Test accessing nested dictionary."""
        data = {"game": {"date": "2024-02-17"}}
        result = get_nested_value(data, "date")  # Should not find nested
        assert result is None


# =============================================================================
# normalize_sort_date Tests
# =============================================================================


class TestNormalizeSortDate:
    """Tests for normalize_sort_date function."""

    @pytest.mark.unit
    def test_yyyy_mm_dd_format(self):
        """Test YYYY-MM-DD format (already correct)."""
        result = normalize_sort_date("2024-02-17")
        assert result == "2024-02-17"

    @pytest.mark.unit
    def test_dd_mm_yyyy_format(self):
        """Test DD/MM/YYYY format conversion."""
        result = normalize_sort_date("17/02/2024")
        assert result == "2024-02-17"

    @pytest.mark.unit
    def test_dd_mm_yyyy_dashes(self):
        """Test DD-MM-YYYY format conversion."""
        result = normalize_sort_date("17-02-2024")
        assert result == "2024-02-17"

    @pytest.mark.unit
    def test_empty_string(self):
        """Test empty string returns empty."""
        result = normalize_sort_date("")
        assert result == ""

    @pytest.mark.unit
    def test_none_value(self):
        """Test None value."""
        result = normalize_sort_date(None)
        assert result == ""


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
                    "result": "missed",
                    "points": 0,
                    "quarter": 1,
                    "clockSeconds": 40,
                    "timestamp": 1040,
                    "x": 80,
                    "y": 320,
                },
                {
                    "shooter": "Alice",
                    "type": "3pt",
                    "result": "made",
                    "points": 3,
                    "quarter": 1,
                    "clockSeconds": 50,
                    "timestamp": 1050,
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
                    "detail": {"play_name": "Horns"},
                },
                {
                    "type": "OPP_SCORE",
                    "quarter": 1,
                    "clockSeconds": 20,
                    "timestamp": 1020,
                    "time_remaining": "9:40",
                    "game_seconds": 20,
                    "score_margin": 0,
                    "detail": {"points": 2},
                },
                {
                    "type": "SHOT_3PT",
                    "player": "Bob",
                    "quarter": 1,
                    "clockSeconds": 40,
                    "timestamp": 1040,
                    "detail": {"play_name": "Delay"},
                },
                {
                    "type": "FT",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 45,
                    "timestamp": 1045,
                    "detail": {"ftm": 2, "fta": 2},
                },
                {
                    "type": "SHOT_3PT",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 50,
                    "timestamp": 1050,
                    "detail": {"play_name": "Delay"},
                },
            ],
            "starting_lineup": ["Alice", "Bob", "Carol", "Diana", "Eve"],
        }

    def _payload_with_top_level_plays(self):
        return {
            "schema_version": 3,
            "game": {
                "date": "2026-03-02",
                "opponent": "Play Sync Opponent",
                "team_score": 4,
                "opponent_score": 0,
                "game_type": "Season",
            },
            "plays": [
                {"id": 101, "name": "Horns Twist", "play_type": "Offense"},
                {"id": 202, "name": "Zone Matchup", "play_type": "Defense"},
            ],
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
                    "play_id": 101,
                }
            ],
            "game_events": [
                {
                    "type": "SHOT_2PT",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                    "play_id": 101,
                },
                {
                    "type": "TURNOVER",
                    "player": "Alice",
                    "quarter": 1,
                    "clockSeconds": 20,
                    "timestamp": 1020,
                    "play_id": 101,
                },
            ],
            "starting_lineup": ["Alice", "Bob", "Carol", "Diana", "Eve"],
        }

    def _rescue_like_payload(self):
        return {
            "schema_version": 3,
            "exported_at": "2026-03-20T10:00:00",
            "game": {
                "date": "2026-03-03",
                "opponent": "Rescue Opponent",
                "team_score": 2,
                "opponent_score": 0,
                "game_type": "Season",
                "source": "RESCUE",
            },
            "player_stats": {},
            "shot_locations": [
                {
                    "shooter": "Alice",
                    "type": "2pt",
                    "result": "made",
                    "points": 2,
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                    "play_id": 77,
                }
            ],
            "game_events": [
                {
                    "type": "SHOT_2PT",
                    "player": "Alice",
                    "detail": {"play_id": 77, "play_name": "Flash"},
                    "quarter": 1,
                    "clockSeconds": 10,
                    "timestamp": 1010,
                    "play_id": 77,
                }
            ],
            "starting_lineup": ["Alice", "Bob", "Carol", "Diana", "Eve"],
            "lineup_history": [],
        }

    @pytest.mark.integration
    def test_basic_game_creation(self, db_session, live_game_payload):
        """Test basic game creation from live data."""
        game = create_game_from_live_data(live_game_payload)

        assert game is not None
        assert game.id is not None
        assert game.opponent == "Test Team"
        assert game.team_score == 75
        assert game.opponent_score == 68
        assert game.result == "W"
        assert game.source == "LIVE"

    @pytest.mark.integration
    def test_player_stats_creation(self, db_session, live_game_payload):
        """Test player stats are created correctly."""
        game = create_game_from_live_data(live_game_payload)

        stats = PlayerStat.query.filter_by(game_id=game.id).all()
        assert len(stats) == 1
        assert stats[0].player_name == "John Doe"
        assert stats[0].points == 18
        assert stats[0].fgm == 7
        assert stats[0].fga == 14

    @pytest.mark.integration
    def test_shot_events_creation(self, db_session, live_game_payload):
        """Test shot events are created correctly."""
        game = create_game_from_live_data(live_game_payload)

        shots = ShotEvent.query.filter_by(game_id=game.id).all()
        assert len(shots) == 1
        assert shots[0].player_name == "John Doe"
        assert shots[0].shot_type == "2pt"
        assert shots[0].result == "made"

    @pytest.mark.integration
    def test_game_events_creation(self, db_session, live_game_payload):
        """Test game events are created with timeline fields."""
        game = create_game_from_live_data(live_game_payload)

        events = GameEvent.query.filter_by(game_id=game.id).all()
        assert len(events) == 1
        assert events[0].event_type == "SHOT_2PT"
        assert events[0].time_remaining == "8:30"
        assert events[0].score_margin == 2
        assert events[0].game_seconds == 90
        assert events[0].possession_number == 1

    @pytest.mark.integration
    def test_game_creation_invalid_play_id(self, db_session, live_game_payload):
        """Test game creation ignores invalid play IDs."""
        live_game_payload["shot_locations"][0]["play_id"] = 99999

        # Should not raise error, just skip invalid play_id
        game = create_game_from_live_data(live_game_payload)
        assert game is not None

        shots = ShotEvent.query.filter_by(game_id=game.id).all()
        assert shots[0].play_id is None

    @pytest.mark.integration
    def test_nested_import_format(self, db_session):
        """Test game creation with nested import format."""
        payload = {
            "game": {
                "date": "2024-02-17",
                "opponent": "Import Team",
                "team_score": 80,
                "opponent_score": 70,
                "game_type": "Tournament",
            },
            "player_stats": [
                {
                    "player_name": "Player One",
                    "points": 20,
                    "fgm": 8,
                    "fga": 15,
                    "tpm": 2,
                    "tpa": 5,
                    "ftm": 2,
                    "fta": 3,
                    "oreb": 1,
                    "dreb": 4,
                    "ast": 3,
                    "stl": 2,
                    "blk": 1,
                    "tov": 2,
                    "pf": 3,
                    "minutes": "25:00",
                }
            ],
            "shot_events": [],
            "game_events": [],
        }

        game = create_game_from_live_data(payload)

        assert game is not None
        assert game.source == "IMPORT_JSON"
        assert game.opponent == "Import Team"

    @pytest.mark.integration
    def test_schema4_reconciles_shot_attempt_and_timeline_fields(self, db_session):
        """Schema 4 imports should hydrate shot outcomes and derived timeline fields."""
        game = create_game_from_live_data(self._schema4_payload())

        events = (
            GameEvent.query.filter_by(game_id=game.id)
            .order_by(GameEvent.timestamp.asc())
            .all()
        )

        assert events[1].event_type == "SHOT_2PT"
        assert events[1].shot_attempt == "made"
        assert events[1].game_seconds == 10
        assert events[1].time_remaining == "9:50"
        assert events[1].score_margin == 2

        assert events[3].event_type == "SHOT_3PT"
        assert events[3].shot_attempt == "missed"
        assert events[3].game_seconds == 40
        assert events[3].time_remaining == "9:20"

        assert events[5].event_type == "SHOT_3PT"
        assert events[5].shot_attempt == "made"
        assert events[5].score_margin == 5

    @pytest.mark.integration
    def test_schema4_imported_events_reconstruct_team_score(self, db_session):
        """Schema 4 imports should preserve event-based team scoring totals."""
        game = create_game_from_live_data(self._schema4_payload())

        events = (
            GameEvent.query.filter_by(game_id=game.id)
            .order_by(GameEvent.timestamp.asc())
            .all()
        )

        reconstructed = 0
        for event in events:
            if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
                reconstructed += 2
            elif event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
                reconstructed += 3
            elif event.event_type == "FT":
                reconstructed += json.loads(event.detail)["ftm"]

        assert reconstructed == game.team_score

    @pytest.mark.integration
    def test_schema4_backfills_play_ids_using_unique_timeline_match(self, db_session):
        """Play backfill should match the correct shot when a player takes multiple shots in a quarter."""
        payload = self._schema4_payload()
        payload["shot_locations"] = [
            {
                "shooter": "Alice",
                "type": "2pt",
                "result": "missed",
                "points": 0,
                "quarter": 1,
                "clockSeconds": 12,
                "timestamp": 1012,
                "x": 240,
                "y": 90,
            },
            {
                "shooter": "Alice",
                "type": "2pt",
                "result": "made",
                "points": 2,
                "quarter": 1,
                "clockSeconds": 18,
                "timestamp": 1018,
                "x": 242,
                "y": 92,
            },
        ]
        payload["game_events"] = [
            {
                "type": "SHOT_2PT",
                "player": "Alice",
                "quarter": 1,
                "clockSeconds": 18,
                "timestamp": 1018,
                "detail": {"play_name": "Horns"},
            }
        ]
        payload["team_score"] = 2
        payload["opponent_score"] = 0

        game = create_game_from_live_data(payload)
        horns = Play.query.filter_by(name="Horns").first()
        shots = ShotEvent.query.filter_by(game_id=game.id).order_by(ShotEvent.id.asc()).all()

        assert shots[0].play_id is None
        assert shots[1].play_id == horns.id

    @pytest.mark.integration
    def test_schema4_backfill_leaves_ambiguous_shots_untagged(self, db_session):
        """Backfill should not guess when multiple raw shots match the same event key."""
        payload = self._schema4_payload()
        payload["shot_locations"] = [
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
                "shooter": "Alice",
                "type": "2pt",
                "result": "made",
                "points": 2,
                "quarter": 1,
                "clockSeconds": 10,
                "timestamp": 1010,
                "x": 241,
                "y": 91,
            },
        ]
        payload["game_events"] = [
            {
                "type": "SHOT_2PT",
                "player": "Alice",
                "quarter": 1,
                "clockSeconds": 10,
                "timestamp": 1010,
                "detail": {"play_name": "Horns"},
            }
        ]
        payload["team_score"] = 2
        payload["opponent_score"] = 0

        game = create_game_from_live_data(payload)
        shots = ShotEvent.query.filter_by(game_id=game.id).all()

        assert all(shot.play_id is None for shot in shots)

    @pytest.mark.integration
    def test_import_syncs_top_level_plays_before_event_processing(self, db_session):
        """Importer should create payload plays even before events reference them."""
        payload = self._payload_with_top_level_plays()

        game = create_game_from_live_data(payload)
        synced_play = Play.query.filter_by(name="Horns Twist").first()
        defense_play = Play.query.filter_by(name="Zone Matchup").first()
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        events = GameEvent.query.filter_by(game_id=game.id).order_by(GameEvent.timestamp.asc()).all()

        assert synced_play is not None
        assert synced_play.play_type == "Offense"
        assert defense_play is not None
        assert defense_play.play_type == "Defense"
        assert shot.play_id == synced_play.id
        assert all(event.play_id == synced_play.id for event in events)

    @pytest.mark.integration
    def test_import_sync_reuses_existing_play_name_and_remaps_payload_id(self, db_session, default_team):
        """Payload play ids should map to an existing DB play when the name already exists."""
        existing = Play(name="Horns Twist", play_type="Offense", description="Existing", team_id=default_team.id)
        db_session.add(existing)
        db_session.commit()

        payload = self._payload_with_top_level_plays()
        game = create_game_from_live_data(payload)

        plays = Play.query.filter_by(name="Horns Twist").all()
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        events = GameEvent.query.filter_by(game_id=game.id).all()

        assert len(plays) == 1
        assert shot.play_id == existing.id
        assert all(event.play_id == existing.id for event in events)

    @pytest.mark.integration
    def test_import_without_top_level_plays_still_creates_referenced_play(self, db_session):
        """Legacy fallback creation should still work when payload omits the plays list."""
        payload = self._schema4_payload()

        game = create_game_from_live_data(payload)
        horns = Play.query.filter_by(name="Horns").first()
        delay = Play.query.filter_by(name="Delay").first()
        shots = ShotEvent.query.filter_by(game_id=game.id).all()

        assert horns is not None
        assert delay is not None
        assert any(shot.play_id == horns.id for shot in shots)

    @pytest.mark.integration
    def test_import_syncs_rescue_embedded_play_refs_without_top_level_list(self, db_session):
        """Rescue payloads should synthesize plays from embedded shot/event play refs."""
        payload = self._rescue_like_payload()

        game = create_game_from_live_data(payload)
        flash_play = Play.query.filter_by(name="Flash").first()
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        event = GameEvent.query.filter_by(game_id=game.id).first()

        assert flash_play is not None
        assert shot.play_id == flash_play.id
        assert event.play_id == flash_play.id

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
            "opponent": "Team A",
            "team_score": 70,
            "opponent_score": 65,
            "date": "2024-02-17",
            "player_stats": {
                "FT Shooter": {
                    "points": 2,
                    "fgm": 0,
                    "fga": 0,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 3,
                }
            },
            "game_events": [
                {
                    "type": "FT",
                    "player": "FT Shooter",
                    "detail": {"ftm": 2, "fta": 3},
                    "quarter": 2,
                    "time_remaining": "5:30",
                    "score_margin": 5,
                    "game_seconds": 330,
                    "possession_number": 15,
                    "timestamp": 1708176000000,
                }
            ],
        }

        game = create_game_from_live_data(payload)

        events = GameEvent.query.filter_by(game_id=game.id, event_type="FT").all()
        assert len(events) == 1

        # Check detail is stored as JSON
        detail = json.loads(events[0].detail) if events[0].detail else {}
        assert detail["ftm"] == 2
        assert detail["fta"] == 3


# =============================================================================
# Lineup Processing Integration Tests
# =============================================================================


class TestCreateGameFromLiveDataLineups:
    """Tests for lineup processing during game creation."""

    @pytest.mark.integration
    def test_processes_lineups_with_schema_version_2(self, db_session):
        """Lineups processed when schema_version >= 2."""
        from core.models import LineupSegment, GameEvent

        payload = {
            "opponent": "Lineup Test Team",
            "team_score": 85,
            "opponent_score": 78,
            "date": "2024-02-17",
            "schema_version": 2,
            "starting_lineup": ["P1", "P2", "P3", "P4", "P5"],
            "player_stats": {
                "P1": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 8,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
                "P2": {
                    "points": 8,
                    "fgm": 3,
                    "fga": 6,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
                "P3": {
                    "points": 12,
                    "fgm": 5,
                    "fga": 10,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 3,
                },
                "P4": {
                    "points": 6,
                    "fgm": 3,
                    "fga": 5,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                },
                "P5": {
                    "points": 4,
                    "fgm": 2,
                    "fga": 4,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                },
            },
            "game_events": [
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "P1",
                    "timestamp": 1000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "P2",
                    "timestamp": 2000,
                    "quarter": 1,
                    "shot_attempt": "missed",
                },
                {
                    "event_type": "SUB_OUT",
                    "player_name": "P5",
                    "timestamp": 10000,
                    "quarter": 1,
                },
                {
                    "event_type": "SUB_IN",
                    "player_name": "P6",
                    "timestamp": 10001,
                    "quarter": 1,
                },
            ],
        }

        game = create_game_from_live_data(payload)

        # Verify lineups were processed
        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert len(segments) >= 1, (
            "Lineup segments should be created with schema_version=2"
        )

        # First segment should have starting lineup
        assert segments[0].players == ["P1", "P2", "P3", "P4", "P5"]

    @pytest.mark.integration
    def test_processes_lineups_with_feature_flag(self, db_session):
        """Lineups processed when features.LINEUP_TRACKING = true."""
        from core.models import LineupSegment

        payload = {
            "opponent": "Feature Flag Team",
            "team_score": 70,
            "opponent_score": 65,
            "date": "2024-02-17",
            "schema_version": 1,  # Old version
            "features": {"LINEUP_TRACKING": True},  # But feature flag enabled
            "starting_lineup": ["A", "B", "C", "D", "E"],
            "player_stats": {
                "A": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 8,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
                "B": {
                    "points": 8,
                    "fgm": 3,
                    "fga": 6,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
                "C": {
                    "points": 12,
                    "fgm": 5,
                    "fga": 10,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 3,
                },
                "D": {
                    "points": 6,
                    "fgm": 3,
                    "fga": 5,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                },
                "E": {
                    "points": 4,
                    "fgm": 2,
                    "fga": 4,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                },
            },
            "game_events": [
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "A",
                    "timestamp": 1000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
            ],
        }

        game = create_game_from_live_data(payload)

        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert len(segments) >= 1, (
            "Lineup segments should be created with LINEUP_TRACKING=true"
        )

    @pytest.mark.integration
    def test_skips_lineups_without_flag(self, db_session):
        """Lineups skipped when no flag and no lineup data provided."""
        from core.models import LineupSegment

        payload = {
            "opponent": "No Lineup Team",
            "team_score": 60,
            "opponent_score": 55,
            "date": "2024-02-17",
            "schema_version": 1,  # Old version
            # No features flag
            # No starting_lineup
            "player_stats": {
                "Player1": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 8,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
            },
            "game_events": [
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "Player1",
                    "timestamp": 1000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
                # Has sub events but shouldn't trigger lineup processing
                {
                    "event_type": "SUB_OUT",
                    "player_name": "Player1",
                    "timestamp": 5000,
                    "quarter": 1,
                },
                {
                    "event_type": "SUB_IN",
                    "player_name": "Player2",
                    "timestamp": 5001,
                    "quarter": 1,
                },
            ],
        }

        game = create_game_from_live_data(payload)

        # Lineups should NOT be processed (no flag, old schema)
        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert len(segments) == 0, "Lineup segments should NOT be created without flag"

    @pytest.mark.integration
    def test_passes_starting_lineup_to_processor(self, db_session):
        """starting_lineup from payload is passed to lineup processor."""
        from core.models import LineupSegment

        payload = {
            "opponent": "Starting Lineup Team",
            "team_score": 80,
            "opponent_score": 75,
            "date": "2024-02-17",
            "schema_version": 2,
            "starting_lineup": [
                "Starter1",
                "Starter2",
                "Starter3",
                "Starter4",
                "Starter5",
            ],
            "player_stats": {
                "Starter1": {
                    "points": 15,
                    "fgm": 6,
                    "fga": 12,
                    "tpm": 1,
                    "tpa": 3,
                    "ftm": 2,
                    "fta": 2,
                },
                "Starter2": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 8,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
                "Starter3": {
                    "points": 8,
                    "fgm": 3,
                    "fga": 6,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 3,
                },
                "Starter4": {
                    "points": 6,
                    "fgm": 3,
                    "fga": 5,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                },
                "Starter5": {
                    "points": 4,
                    "fgm": 2,
                    "fga": 4,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 0,
                    "fta": 0,
                },
            },
            "game_events": [
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "Starter1",
                    "timestamp": 1000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
            ],
        }

        game = create_game_from_live_data(payload)

        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert len(segments) >= 1

        # Verify the starting lineup was used
        assert "Starter1" in segments[0].players
        assert "Starter2" in segments[0].players
        assert "Starter3" in segments[0].players
        assert "Starter4" in segments[0].players
        assert "Starter5" in segments[0].players

    @pytest.mark.integration
    def test_handles_lineup_processing_failure_gracefully(self, db_session):
        """Game still saved even if lineup processing fails."""
        payload = {
            "opponent": "Error Test Team",
            "team_score": 65,
            "opponent_score": 60,
            "date": "2024-02-17",
            "schema_version": 2,
            "starting_lineup": ["P1", "P2", "P3", "P4", "P5"],
            "player_stats": {
                "P1": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 8,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                },
            },
            "game_events": [
                # Valid events
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "P1",
                    "timestamp": 1000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
            ],
        }

        # Should not raise error even if lineup processing has issues
        game = create_game_from_live_data(payload)

        # Game should still be created
        assert game is not None
        assert game.opponent == "Error Test Team"
