"""
Unit tests for core/models.py.

Tests model validation, relationships, and methods.
"""

import pytest
from core.models import (
    User,
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    Play,
    PlayType,
    LineupSegment,
    Possession,
    ShotZone,
)
from web import db


# =============================================================================
# User Model Tests
# =============================================================================


class TestUserModel:
    """Tests for User model."""

    @pytest.mark.integration
    def test_user_creation(self, db_session):
        """Test basic user creation."""
        user = User(username="testuser", email="test@test.com", role="editor")
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()

        assert user.id is not None
        assert user.username == "testuser"
        assert user.email == "test@test.com"
        assert user.role == "editor"

    @pytest.mark.integration
    def test_password_hashing(self, db_session):
        """Test password is hashed, not stored in plain text."""
        user = User(username="testuser2", email="test2@test.com", role="editor")
        user.set_password("mypassword")
        db_session.add(user)
        db_session.commit()

        assert user.password_hash is not None
        assert user.password_hash != "mypassword"

    @pytest.mark.integration
    def test_password_verification(self, db_session):
        """Test password verification."""
        user = User(username="testuser3", email="test3@test.com", role="editor")
        user.set_password("mypassword")
        db_session.add(user)
        db_session.commit()

        assert user.check_password("mypassword") is True
        assert user.check_password("wrongpassword") is False

    @pytest.mark.integration
    def test_is_manager_property(self, db_session):
        """Test is_manager property for admin users."""
        admin = User(username="admin", email="admin@test.com", role="admin")
        admin.set_password("adminpass")
        editor = User(username="editor", email="editor@test.com", role="editor")
        editor.set_password("editorpass")
        db_session.add_all([admin, editor])
        db_session.commit()

        assert admin.is_manager is True
        assert editor.is_manager is False


# =============================================================================
# Game Model Tests
# =============================================================================


class TestGameModel:
    """Tests for Game model."""

    @pytest.mark.integration
    def test_game_creation(self, db_session):
        """Test basic game creation."""
        game = Game(
            date="17-02-2024",
            opponent="Test Opponents",
            team_score=75,
            opponent_score=68,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        assert game.id is not None
        assert game.opponent == "Test Opponents"
        assert game.team_score == 75
        assert game.opponent_score == 68
        assert game.result == "W"

    @pytest.mark.integration
    def test_game_source_types(self, db_session):
        """Test different game source types."""
        live_game = Game(
            date="01-01-2024",
            opponent="Team1",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-01-01",
            source="LIVE",
        )
        import_game = Game(
            date="02-01-2024",
            opponent="Team2",
            team_score=75,
            opponent_score=70,
            result="W",
            game_type="Season",
            sort_date="2024-01-02",
            source="IMPORT",
        )
        manual_game = Game(
            date="03-01-2024",
            opponent="Team3",
            team_score=80,
            opponent_score=75,
            result="W",
            game_type="Season",
            sort_date="2024-01-03",
            source="MANUAL",
        )

        db_session.add_all([live_game, import_game, manual_game])
        db_session.commit()

        assert live_game.source == "LIVE"
        assert import_game.source == "IMPORT"
        assert manual_game.source == "MANUAL"


# =============================================================================
# PlayerStat Model Tests
# =============================================================================


class TestPlayerStatModel:
    """Tests for PlayerStat model."""

    @pytest.mark.integration
    def test_player_stat_creation(self, db_session):
        """Test basic player stat creation."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        stat = PlayerStat(
            game_id=game.id, player_name="John Doe", points=18, fgm=7, fga=14
        )
        db_session.add(stat)
        db_session.commit()

        assert stat.id is not None
        assert stat.game_id == game.id
        assert stat.player_name == "John Doe"
        assert stat.points == 18


# =============================================================================
# ShotEvent Model Tests
# =============================================================================


class TestShotEventModel:
    """Tests for ShotEvent model."""

    @pytest.mark.integration
    def test_shot_event_creation(self, db_session):
        """Test basic shot event creation."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        shot = ShotEvent(
            game_id=game.id,
            player_name="Shooter",
            shot_type="3pt",
            result="made",
            points=3,
        )
        db_session.add(shot)
        db_session.commit()

        assert shot.id is not None
        assert shot.shot_type == "3pt"
        assert shot.result == "made"
        assert shot.points == 3

    @pytest.mark.integration
    def test_shot_event_coordinates(self, db_session):
        """Test shot event with coordinates."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        shot = ShotEvent(
            game_id=game.id,
            player_name="Shooter",
            shot_type="2pt",
            result="made",
            points=2,
            x_loc=250.0,
            y_loc=100.0,
        )
        db_session.add(shot)
        db_session.commit()

        assert shot.x_loc == 250.0
        assert shot.y_loc == 100.0


# =============================================================================
# GameEvent Model Tests
# =============================================================================


class TestGameEventModel:
    """Tests for GameEvent model."""

    @pytest.mark.integration
    def test_game_event_creation(self, db_session):
        """Test basic game event creation."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        event = GameEvent(game_id=game.id, event_type="SHOT_2PT", player_name="Player")
        db_session.add(event)
        db_session.commit()

        assert event.id is not None
        assert event.event_type == "SHOT_2PT"

    @pytest.mark.integration
    def test_game_event_timeline_fields(self, db_session):
        """Test timeline fields are stored."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        event = GameEvent(
            game_id=game.id,
            event_type="SHOT_2PT",
            quarter=2,
            time_remaining="5:30",
            score_margin=3,
            game_seconds=270,
            possession_number=15,
        )
        db_session.add(event)
        db_session.commit()

        assert event.quarter == 2
        assert event.time_remaining == "5:30"
        assert event.score_margin == 3
        assert event.game_seconds == 270
        assert event.possession_number == 15

    @pytest.mark.integration
    def test_game_event_substitution(self, db_session):
        """Test substitution event types."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        sub_in = GameEvent(game_id=game.id, event_type="SUB_IN", player_name="Player A")
        sub_out = GameEvent(
            game_id=game.id, event_type="SUB_OUT", player_name="Player B"
        )
        db_session.add_all([sub_in, sub_out])
        db_session.commit()

        assert sub_in.event_type == "SUB_IN"
        assert sub_out.event_type == "SUB_OUT"


