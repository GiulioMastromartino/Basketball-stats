"""
Unit tests for multi-server support and automatic sync functionality.

Tests config parsing, peer health check endpoints, and sync coordination
endpoints for the multi-server / automatic sync feature.
"""

import json
import os
from unittest.mock import MagicMock, patch

from web import create_app
from core.models import User, Organization, Team, OrganizationMembership
from config import Config


class TestMultiServerConfig:
    """Tests for multi-server configuration parsing."""

    def test_default_server_urls_empty(self):
        """SERVER_URLS defaults to an empty list when not set."""
        config = Config()
        assert config.SERVER_URLS == []

    def test_sync_disabled_by_default(self):
        """SYNC_ENABLED defaults to False."""
        config = Config()
        assert config.SYNC_ENABLED is False

    def test_sync_interval_default(self):
        """SYNC_INTERVAL defaults to 300 seconds."""
        config = Config()
        assert config.SYNC_INTERVAL == 300

    def test_sync_timeout_default(self):
        """SYNC_TIMEOUT defaults to 10 seconds."""
        config = Config()
        assert config.SYNC_TIMEOUT == 10

    def test_server_urls_parsed_from_env(self):
        """SERVER_URLS env var is split into a list of URLs."""
        os.environ["SERVER_URLS"] = "http://server1:8080, http://server2:8080"
        try:
            config = Config()
            assert config.SERVER_URLS == [
                "http://server1:8080",
                "http://server2:8080",
            ]
        finally:
            del os.environ["SERVER_URLS"]

    def test_sync_enabled_from_env(self):
        """SYNC_ENABLED env var is parsed as a boolean."""
        os.environ["SYNC_ENABLED"] = "true"
        try:
            config = Config()
            assert config.SYNC_ENABLED is True
        finally:
            del os.environ["SYNC_ENABLED"]

    def test_sync_interval_from_env(self):
        """SYNC_INTERVAL env var is parsed as an int."""
        os.environ["SYNC_INTERVAL"] = "600"
        try:
            config = Config()
            assert config.SYNC_INTERVAL == 600
        finally:
            del os.environ["SYNC_INTERVAL"]

    def test_sync_timeout_from_env(self):
        """SYNC_TIMEOUT env var is parsed as an int."""
        os.environ["SYNC_TIMEOUT"] = "15"
        try:
            config = Config()
            assert config.SYNC_TIMEOUT == 15
        finally:
            del os.environ["SYNC_TIMEOUT"]

    def test_server_urls_strips_whitespace(self):
        """SERVER_URLS values are stripped of surrounding whitespace."""
        os.environ["SERVER_URLS"] = "  http://server1:8080 ,  http://server2:8080  "
        try:
            config = Config()
            assert config.SERVER_URLS == [
                "http://server1:8080",
                "http://server2:8080",
            ]
        finally:
            del os.environ["SERVER_URLS"]

    def test_empty_entries_ignored(self):
        """Empty entries in SERVER_URLS are ignored."""
        os.environ["SERVER_URLS"] = ",http://server1:8080,,,"
        try:
            config = Config()
            assert config.SERVER_URLS == ["http://server1:8080"]
        finally:
            del os.environ["SERVER_URLS"]


