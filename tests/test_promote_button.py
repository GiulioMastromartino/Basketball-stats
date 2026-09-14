"""Tests for the Promote button on the championship page.

UI half of the merged promote endpoint: the championship route threads the
sidecar ext game id into each snapshot row; the template renders one
Promote button per ext row (GM/coach only) that POSTs to
POST /api/advanced/external/games/<id>/promote with CSRF.
"""

import pytest

from core import external_store as store
from core.models import (
    OrganizationMembership,
    TeamAssignment,
    TrackedChampionship,
    User,
    db,
)

CHAMP_KEYS = {
    "provider": "playbasket_html",
    "comitato": "RLO",
    "campionato": "DR4",
    "fase": "1",
    "girone": "M",
    "season": "2025/2026",
}

TRACKED_KEYS = {
    "provider": "playbasket_html",
    "comitato_codice": "RLO",
    "province_codice": "MI",
    "codice_campionato": "DR4",
    "codice_fase": "1",
    "codice_girone": "M",
    "season_label": "2025/2026",
}


@pytest.fixture
def ext_seed(tmp_path, monkeypatch):
    """Seed an isolated sidecar with one scored + one unscored game."""
    monkeypatch.setenv("EXT_CACHE_PATH", str(tmp_path / "ext_cache.db"))
    conn = store.connect(tmp_path / "ext_cache.db")
    try:
        champ_id = store.upsert_championship(
            conn, display_name="DR4 Girone M",
            source_url="https://example.test/champ", **CHAMP_KEYS)
        store.upsert_game(
            conn, champ_id,
            {"round": "Andata 1", "date": "16/10", "home": "Team A",
             "away": "Team B", "home_score": 68, "away_score": 60,
             "status": "played"})
        store.upsert_game(
            conn, champ_id,
            {"round": "Andata 2", "date": "23/10", "home": "Team C",
             "away": "Team D", "status": "scheduled"})
        games = store.list_games(conn, champ_id)
        return {f"{g['home']} vs {g['away']}": g["id"] for g in games}
    finally:
        conn.close()


@pytest.fixture
def tracked(db_session, default_team):
    row = TrackedChampionship.query.filter_by(
        team_id=default_team.id, **TRACKED_KEYS).first()
    if row is None:
        row = TrackedChampionship(team_id=default_team.id,
                                  display_name="DR4", active=True,
                                  **TRACKED_KEYS)
        db_session.add(row)
        db_session.commit()
    return row


@pytest.fixture
def coach_client(client, db_session, default_org, default_team):
    user = User(username="promo_coach", email="promo_coach@test.com",
                organization_id=default_org.id)
    user.set_password("password123")
    db_session.add(user)
    db_session.flush()
    db_session.add(OrganizationMembership(
        user_id=user.id, organization_id=default_org.id, is_gm=False))
    db_session.add(TeamAssignment(user_id=user.id, team_id=default_team.id,
                                  is_coach=True))
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["current_team_id"] = default_team.id
        sess["current_team_name"] = default_team.name
    return client


class TestPromoteButton:
    def test_page_contains_buttons_with_ext_ids(
            self, admin_client, ext_seed):
        resp = admin_client.get("/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        html = resp.data.decode()
        for label, ext_id in ext_seed.items():
            assert f'data-ext-id="{ext_id}"' in html
        assert "data-promote-button" in html
        # Inline script POSTs with CSRF and links the created draft game.
        assert "/api/advanced/external/games/" in html
        assert "X-CSRFToken" in html
        assert "/game/" in html
        assert "textContent" in html

    def test_scored_and_unscored_rows_both_have_buttons(
            self, admin_client, ext_seed):
        resp = admin_client.get("/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        html = resp.data.decode()
        # One scored (68-60) + one unscored ("-") row, each with a button.
        assert html.count("data-promote-button data-ext-id") == 2

    def test_coach_sees_buttons(self, coach_client, ext_seed):
        resp = coach_client.get(
            "/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        assert "data-promote-button data-ext-id" in resp.data.decode()

    def test_editor_sees_no_buttons(self, auth_client, ext_seed):
        resp = auth_client.get(
            "/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        assert "data-promote-button data-ext-id" not in resp.data.decode()

    def test_promote_flow_then_drafted_state(
            self, admin_client, ext_seed, tracked):
        ext_id = ext_seed["Team A vs Team B"]
        first = admin_client.post(
            f"/api/advanced/external/games/{ext_id}/promote")
        assert first.status_code == 201
        assert first.get_json()["already_promoted"] is False
        page = admin_client.get("/analytics/championship?source=playbasket")
        assert page.status_code == 200
        html = page.data.decode()
        assert "Drafted \u2713" in html
        # The promoted row no longer offers a button; the other row still does.
        assert f'data-promote-button data-ext-id="{ext_id}"' not in html
        other = ext_seed["Team C vs Team D"]
        assert f'data-ext-id="{other}"' in html

    def test_bundled_fallback_has_no_buttons(self, admin_client, tmp_path,
                                             monkeypatch):
        # No sidecar seeded: bundled JSON snapshot has no ext ids.
        # Pin EXT_CACHE_PATH at an empty location so a real default sidecar
        # file can never leak ext ids into this fallback assertion.
        monkeypatch.setenv("EXT_CACHE_PATH", str(tmp_path / "empty.db"))
        resp = admin_client.get("/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        assert "data-promote-button data-ext-id" not in resp.data.decode()

    def test_unauthenticated_redirect_no_crash(self, client, ext_seed):
        resp = client.get("/analytics/championship?source=playbasket",
                          follow_redirects=False)
        assert resp.status_code in (302, 401, 403)
        followed = client.get("/analytics/championship?source=playbasket",
                              follow_redirects=True)
        assert followed.status_code == 200
