"""Tests for the Lineup Optimizer UI card on the lineups page.

Covers the UI slice only (web/templates/lineups.html): the optimizer card
with context select + results container + inline script calling
GET /api/advanced/lineup-optimizer.
"""

import pytest

EXPECTED_CONTEXTS = [
    "balanced",
    "vs_zone",
    "vs_fast",
    "protect_lead",
    "need_stops",
    "need_score",
]


class TestLineupOptimizerUI:
    @pytest.mark.integration
    def test_lineups_page_contains_optimizer_card(self, auth_client):
        resp = auth_client.get("/lineups")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="optimizerCard"' in html
        assert 'data-endpoint="/api/advanced/lineup-optimizer"' in html
        assert 'id="optimizerContext"' in html
        assert 'id="optimizerBtn"' in html
        assert "Get suggestions" in html
        assert 'id="optimizerResults"' in html

    @pytest.mark.integration
    def test_optimizer_card_context_options(self, auth_client):
        resp = auth_client.get("/lineups")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        for context in EXPECTED_CONTEXTS:
            assert f'value="{context}"' in html

    @pytest.mark.integration
    def test_optimizer_card_xss_safe_rendering(self, auth_client):
        """Player names/score/explanation must be rendered via textContent."""
        resp = auth_client.get("/lineups")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "textContent" in html
        # The optimizer script must not inject server data via innerHTML.
        script = html.split('id="optimizerCard"')[-1]
        assert "innerHTML" not in script

    @pytest.mark.integration
    def test_optimizer_card_empty_state_copy(self, auth_client):
        resp = auth_client.get("/lineups")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True).lower()
        assert "not enough tracked possessions" in html

    @pytest.mark.integration
    def test_lineups_page_anonymous_no_crash(self, client, sample_game):
        """Anonymous handling matches page convention: redirect, never 500."""
        resp = client.get("/lineups")
        assert resp.status_code in (302, 401)
        assert resp.status_code != 500
