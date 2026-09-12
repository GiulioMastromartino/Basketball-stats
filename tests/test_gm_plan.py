"""Tests for the GM & Admin UX plan (Assignment matrix, invite, rename,
transfer, org workspace, audit trail, per-team GM, auditor, org switcher).
"""

import pytest

from core.models import (
    AdminAudit,
    Game,
    Organization,
    OrganizationMembership,
    Team,
    TeamAssignment,
    User,
    db,
)


def _other_user(db_session, org, username="gmplan_mate", email="gmplan@test.com"):
    user = User(username=username, email=email, organization_id=org.id)
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    db.session.add(OrganizationMembership(
        user_id=user.id, organization_id=org.id, is_gm=False))
    db.session.commit()
    return user


class TestMatrixAndActivity:
    def test_matrix_section_renders(self, admin_client):
        resp = admin_client.get("/admin/matrix")
        assert resp.status_code == 200
        assert b"Assignment matrix" in resp.data

    def test_activity_section_renders(self, admin_client):
        resp = admin_client.get("/admin/activity")
        assert resp.status_code == 200
        assert b"Activity" in resp.data

    def test_matrix_click_toggle(self, admin_client, db_session,
                                 default_org, default_team):
        user = _other_user(db_session, default_org)
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": True})
        assert resp.get_json()["ok"] is True
        resp = admin_client.get("/admin/matrix")
        assert default_team.name.encode() in resp.data
        assert user.username.encode() in resp.data


class TestInviteFlow:
    def test_invite_creates_user_with_teams(
            self, admin_client, db_session, default_org, default_team):
        resp = admin_client.post(
            "/auth/users/invite",
            data={"username": "sara.k", "email": "sara@club.it",
                  "team_ids": [str(default_team.id)],
                  "is_coach": "on"},
            follow_redirects=True)
        assert resp.status_code == 200
        user = User.query.filter_by(username="sara.k").first()
        assert user is not None
        assert user.organization_id == default_org.id
        ta = TeamAssignment.query.filter_by(
            user_id=user.id, team_id=default_team.id).first()
        assert ta is not None and ta.is_coach is True
        audit = AdminAudit.query.filter_by(action="user.invite").first()
        assert audit is not None

    def test_invite_rejects_duplicates(
            self, admin_client, db_session, default_org, default_team):
        user = _other_user(db_session, default_org)
        resp = admin_client.post(
            "/auth/users/invite",
            data={"username": user.username, "email": "fresh@club.it"},
            follow_redirects=True)
        assert resp.status_code == 200
        assert User.query.filter_by(email="fresh@club.it").first() is None

    def test_invite_requires_username_email(self, admin_client):
        resp = admin_client.post(
            "/auth/users/invite", data={"username": "", "email": ""},
            follow_redirects=True)
        assert resp.status_code == 200


class TestRenameTransfer:
    def test_rename_org(self, admin_client, db_session, default_org):
        resp = admin_client.post(
            f"/orgs/{default_org.id}/rename",
            data={"name": "Renamed Org"}, follow_redirects=True)
        assert resp.status_code == 200
        assert Organization.query.get(default_org.id).name == "Renamed Org"

    def test_rename_org_rejects_duplicates(
            self, admin_client, db_session, default_org):
        other = Organization(name="Satellite", slug="satellite")
        db.session.add(other)
        db.session.commit()
        resp = admin_client.post(
            f"/orgs/{default_org.id}/rename",
            data={"name": "Satellite"}, follow_redirects=True)
        assert resp.status_code == 200
        assert Organization.query.get(default_org.id).name == default_org.name

    def test_rename_team(self, admin_client, db_session, default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/rename",
            data={"name": "U14 Herons"}, follow_redirects=True)
        assert resp.status_code == 200
        assert Team.query.get(default_team.id).name == "U14 Herons"

    def test_transfer_team_keeps_games(
            self, admin_client, db_session, default_team, sample_game):
        dest = Organization(name="Dest Club", slug="dest-club")
        db.session.add(dest)
        db.session.commit()
        games_before = Game.query.filter_by(team_id=default_team.id).count()
        assert games_before >= 1
        resp = admin_client.post(
            f"/teams/{default_team.id}/transfer",
            data={"organization_id": dest.id}, follow_redirects=True)
        assert resp.status_code == 200
        team = Team.query.get(default_team.id)
        assert team.organization_id == dest.id
        assert Game.query.filter_by(team_id=team.id).count() == games_before

    def test_transfer_rejects_same_org(
            self, admin_client, db_session, default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/transfer",
            data={"organization_id": default_team.organization_id},
            follow_redirects=True)
        assert resp.status_code == 200
        assert Team.query.get(default_team.id).organization_id == \
            default_team.organization_id


