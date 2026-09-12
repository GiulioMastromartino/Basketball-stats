"""Tests for the Championship analytics subpage (selectable source)."""

from core.models import Game, db


class TestChampionship:
    def test_internal_default(self, admin_client, db_session, sample_game):
        resp = admin_client.get("/analytics/championship")
        assert resp.status_code == 200
        assert b"Championship" in resp.data
        assert b"Source" in resp.data
        assert sample_game.opponent.encode() in resp.data

    def test_unknown_source_falls_back(self, admin_client, db_session,
                                       sample_game):
        resp = admin_client.get("/analytics/championship?source=bogus")
        assert resp.status_code == 200
        assert sample_game.opponent.encode() in resp.data

    def test_playbasket_source(self, admin_client):
        resp = admin_client.get("/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        assert b"Leone XIII Milano sq.B" in resp.data
        assert b"Standings" in resp.data

    def test_playbasket_team_filter(self, admin_client):
        resp = admin_client.get(
            "/analytics/championship?source=playbasket&team=aurora")
        assert resp.status_code == 200
        assert b"Aurora Milano" in resp.data
        # Aurora played 22 games: filter keeps exactly those result rows.
        assert resp.data.count(b'<td class="ps-4 small">') == 22

    def test_internal_empty_team(self, admin_client, db_session, default_org):
        from core.models import Team
        team = Team(name="Empty", organization_id=default_org.id,
                    slug="empty-t")
        db.session.add(team)
        db.session.commit()
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = team.id
        resp = admin_client.get("/analytics/championship?source=internal")
        assert resp.status_code == 200
        assert b"No games in scope" in resp.data

    def test_nav_link_present(self, admin_client, db_session, sample_game):
        resp = admin_client.get("/analytics")
        assert resp.status_code == 200

    def test_auditor_without_home_org_sees_no_users(self, client, db_session,
                                                   default_org):
        from core.models import OrganizationMembership as _M, User as _U
        auditor = _U(username="aud_nohome", email="aud_nohome@test.com",
                     organization_id=None, is_auditor=True)
        auditor.set_password("password123")
        db.session.add(auditor)
        db.session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(auditor.id)
            sess["_fresh"] = True
        resp = client.get("/admin/users")
        assert resp.status_code == 200
        assert b"test_admin" not in resp.data

    def test_playbasket_missing_snapshot_shows_warning(
            self, admin_client, monkeypatch):
        import web.routes.analytics as _a
        monkeypatch.setattr(
            _a, "_load_playbasket_snapshot",
            lambda: {"meta": {}, "standings": [], "games": []})
        resp = admin_client.get("/analytics/championship?source=playbasket")
        assert resp.status_code == 200
        assert b"unavailable" in resp.data