# =============================================================================
# Play Model Tests
# =============================================================================


class TestPlayModel:
    """Tests for Play model."""

    @pytest.mark.integration
    def test_play_creation(self, db_session):
        """Test basic play creation."""
        play = Play(name="Horns PnR", play_type="Pick and Roll")
        db_session.add(play)
        db_session.commit()

        assert play.id is not None
        assert play.name == "Horns PnR"
        assert play.play_type == "Pick and Roll"


# =============================================================================
# LineupSegment Model Tests
# =============================================================================


class TestLineupSegmentModel:
    """Tests for LineupSegment model."""

    @pytest.mark.integration
    def test_lineup_segment_creation(self, db_session):
        """Test basic lineup segment creation."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        segment = LineupSegment(
            game_id=game.id,
            start_timestamp=0,
            end_timestamp=100,
            players=["P1", "P2", "P3", "P4", "P5"],
            quarter=1,
            lineup_hash="abc123",
        )
        db_session.add(segment)
        db_session.commit()

        assert segment.id is not None
        assert len(segment.players) == 5
        assert segment.quarter == 1


# =============================================================================
# Possession Model Tests
# =============================================================================


class TestPossessionModel:
    """Tests for Possession model."""

    @pytest.mark.integration
    def test_possession_creation(self, db_session):
        """Test basic possession creation."""
        game = Game(
            date="17-02-2024",
            opponent="Test",
            team_score=70,
            opponent_score=65,
            result="W",
            game_type="Season",
            sort_date="2024-02-17",
            source="MANUAL",
        )
        db_session.add(game)
        db_session.commit()

        event = GameEvent(game_id=game.id, event_type="SHOT_2PT")
        db_session.add(event)
        db_session.commit()

        possession = Possession(
            game_id=game.id,
            start_event_id=event.id,
            points=2,
            quarter=1,
            team_possession=True,
        )
        db_session.add(possession)
        db_session.commit()

        assert possession.id is not None
        assert possession.points == 2
        assert possession.team_possession is True


# =============================================================================
# ShotZone Model Tests
# =============================================================================


class TestShotZoneModel:
    """Tests for ShotZone model."""

    @pytest.mark.integration
    def test_shot_zone_creation(self, db_session):
        """Test shot zone creation."""
        zone = ShotZone(
            zone_name="Rim",
            zone_type="Rim",
            expected_value=1.25,
            x_min=200,
            x_max=300,
            y_min=0,
            y_max=100,
        )
        db_session.add(zone)
        db_session.commit()

        assert zone.id is not None
        assert zone.zone_name == "Rim"
        assert zone.expected_value == 1.25
