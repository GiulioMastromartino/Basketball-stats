"""Tests for promoting a sidecar external game to an internal draft.

The SQLite sidecar (core.external_store) is reference data only: the POST
.../external/games/<id>/promote endpoint is the single sanctioned path to
an internal Game, requiring an explicit action scoped to the user's team.
"""

import pytest

from core import external_store as store
from core.models import (
    Game,
    Organization,
    OrganizationMembership,
    Team,
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
def ext_game_id(tmp_path, monkeypatch):
    """Seed an isolated sidecar (never the real data/external_cache.db)."""
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
        return store.list_games(conn, champ_id)[0]["id"]
    finally:
        conn.close()


@pytest.fixture
def tracked(db_session, default_team):
    row = TrackedChampionship(team_id=default_team.id, display_name="DR4",
                              active=True, **TRACKED_KEYS)
    db_session.add(row)
    db_session.commit()
    return row


def _promote_url(ext_game_id):
    return f"/api/advanced/external/games/{ext_game_id}/promote"


class TestPromoteExternal:
    def test_promote_creates_draft(self, admin_client, db_session,
                                   default_team, ext_game_id, tracked):
        resp = admin_client.post(_promote_url(ext_game_id))
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["already_promoted"] is False

        game = Game.query.filter_by(id=data["game_id"]).first()
        assert game is not None
        assert game.team_id == default_team.id
        assert game.game_type == "Draft"
        assert game.source == "EXTERNAL"
        assert game.opponent == "Team A vs Team B"
        assert game.date == "16-10-2025"
        assert game.sort_date == "2025-10-16"
        assert (game.team_score, game.opponent_score) == (68, 60)
        assert data["source_url"] == "https://example.test/champ"
        assert data["stable_hash"]

    def test_repromote_is_idempotent(self, admin_client, ext_game_id,
                                     tracked):
        first = admin_client.post(_promote_url(ext_game_id))
        second = admin_client.post(_promote_url(ext_game_id))
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.get_json()["game_id"] == first.get_json()["game_id"]
        assert second.get_json()["already_promoted"] is True
        assert Game.query.filter_by(source="EXTERNAL").count() == 1

    def test_cross_team_denied(self, admin_client, db_session, default_org,
                               ext_game_id, tracked):
        other = Team(name="Other", organization_id=default_org.id,
                     slug="other-t")
        db_session.add(other)
        db_session.commit()
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = other.id
            sess["current_team_name"] = other.name
        resp = admin_client.post(_promote_url(ext_game_id))
        assert resp.status_code == 403
        assert Game.query.filter_by(source="EXTERNAL").count() == 0

    def test_cross_org_denied(self, admin_client, db_session, ext_game_id):
        org2 = Organization(name="Org Two", slug="org-two")
        db_session.add(org2)
        db_session.flush()
        team2 = Team(name="Team Two", organization_id=org2.id,
                     slug="team-two")
        db_session.add(team2)
        db_session.flush()
        db_session.add(TrackedChampionship(
            team_id=team2.id, display_name="DR4", active=True,
            **TRACKED_KEYS))
        db_session.commit()
        # Org-1 admin tampers the session onto org-2's tracked team.
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = team2.id
            sess["current_team_name"] = team2.name
        resp = admin_client.post(_promote_url(ext_game_id))
        assert resp.status_code == 403
        assert Game.query.filter_by(source="EXTERNAL").count() == 0

    def test_own_org_other_team_tracking_works(self, client, db_session,
                                               ext_game_id):
        org2 = Organization(name="Org Two", slug="org-two")
        db_session.add(org2)
        db_session.flush()
        team2 = Team(name="Team Two", organization_id=org2.id,
                     slug="team-two")
        db_session.add(team2)
        db_session.flush()
        user2 = User(username="gm2", email="gm2@test.com",
                     organization_id=org2.id)
        user2.set_password("password123")
        db_session.add(user2)
        db_session.flush()
        db_session.add(OrganizationMembership(
            user_id=user2.id, organization_id=org2.id, is_gm=True))
        db_session.add(TrackedChampionship(
            team_id=team2.id, display_name="DR4", active=True,
            **TRACKED_KEYS))
        db_session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user2.id)
            sess["_fresh"] = True
            sess["current_team_id"] = team2.id
            sess["current_team_name"] = team2.name
        resp = client.post(_promote_url(ext_game_id))
        assert resp.status_code == 201
        game = Game.query.filter_by(id=resp.get_json()["game_id"]).first()
        assert game.team_id == team2.id

    def test_unknown_ext_id_404(self, admin_client, ext_game_id, tracked):
        resp = admin_client.post("/api/advanced/external/games/999999/promote")
        assert resp.status_code == 404