class TestPeerHealthEndpoints:
    """Tests for peer server health check endpoints."""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        org = Organization(name="Test Org", slug="test-org")
        self.app.app_context().push()
        from web import db

        db.create_all()
        db.session.add(org)
        db.session.flush()
        team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(team)
        db.session.flush()
        self.team_id = team.id

        user = User(
            username="sync_test_user", email="sync@example.com", organization_id=org.id
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        membership = OrganizationMembership(
            user_id=user.id, organization_id=org.id, is_gm=False
        )
        db.session.add(membership)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["current_team_id"] = team.id

        self.client.post(
            "/auth/login",
            data={"username": "sync_test_user", "password": "password"},
            follow_redirects=True,
        )

    def tearDown(self):
        from web import db

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_health_peers_no_configured_servers(self):
        """GET /health/peers returns empty results when no servers configured."""
        response = self.client.get("/health/peers")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert data["total"] == 0
        assert data["healthy"] == 0
        assert data["servers"] == []

    @patch("web.routes.health.httpx.Client")
    def test_health_peers_all_healthy(self, mock_client_cls):
        """GET /health/peers reports healthy status for reachable peers."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        os.environ["SERVER_URLS"] = "http://server1:8080,http://server2:8080"
        try:
            response = self.client.get("/health/peers")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "healthy"
            assert data["total"] == 2
            assert data["healthy"] == 2
            assert len(data["servers"]) == 2
        finally:
            del os.environ["SERVER_URLS"]

    @patch("web.routes.health.httpx.Client")
    def test_health_peers_some_unreachable(self, mock_client_cls):
        """GET /health/peers reports degraded status when some peers unreachable."""

        class MockClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args, **kwargs):
                pass

            def get(self, url):
                if "server1" in url:
                    resp = MagicMock()
                    resp.status_code = 200
                    return resp
                raise Exception("Connection refused")

        mock_client_cls.return_value = MockClient()

        os.environ["SERVER_URLS"] = "http://server1:8080,http://server2:8080"
        try:
            response = self.client.get("/health/peers")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "degraded"
            assert data["total"] == 2
            assert data["healthy"] == 1
        finally:
            del os.environ["SERVER_URLS"]

    @patch("web.routes.health.httpx.Client")
    def test_health_peer_single_reachable(self, mock_client_cls):
        """GET /health/peers/<url> returns healthy for a reachable peer."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        os.environ["SERVER_URLS"] = "http://server1:8080"
        try:
            response = self.client.get("/health/peers/http://server1:8080")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "healthy"
            assert data["server"] == "http://server1:8080"
        finally:
            del os.environ["SERVER_URLS"]

    def test_health_peer_not_configured(self):
        """GET /health/peers/<url> returns 400 for unconfigured peer."""
        response = self.client.get("/health/peers/http://unknown:8080")
        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["status"] == "error"


class TestSyncStatusEndpoint:
    """Tests for the sync status endpoint."""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        from web import db

        db.create_all()

        org = Organization(name="Test Org", slug="test-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(team)
        db.session.flush()
        self.team_id = team.id

        user = User(
            username="sync_status_user",
            email="syncstatus@example.com",
            organization_id=org.id,
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        membership = OrganizationMembership(
            user_id=user.id, organization_id=org.id, is_gm=False
        )
        db.session.add(membership)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["current_team_id"] = team.id

        self.client.post(
            "/auth/login",
            data={"username": "sync_status_user", "password": "password"},
            follow_redirects=True,
        )

    def tearDown(self):
        from web import db

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_sync_status_defaults(self):
        """GET /api/v1/sync/status returns default sync config."""
        response = self.client.get("/api/v1/sync/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["sync_enabled"] is False
        assert data["server_urls"] == []
        assert data["sync_interval"] == 300
        assert data["sync_timeout"] == 10

    @patch.dict(os.environ, {"SYNC_ENABLED": "true", "SYNC_INTERVAL": "600"})
    def test_sync_status_custom_env(self):
        """GET /api/v1/sync/status returns config from env vars."""
        response = self.client.get("/api/v1/sync/status")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["sync_enabled"] is True
        assert data["sync_interval"] == 600


class TestSyncPeersEndpoint:
    """Tests for the sync peers endpoint."""

    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

        from web import db

        db.create_all()

        org = Organization(name="Test Org", slug="test-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(team)
        db.session.flush()
        self.team_id = team.id

        user = User(
            username="sync_peers_user",
            email="syncpeers@example.com",
            organization_id=org.id,
        )
        user.set_password("password")
        db.session.add(user)
        db.session.flush()
        membership = OrganizationMembership(
            user_id=user.id, organization_id=org.id, is_gm=False
        )
        db.session.add(membership)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess["current_team_id"] = team.id

        self.client.post(
            "/auth/login",
            data={"username": "sync_peers_user", "password": "password"},
            follow_redirects=True,
        )

    def tearDown(self):
        from web import db

        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_sync_peers_no_configured_servers(self):
        """GET /api/v1/sync/peers returns empty results when no servers configured."""
        response = self.client.get("/api/v1/sync/peers")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert data["total"] == 0
        assert data["reachable"] == 0

    @patch("web.routes.api_v1.httpx.Client")
    def test_sync_peers_all_reachable(self, mock_client_cls):
        """GET /api/v1/sync/peers reports all reachable."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        os.environ["SERVER_URLS"] = "http://server1:8080,http://server2:8080"
        try:
            response = self.client.get("/api/v1/sync/peers")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "healthy"
            assert data["total"] == 2
            assert data["reachable"] == 2
        finally:
            del os.environ["SERVER_URLS"]

    def test_sync_trigger_no_configured_servers(self):
        """POST /api/v1/sync/trigger returns empty results when no servers configured."""
        response = self.client.post("/api/v1/sync/trigger")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "complete"
        assert data["total"] == 0
        assert data["synced"] == 0
        assert data["results"] == []
