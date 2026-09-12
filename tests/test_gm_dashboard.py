"""Regression tests for GM dashboard without an organization.

Covers the dev/no-auth mode (NoAuthUser) and real users: the dashboard
must never 500 when no organization can be resolved.
"""

import pytest

from core.models import Organization, Team, db
from web import create_app


def _dev_app(monkeypatch):
    """Fresh app with auth disabled (dev mode: NoAuthUser acts as GM)."""
    monkeypatch.setenv("DISABLE_AUTH", "1")
    app = create_app("testing")
    app.config["WTF_CSRF_ENABLED"] = False
    return app


class TestGMDashboardWithoutOrg:
    def test_dev_mode_empty_db_redirects(self, monkeypatch):
        app = _dev_app(monkeypatch)
        client = app.test_client()
        ctx = app.app_context()
        ctx.push()
        db.create_all()
        try:
            resp = client.get("/gm/dashboard", follow_redirects=False)
            assert resp.status_code in (200, 302)
        finally:
            db.session.remove()
            db.drop_all()
            ctx.pop()

    def test_dev_mode_lists_org_teams(self, monkeypatch):
        app = _dev_app(monkeypatch)
        client = app.test_client()
        ctx = app.app_context()
        ctx.push()
        db.create_all()
        try:
            org = Organization(name="Dev Org", slug="dev-org")
            db.session.add(org)
            db.session.flush()
            db.session.add(
                Team(name="Dev Team", organization_id=org.id, slug="dev-team")
            )
            db.session.commit()
            resp = client.get("/gm/dashboard")
            assert resp.status_code == 200
            assert b"Dev Team" in resp.data
        finally:
            db.session.remove()
            db.drop_all()
            ctx.pop()

    def test_gm_with_org_still_works(self, admin_client, default_team):
        resp = admin_client.get("/gm/dashboard")
        assert resp.status_code == 200

    def test_dev_mode_whatsapp_groups_allowed(self, monkeypatch):
        from core.models import WhatsAppGroup

        app = _dev_app(monkeypatch)
        client = app.test_client()
        ctx = app.app_context()
        ctx.push()
        db.create_all()
        try:
            org = Organization(name="Dev Org", slug="dev-org")
            db.session.add(org)
            db.session.flush()
            team = Team(name="Dev Team", organization_id=org.id, slug="dev-team")
            db.session.add(team)
            db.session.commit()
            resp = client.get(f"/auth/admin/teams/{team.id}/whatsapp-groups")
            assert resp.status_code == 200
            resp = client.post(
                f"/auth/admin/teams/{team.id}/whatsapp-groups",
                data={"action": "add", "group_name": "Parents",
                      "group_wa_id": "12345@g.us"},
                follow_redirects=False,
            )
            assert resp.status_code == 302
            assert WhatsAppGroup.query.filter_by(team_id=team.id).count() == 1
        finally:
            db.session.remove()
            db.drop_all()
            ctx.pop()
