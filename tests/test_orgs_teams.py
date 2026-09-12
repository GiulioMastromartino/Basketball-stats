"""Tests for org & team admin management."""

import pytest

from core.models import Game, Organization, Team, TeamAssignment, User, db


class TestOrgAdmin:
    def test_admin_panel_orgs_section(self, admin_client):
        resp = admin_client.get("/admin/orgs")
        assert resp.status_code == 200
        assert b"Organizations" in resp.data or b"Orgs" in resp.data

    def test_create_org(self, admin_client, db_session):
        resp = admin_client.post(
            "/orgs/create", data={"name": "New Org"}, follow_redirects=True
        )
        assert resp.status_code == 200
        org = Organization.query.filter_by(slug="new-org").first()
        assert org is not None
        assert org.name == "New Org"

    def test_create_org_rejects_blank_and_duplicates(
        self, admin_client, db_session, default_org
    ):
        resp = admin_client.post(
            "/orgs/create", data={"name": ""}, follow_redirects=True
        )
        assert resp.status_code == 200
        resp = admin_client.post(
            "/orgs/create", data={"name": default_org.name},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert Organization.query.filter_by(slug="test-org").count() == 1

    def test_delete_empty_org(self, admin_client, db_session):
        org = Organization(name="Lonely", slug="lonely")
        db.session.add(org)
        db.session.commit()
        resp = admin_client.post(
            f"/orgs/{org.id}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert Organization.query.get(org.id) is None

    def test_delete_org_blocked_with_teams(
        self, admin_client, db_session, default_team
    ):
        resp = admin_client.post(
            f"/orgs/{default_team.organization_id}/delete",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert Organization.query.get(default_team.organization_id) is not None

    def test_editor_cannot_manage_orgs(
        self, auth_client, db_session, default_org
    ):
        resp = auth_client.post(
            "/orgs/create", data={"name": "Nope"}, follow_redirects=False
        )
        assert resp.status_code in (302, 403)
        assert Organization.query.filter_by(slug="nope").first() is None
        resp = auth_client.post(
            f"/orgs/{default_org.id}/delete", follow_redirects=False
        )
        assert resp.status_code in (302, 403)
        assert Organization.query.get(default_org.id) is not None


class TestTeamAdmin:
    def test_create_team(self, admin_client, db_session, default_org):
        resp = admin_client.post(
            "/teams/create",
            data={"organization_id": default_org.id, "name": "Second Team"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        team = Team.query.filter_by(
            organization_id=default_org.id, slug="second-team"
        ).first()
        assert team is not None

    def test_create_team_rejects_bad_input(
        self, admin_client, db_session, default_org, default_team
    ):
        resp = admin_client.post(
            "/teams/create",
            data={"organization_id": 999999, "name": "Ghost"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        resp = admin_client.post(
            "/teams/create",
            data={"organization_id": default_org.id,
                  "name": default_team.name},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert Team.query.filter_by(
            organization_id=default_org.id, slug=default_team.slug
        ).count() == 1

    def test_delete_empty_team(self, admin_client, db_session, default_org):
        team = Team(name="Temp", organization_id=default_org.id, slug="temp")
        db.session.add(team)
        db.session.commit()
        team_id = team.id
        resp = admin_client.post(
            f"/teams/{team_id}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert Team.query.get(team_id) is None

    def test_delete_team_blocked_with_games(
        self, admin_client, db_session, sample_game
    ):
        resp = admin_client.post(
            f"/teams/{sample_game.team_id}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert Team.query.get(sample_game.team_id) is not None

    def test_editor_cannot_manage_teams(
        self, auth_client, db_session, default_org
    ):
        resp = auth_client.post(
            "/teams/create",
            data={"organization_id": default_org.id, "name": "Nope"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        assert Team.query.filter_by(slug="nope").first() is None


class TestUserTeamAssignment:
    def _other_user(self, db_session, default_org):
        user = User(username="teammate", email="mate@test.com",
                    organization_id=default_org.id)
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        return user

    def test_assign_and_remove(self, admin_client, db_session, default_org,
                               default_team):
        user = self._other_user(db_session, default_org)
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert TeamAssignment.query.filter_by(
            user_id=user.id, team_id=default_team.id
        ).first() is not None
        # Idempotent re-assign.
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": True},
        )
        assert resp.get_json()["ok"] is True
        assert TeamAssignment.query.filter_by(user_id=user.id).count() == 1
        # Remove.
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": False},
        )
        assert resp.get_json()["ok"] is True
        assert TeamAssignment.query.filter_by(user_id=user.id).count() == 0

    def test_assign_invalid_team(self, admin_client, db_session, default_org):
        user = self._other_user(db_session, default_org)
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams", json={"team_id": 999999}
        )
        assert resp.status_code == 404

    def test_cannot_modify_own_teams(
        self, admin_client, db_session, admin_user, default_team
    ):
        resp = admin_client.post(
            f"/auth/users/{admin_user.id}/teams",
            json={"team_id": default_team.id, "assigned": False},
        )
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_cross_org_team_rejected(
        self, admin_client, db_session, default_org
    ):
        user = self._other_user(db_session, default_org)
        other_org = Organization(name="Other", slug="other")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id,
                          slug="other-team")
        db.session.add(other_team)
        db.session.commit()
        resp = admin_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": other_team.id, "assigned": True},
        )
        assert resp.status_code == 403
        assert TeamAssignment.query.filter_by(user_id=user.id).count() == 0

    def test_editor_cannot_assign(
        self, auth_client, db_session, default_org, default_team
    ):
        user = self._other_user(db_session, default_org)
        resp = auth_client.post(
            f"/auth/users/{user.id}/teams",
            json={"team_id": default_team.id, "assigned": True},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        assert TeamAssignment.query.filter_by(user_id=user.id).count() == 0
