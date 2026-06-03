"""
Integration tests for live game routes.

Tests the live game tracking and save functionality.
"""

import pytest
import json
from tests.factories import GameFactory, UserFactory


class TestLiveGameRoutes:
    """Tests for live game routes."""

    @pytest.mark.integration
    def test_live_game_page_loads(self, auth_client):
        """Test live game page loads successfully."""
        response = auth_client.get("/live-game")
        assert response.status_code == 200
        assert b"Live Game" in response.data or b"live" in response.data.lower()

    @pytest.mark.integration
    def test_live_game_save_basic(self, auth_client, live_game_payload):
        """Test basic live game save."""
        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        data = json.loads(response.data)
        assert data.get("success", True) is True

    @pytest.mark.integration
    def test_live_game_save_creates_game(
        self, auth_client, live_game_payload, db_session
    ):
        """Test live game save creates game in database."""
        from core.models import Game

        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]

        # Verify game created
        game = Game.query.filter_by(opponent="Test Team").first()
        assert game is not None
        assert game.team_score == 75
        assert game.opponent_score == 68

    @pytest.mark.integration
    def test_live_game_save_creates_player_stats(
        self, auth_client, live_game_payload, db_session
    ):
        """Test live game save creates player stats."""
        from core.models import PlayerStat, Game

        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        game = Game.query.filter_by(opponent="Test Team").first()
        stats = PlayerStat.query.filter_by(game_id=game.id).all()

        assert len(stats) == 1
        assert stats[0].player_name == "John Doe"
        assert stats[0].points == 18

    @pytest.mark.integration
    def test_live_game_save_creates_shot_events(
        self, auth_client, live_game_payload, db_session
    ):
        """Test live game save creates shot events."""
        from core.models import ShotEvent, Game

        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        game = Game.query.filter_by(opponent="Test Team").first()
        shots = ShotEvent.query.filter_by(game_id=game.id).all()

        assert len(shots) == 1
        assert shots[0].player_name == "John Doe"

    @pytest.mark.integration
    def test_live_game_save_creates_game_events(
        self, auth_client, live_game_payload, db_session
    ):
        """Test live game save creates game events with timeline fields."""
        from core.models import GameEvent, Game

        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        game = Game.query.filter_by(opponent="Test Team").first()
        events = GameEvent.query.filter_by(game_id=game.id).all()

        assert len(events) == 1
        assert events[0].time_remaining == "8:30"
        assert events[0].score_margin == 2

    @pytest.mark.integration
    def test_live_game_save_unauthorized(self, client):
        """Test live game save requires authentication."""
        response = client.post(
            "/live-game/save",
            json={"opponent": "Test"},
            content_type="application/json",
        )

        # Should redirect to login or return 401
        assert response.status_code in [302, 401]

    @pytest.mark.integration
    def test_live_game_save_empty_data(self, auth_client):
        """Test live game save with empty data."""
        response = auth_client.post(
            "/live-game/save", json={}, content_type="application/json"
        )

        # Should return error
        assert response.status_code in [400, 500]


class TestMainRoutes:
    """Tests for main application routes."""

    @pytest.mark.integration
    def test_dashboard_requires_auth(self, client):
        """Test dashboard requires authentication."""
        response = client.get("/")
        assert response.status_code in [302, 401]

    @pytest.mark.integration
    def test_dashboard_loads(self, auth_client):
        """Test dashboard loads for authenticated user."""
        response = auth_client.get("/")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_game_detail_page(self, auth_client, sample_game):
        """Test game detail page loads."""
        response = auth_client.get(f"/game/{sample_game.id}")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_game_detail_not_found(self, auth_client):
        """Test game detail for non-existent game."""
        response = auth_client.get("/game/99999")
        assert response.status_code == 404

    @pytest.mark.integration
    def test_player_detail_page(self, auth_client, sample_player_stat):
        """Test player detail page loads."""
        response = auth_client.get(f"/player/{sample_player_stat.player_name}")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_games_list_page(self, auth_client, sample_games):
        """Test games list page loads with games."""
        response = auth_client.get("/games-list")
        assert response.status_code == 200


class TestAuthRoutes:
    """Tests for authentication routes."""

    @pytest.mark.integration
    def test_login_page_loads(self, client):
        """Test login page loads."""
        response = client.get("/auth/login")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_login_success(self, client, editor_user):
        """Test successful login."""
        response = client.post(
            "/auth/login",
            data={"username": "test_editor", "password": "password123"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Welcome back" in response.data or b"test_editor" in response.data

    @pytest.mark.integration
    def test_login_invalid_credentials(self, client, editor_user):
        """Test login with invalid credentials."""
        response = client.post(
            "/auth/login", data={"username": "test_editor", "password": "wrongpassword"}
        )

        assert response.status_code == 200
        assert b"Invalid" in response.data or b"invalid" in response.data.lower()

    @pytest.mark.integration
    def test_logout(self, auth_client):
        """Test logout."""
        response = auth_client.get("/auth/logout", follow_redirects=True)

        assert response.status_code == 200

    @pytest.mark.integration
    def test_admin_login_otp_required(self, client, admin_user, mock_email_send):
        """Test admin login requires OTP verification."""
        response = client.post(
            "/auth/login",
            data={"username": "test_admin", "password": "admin123"},
            follow_redirects=False,
        )

        # Should redirect to OTP verification
        assert "/verify-otp" in response.location or response.status_code == 302


class TestAdminRoutes:
    """Tests for admin-only routes."""

    @pytest.mark.integration
    def test_users_list_admin(self, admin_client, editor_user):
        """Test admin can access users list."""
        response = admin_client.get("/auth/users")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_users_list_editor_denied(self, auth_client):
        """Test editor cannot access users list."""
        response = auth_client.get("/auth/users")
        assert response.status_code in [403, 302]

    @pytest.mark.integration
    def test_game_delete_admin(self, admin_client, sample_game):
        """Test admin can delete game."""
        response = admin_client.post(
            f"/game/{sample_game.id}/delete", follow_redirects=True
        )

        assert response.status_code == 200

    @pytest.mark.integration
    def test_game_delete_editor_denied(self, auth_client, sample_game):
        """Test editor cannot delete game."""
        response = auth_client.post(f"/game/{sample_game.id}/delete")

        assert response.status_code in [403, 302]
