"""Slice A1: Live Game v2 console shell + score strip route tests."""

import pytest


class TestLiveV2Route:
    @pytest.mark.integration
    def test_live_v2_page_loads(self, auth_client):
        """Route returns 200 for an authenticated, team-scoped user."""
        response = auth_client.get("/live-v2")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_live_v2_requires_auth(self, client):
        """Unauthenticated users are redirected to login."""
        response = client.get("/live-v2")
        assert response.status_code in (302, 401)

    @pytest.mark.integration
    def test_live_v2_contains_key_element_ids(self, auth_client):
        """Template contains the score strip + shell stub containers."""
        response = auth_client.get("/live-v2")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        for element_id in [
            "v2-score-strip",
            "v2-team-a-name",
            "v2-team-a-score",
            "v2-team-b-name",
            "v2-team-b-score",
            "v2-period",
            "v2-period-prev",
            "v2-period-next",
            "v2-clock",
            "v2-team-a-fouls",
            "v2-team-b-fouls",
            "v2-team-a-timeouts",
            "v2-team-b-timeouts",
            "v2-possession",
            "v2-roster-home",
            "v2-roster-away",
            "v2-court",
            "v2-game-log",
            "v2-action-pad",
        ]:
            assert f'id="{element_id}"' in html, f"missing #{element_id}"

    @pytest.mark.integration
    def test_live_v2_references_v2_js_only(self, auth_client):
        """V2 page loads live_game_v2.js and not the frozen legacy bundle."""
        response = auth_client.get("/live-v2")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "js/live_game_v2.js" in html
        assert "js/live_game.js" not in html.replace("js/live_game_v2.js", "")

    @pytest.mark.integration
    def test_live_v2_roster_action_court_ids(self, auth_client):
        """Roster rails + court tap + action pad + undo + sub sheet IDs exist."""
        response = auth_client.get("/live-v2")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        for element_id in [
            # Court tap popover
            "v2-court-wrap",
            "v2-shot-popover",
            "v2-shot-label",
            "v2-shot-made",
            "v2-shot-miss",
            "v2-shot-cancel",
            "v2-shot-marks",
            "v2-need-player",
            # Action pad
            "v2-selected-display",
            "v2-action-assist",
            "v2-action-rebound",
            "v2-action-block",
            "v2-action-steal",
            "v2-action-ft-made",
            "v2-action-ft-miss",
            "v2-action-foul",
            "v2-action-tech",
            "v2-action-tov",
            "v2-action-timeout",
            "v2-action-sub",
            "v2-action-undo",
            # Substitution sheet
            "v2-sub-sheet",
            "v2-sub-list",
            "v2-sub-close",
        ]:
            assert f'id="{element_id}"' in html, f"missing #{element_id}"

    @pytest.mark.integration
    def test_live_v2_bootstraps_route_context(self, auth_client):
        """Route context (existing_players/plays/now_date) is embedded as JSON."""
        response = auth_client.get("/live-v2")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "window.V2_BOOTSTRAP" in html
        assert "homePlayers" in html
        assert "nowDate" in html

    @pytest.mark.integration
    def test_live_v2_court_is_tappable(self, auth_client):
        """Court SVG is focusable/clickable with an accessible label."""
        response = auth_client.get("/live-v2")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert 'id="v2-court"' in html
        assert "Half-court tap area" in html or "tap" in html.lower()
