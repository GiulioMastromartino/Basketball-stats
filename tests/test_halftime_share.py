"""Slice N1 — halftime one-tap share (text builder + route)."""

import json

from core.halftime_share import build_halftime_text, validate_halftime_payload
from core.models import WhatsAppGroup, db


def _payload(**overrides):
    base = {
        "opponent": "Rivals",
        "date": "2026-09-18",
        "team_score": 45,
        "opp_score": 42,
        "player_stats": {
            "Anna": {"points": 14, "fgm": 6, "fga": 10, "oreb": 1,
                     "dreb": 3, "ast": 2, "tov": 1},
            "Bea": {"points": 9, "fgm": 4, "fga": 8, "oreb": 0,
                    "dreb": 2, "ast": 4, "tov": 2},
        },
    }
    base.update(overrides)
    return base


class TestValidate:
    def test_valid(self):
        assert validate_halftime_payload(_payload()) == []

    def test_not_an_object(self):
        assert validate_halftime_payload([]) == ["payload must be a JSON object"]

    def test_missing_fields(self):
        errors = validate_halftime_payload({})
        assert "opponent is required" in errors
        assert "date is required" in errors
        assert "player_stats must be a non-empty object" in errors

    def test_bad_scores(self):
        errors = validate_halftime_payload(_payload(team_score="many"))
        assert "team_score must be an integer" in errors

    def test_non_string_fields_rejected(self):
        errors = validate_halftime_payload(_payload(opponent=123))
        assert "opponent is required" in errors
        errors = validate_halftime_payload(_payload(date=["2026-09-18"]))
        assert "date is required" in errors

    def test_non_dict_player_rows_rejected(self):
        errors = validate_halftime_payload(
            _payload(player_stats={"Anna": 12}))
        assert any("must be objects" in e for e in errors)


class TestBuildText:
    def test_contains_score_and_leaders(self):
        text = build_halftime_text(_payload())
        assert "HALFTIME" in text
        assert "45 - 42" in text
        assert "Anna: 14 PTS" in text
        assert "Team FG 10/18" in text

    def test_empty_stats_still_renders(self):
        text = build_halftime_text(_payload(player_stats={"Zed": {}}))
        assert "Rivals" in text


def _login(client, user, team):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["current_team_id"] = team.id
        sess["current_team_name"] = team.name


class TestRoute:
    def test_no_destination_returns_text(self, client, editor_user, default_team):
        _login(client, editor_user, default_team)
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload()),
                           content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sent"] is False
        assert "45 - 42" in data["text"]

    def test_invalid_payload_400(self, client, editor_user, default_team):
        _login(client, editor_user, default_team)
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps({}),
                           content_type="application/json")
        assert resp.status_code == 400

    def test_auditor_blocked(self, client, db_session, default_org, default_team):
        from core.models import User, OrganizationMembership, TeamAssignment
        auditor = User(username="ht_auditor", email="ht_auditor@t.com",
                       organization_id=default_org.id, is_auditor=True)
        auditor.set_password("password123")
        db_session.add(auditor)
        db_session.flush()
        db_session.add(OrganizationMembership(
            user_id=auditor.id, organization_id=default_org.id, is_gm=False))
        db_session.add(TeamAssignment(user_id=auditor.id, team_id=default_team.id))
        db_session.commit()
        _login(client, auditor, default_team)
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload()),
                           content_type="application/json")
        assert resp.status_code == 403

    def test_group_send_and_scoping(self, client, editor_user, default_team,
                                    db_session, default_org, mocker):
        from core.models import Team
        other = Team(name="Other", organization_id=default_org.id, slug="other-t")
        db_session.add(other)
        db_session.commit()
        mine = WhatsAppGroup(team_id=default_team.id, group_name="Staff",
                             group_wa_id="staff@g.us", active=True)
        theirs = WhatsAppGroup(team_id=other.id, group_name="Them",
                               group_wa_id="them@g.us", active=True)
        db_session.add_all([mine, theirs])
        db_session.commit()

        sent = mocker.patch(
            "core.services.whatsapp_service.send_text_message", return_value=True)
        _login(client, editor_user, default_team)

        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload(group_id=mine.id)),
                           content_type="application/json")
        assert resp.status_code == 200
        assert json.loads(resp.data)["sent"] is True
        assert sent.call_count == 1

        # Cross-team group ids must not leak.
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload(group_id=theirs.id)),
                           content_type="application/json")
        assert resp.status_code == 404

    def test_phone_send_failure_502(self, client, editor_user, default_team, mocker):
        mocker.patch(
            "core.services.whatsapp_service.send_text_message", return_value=False)
        _login(client, editor_user, default_team)
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload(phone="+39 333 000 0000")),
                           content_type="application/json")
        assert resp.status_code == 502
        assert json.loads(resp.data)["sent"] is False

    def test_default_group_resolution(self, client, editor_user,
                                      default_team, db_session, mocker):
        group = WhatsAppGroup(team_id=default_team.id, group_name="Staff",
                              group_wa_id="staff@g.us", active=True)
        db_session.add(group)
        db_session.commit()
        sent = mocker.patch(
            "core.services.whatsapp_service.send_text_message",
            return_value=True)
        _login(client, editor_user, default_team)
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload()),
                           content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sent"] is True
        assert data["channel"] == {"kind": "whatsapp_group",
                                   "group_id": group.id}
        assert sent.call_args.args[0] == "staff@g.us"

    def test_no_destination_no_group_returns_text(
            self, client, editor_user, default_team):
        _login(client, editor_user, default_team)
        resp = client.post("/reports/live/halftime-share",
                           data=json.dumps(_payload()),
                           content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["sent"] is False
        assert "45 - 42" in data["text"]
        assert "hint" in data