class TestOrgWorkspaceAndDefaults:
    def test_org_filter(self, admin_client, db_session, default_org):
        other = Organization(name="Other Club", slug="other-club-2")
        db.session.add(other)
        db.session.commit()
        # Cross-org data is no longer visible at all (isolation).
        resp = admin_client.get(f"/admin/orgs?org_id={other.id}")
        assert resp.status_code == 200
        assert b"Other Club" not in resp.data
        # Own org filters fine.
        resp = admin_client.get(f"/admin/orgs?org_id={default_org.id}")
        assert resp.status_code == 200
        assert default_org.name.encode() in resp.data

    def test_update_org_defaults(self, admin_client, db_session, default_org):
        resp = admin_client.post(
            f"/orgs/{default_org.id}/settings",
            data={"timezone": "Europe/Rome", "sport": "basketball",
                  "season_convention": "calendar"},
            follow_redirects=True)
        assert resp.status_code == 200
        org = Organization.query.get(default_org.id)
        assert org.timezone == "Europe/Rome"
        assert org.season_convention == "calendar"

    def test_invalid_convention_falls_back(
            self, admin_client, db_session, default_org):
        admin_client.post(
            f"/orgs/{default_org.id}/settings",
            data={"timezone": "UTC", "sport": "basketball",
                  "season_convention": "nonsense"},
            follow_redirects=True)
        assert Organization.query.get(default_org.id).season_convention == \
            "sept-june"


class TestPerTeamGMAndAuditor:
    def test_team_gm_flag_toggle(
            self, admin_client, db_session, default_org, default_team):
        user = _other_user(db_session, default_org)
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": True,
                  "role": "team_gm"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        ta = TeamAssignment.query.filter_by(
            user_id=user.id, team_id=default_team.id).first()
        assert ta is not None and ta.is_team_gm is True

    def test_auditor_readonly(
            self, client, db_session, default_org, default_team):
        auditor = User(username="auditor1", email="auditor1@test.com",
                       organization_id=default_org.id, is_auditor=True)
        auditor.set_password("password123")
        db.session.add(auditor)
        db.session.flush()
        db.session.add(OrganizationMembership(
            user_id=auditor.id, organization_id=default_org.id,
            is_gm=False))
        db.session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(auditor.id)
            sess["_fresh"] = True
            sess["current_team_id"] = default_team.id
        # Can view admin + activity.
        assert client.get("/admin/users").status_code == 200
        assert client.get("/admin/activity").status_code == 200
        # Cannot mutate via JSON endpoint.
        user = _other_user(db_session, default_org,
                           username="aud_target", email="aud_target@t.com")
        resp = client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": True})
        assert resp.status_code == 403
        # Cannot invite (gm_required redirect).
        resp = client.post(
            "/auth/users/invite",
            data={"username": "x", "email": "x@t.com"},
            follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_switch_org(self, admin_client, db_session, admin_user):
        org2 = Organization(name="Second Org", slug="second-org")
        db.session.add(org2)
        db.session.flush()
        db.session.add(OrganizationMembership(
            user_id=admin_user.id, organization_id=org2.id, is_gm=True))
        db.session.commit()
        resp = admin_client.post(
            "/switch-org", data={"org_id": org2.id},
            follow_redirects=False)
        assert resp.status_code in (302, 303)
        with admin_client.session_transaction() as sess:
            assert sess.get("current_org_id") == org2.id

    def test_gm_dashboard_renders(self, admin_client):
        resp = admin_client.get("/gm/dashboard")
        assert resp.status_code == 200


class TestGMDashboardTeamManagement:
    """Rename + add teams directly from the GM dashboard."""

    def test_dashboard_shows_new_team_and_rename(
            self, admin_client, db_session, default_team):
        resp = admin_client.get("/gm/dashboard")
        assert resp.status_code == 200
        assert b"New team" in resp.data
        assert b"Rename" in resp.data
        assert default_team.name.encode() in resp.data

    def test_dashboard_hides_mutations_for_auditor(
            self, client, db_session, default_org, default_team):
        from core.models import User as _User
        auditor = _User(username="aud_dash", email="aud_dash@test.com",
                        organization_id=default_org.id, is_auditor=True)
        auditor.set_password("password123")
        db.session.add(auditor)
        db.session.flush()
        db.session.add(OrganizationMembership(
            user_id=auditor.id, organization_id=default_org.id,
            is_gm=False))
        db.session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(auditor.id)
            sess["_fresh"] = True
            sess["current_team_id"] = default_team.id
        resp = client.get("/gm/dashboard")
        assert resp.status_code == 200
        assert b"New team" not in resp.data
        assert b"Rename" not in resp.data

    def test_create_team_from_dashboard_redirects_back(
            self, admin_client, db_session, default_org):
        resp = admin_client.post(
            "/teams/create",
            data={"organization_id": default_org.id,
                  "name": "Dash Team", "next": "/gm/dashboard"},
            follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert resp.headers["Location"].endswith("/gm/dashboard")
        assert Team.query.filter_by(
            organization_id=default_org.id, slug="dash-team").first() is not None

    def test_rename_team_from_dashboard_redirects_back(
            self, admin_client, db_session, default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/rename",
            data={"name": "Dash Renamed", "next": "/gm/dashboard"},
            follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert resp.headers["Location"].endswith("/gm/dashboard")
        assert Team.query.get(default_team.id).name == "Dash Renamed"

    def test_unsafe_next_falls_back_to_admin(
            self, admin_client, db_session, default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/rename",
            data={"name": "Safe Name", "next": "http://evil.example/"},
            follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "evil.example" not in resp.headers["Location"]
        assert Team.query.get(default_team.id).name == "Safe Name"


class TestTeamContextLinks:
    """?team_id= links (GM dashboard buttons) scope team pages."""

    def test_team_param_switches_context(
            self, admin_client, db_session, default_org, default_team):
        other = Team(name="Other Side", organization_id=default_org.id,
                     slug="other-side")
        db.session.add(other)
        db.session.commit()
        resp = admin_client.get(f"/players?team_id={other.id}")
        assert resp.status_code == 200
        with admin_client.session_transaction() as sess:
            assert sess.get("current_team_id") == other.id

    def test_team_param_unknown_team_ignored(
            self, admin_client, db_session, default_team):
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = default_team.id
        resp = admin_client.get("/players?team_id=999999")
        assert resp.status_code == 200
        with admin_client.session_transaction() as sess:
            assert sess.get("current_team_id") == default_team.id

    def test_team_param_cross_org_ignored(
            self, admin_client, db_session, default_org, default_team):
        other_org = Organization(name="Far Away", slug="far-away")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Far Team", organization_id=other_org.id,
                          slug="far-team")
        db.session.add(other_team)
        db.session.commit()
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = default_team.id
        resp = admin_client.get(f"/players?team_id={other_team.id}")
        assert resp.status_code == 200
        with admin_client.session_transaction() as sess:
            assert sess.get("current_team_id") == default_team.id


class TestPlayersScopedToTeam:
    """Players listing/detail follow the session team."""

    def _second_team_game(self, db_session, default_org, name="Second Star"):
        from core.models import Game as _Game, PlayerStat as _PS
        team2 = Team(name="Second Team", organization_id=default_org.id,
                     slug="second-team")
        db.session.add(team2)
        db.session.flush()
        game = _Game(date="01-01-2024", opponent="Rivals", team_score=80,
                     opponent_score=70, result="W", game_type="Season",
                     sort_date="2024-01-01", source="MANUAL",
                     team_id=team2.id)
        db.session.add(game)
        db.session.flush()
        db.session.add(_PS(game_id=game.id, player_name=name, points=10,
                           minutes="20:00"))
        db.session.commit()
        return team2

    def test_listing_scoped_to_session_team(
            self, admin_client, db_session, default_org, default_team,
            sample_game, sample_player_stat):
        team2 = self._second_team_game(db_session, default_org)
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = team2.id
        resp = admin_client.get("/players")
        assert resp.status_code == 200
        assert b"Second Star" in resp.data
        assert b"John Doe" not in resp.data

    def test_player_detail_scoped_to_team(
            self, admin_client, db_session, default_org, default_team,
            sample_game, sample_player_stat):
        team2 = self._second_team_game(db_session, default_org)
        with admin_client.session_transaction() as sess:
            sess["current_team_id"] = team2.id
        # John Doe only played for the default team: scoped detail refuses.
        resp = admin_client.get("/player/John%20Doe", follow_redirects=False)
        assert resp.status_code == 302
        assert "/players" in resp.headers["Location"]


class TestCrossOrgIsolation:
    """One org's GM cannot read or mutate another org's data."""

    @pytest.fixture
    def org_b(self, db_session):
        from core.models import Organization as _Org
        org = _Org(name="Org B", slug="org-b")
        db.session.add(org)
        db.session.commit()
        return org

    @pytest.fixture
    def team_b(self, db_session, org_b):
        team = Team(name="B Team", organization_id=org_b.id, slug="b-team")
        db.session.add(team)
        db.session.commit()
        return team

    @pytest.fixture
    def user_b(self, db_session, org_b):
        user = User(username="user_b", email="user_b@test.com",
                    organization_id=org_b.id)
        user.set_password("password123")
        db.session.add(user)
        db.session.flush()
        db.session.add(OrganizationMembership(
            user_id=user.id, organization_id=org_b.id, is_gm=False))
        db.session.commit()
        return user

    def test_cannot_delete_other_org_user(
            self, admin_client, db_session, user_b):
        resp = admin_client.post(f"/auth/users/{user_b.id}/delete",
                                 follow_redirects=False)
        assert resp.status_code == 403
        assert User.query.get(user_b.id) is not None

    def test_cannot_rename_other_org(
            self, admin_client, db_session, org_b):
        resp = admin_client.post(f"/orgs/{org_b.id}/rename",
                                 data={"name": "Hijacked"},
                                 follow_redirects=False)
        assert resp.status_code == 403
        assert Organization.query.get(org_b.id).name == "Org B"

    def test_cannot_delete_other_org_with_data(
            self, admin_client, db_session, org_b, team_b):
        # Non-empty orgs are never deletable (existing guard); the org
        # survives regardless of whose GM attempts it.
        resp = admin_client.post(f"/orgs/{org_b.id}/delete",
                                 follow_redirects=True)
        assert resp.status_code == 200
        assert Organization.query.get(org_b.id) is not None
        assert Team.query.get(team_b.id) is not None

    def test_cannot_change_other_org_settings(
            self, admin_client, db_session, org_b):
        resp = admin_client.post(
            f"/orgs/{org_b.id}/settings",
            data={"timezone": "X", "sport": "Y",
                  "season_convention": "calendar"},
            follow_redirects=False)
        assert resp.status_code == 403
        assert Organization.query.get(org_b.id).timezone != "X"

    def test_cannot_create_team_in_other_org(
            self, admin_client, db_session, org_b):
        resp = admin_client.post(
            "/teams/create",
            data={"organization_id": org_b.id, "name": "Intruder"},
            follow_redirects=False)
        assert resp.status_code == 403
        assert Team.query.filter_by(slug="intruder").first() is None

    def test_cannot_rename_delete_transfer_other_org_team(
            self, admin_client, db_session, org_b, team_b, default_org):
        assert admin_client.post(
            f"/teams/{team_b.id}/rename", data={"name": "Hijacked"},
            follow_redirects=False).status_code == 403
        assert admin_client.post(
            f"/teams/{team_b.id}/delete",
            follow_redirects=False).status_code == 403
        assert admin_client.post(
            f"/teams/{team_b.id}/transfer",
            data={"organization_id": default_org.id},
            follow_redirects=False).status_code == 403
        team = Team.query.get(team_b.id)
        assert team.name == "B Team"
        assert team.organization_id == org_b.id

    def test_switch_org_requires_membership(
            self, admin_client, db_session, org_b):
        resp = admin_client.post("/switch-org", data={"org_id": org_b.id},
                                 follow_redirects=False)
        assert resp.status_code in (302, 303)
        with admin_client.session_transaction() as sess:
            assert sess.get("current_org_id") != org_b.id

    def test_admin_lists_scoped_to_own_org(
            self, admin_client, db_session, org_b, user_b):
        resp = admin_client.get("/admin/users")
        assert resp.status_code == 200
        assert b"user_b" not in resp.data
        resp = admin_client.get("/admin/orgs")
        assert b"Org B" not in resp.data
