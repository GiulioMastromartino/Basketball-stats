"""Live Game v2 per-event API tests (POST/GET /api/live-v2/events + undo)."""

import json

import pytest

from core.models import Game, GameEvent, Organization, ShotEvent, Team, db


def _shot_payload(game_id, **overrides):
    payload = {
        "game_id": game_id,
        "event_type": "2PT MADE",
        "player_name": "John Doe",
        "team": "HOME",
        "number": 7,
        "period": 1,
        "clock": "09:30",
        "x": 250,
        "y": 100,
        "zone": "PAINT",
        "points": 2,
        "client_event_id": "v2-test-1",
    }
    payload.update(overrides)
    return payload


class TestPostEvent:
    @pytest.mark.integration
    def test_shot_persists_game_event_and_shot_event(self, auth_client, sample_game):
        resp = auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["id"]
        assert data["server_timestamp"]
        assert data["duplicate"] is False

        event = GameEvent.query.get(data["id"])
        assert event is not None
        assert event.game_id == sample_game.id
        assert event.event_type == "SHOT_2PT"
        assert event.player_name == "John Doe"
        assert event.shot_attempt == "made"
        assert event.quarter == 1
        assert event.time_remaining == "9:30"
        assert event.x_loc == 250
        assert event.y_loc == 100
        assert event.zone == "PAINT"

        shots = ShotEvent.query.filter_by(game_id=sample_game.id).all()
        assert len(shots) == 1
        assert shots[0].shot_type == "2pt"
        assert shots[0].result == "made"
        assert shots[0].points == 2

    @pytest.mark.integration
    def test_non_shot_persists_game_event_only(self, auth_client, sample_game):
        resp = auth_client.post(
            "/api/live-v2/events",
            json=_shot_payload(
                sample_game.id,
                event_type="ASSIST",
                client_event_id="v2-test-assist",
            ),
        )
        assert resp.status_code == 201
        assert ShotEvent.query.filter_by(game_id=sample_game.id).count() == 0
        assert GameEvent.query.filter_by(game_id=sample_game.id).count() == 1

    @pytest.mark.integration
    def test_js_queue_shape_accepted(self, auth_client, sample_game):
        """The pending-queue payload shape from live_game_v2.js persists."""
        resp = auth_client.post(
            "/api/live-v2/events",
            json={
                "game_id": sample_game.id,
                "client_event_id": "v2-123-4",
                "player": "John Doe",
                "number": 7,
                "team": "HOME",
                "action": "3PT MISS",
                "period": 2,
                "clock": "05:00",
                "x": 100,
                "y": 300,
                "zone": "3PT",
                "points": 3,
            },
        )
        assert resp.status_code == 201
        data = json.loads(resp.data)
        event = GameEvent.query.get(data["id"])
        assert event.event_type == "SHOT_3PT"
        assert event.shot_attempt == "missed"
        shot = ShotEvent.query.filter_by(game_id=sample_game.id).one()
        assert shot.result == "missed"
        assert shot.points == 0

    @pytest.mark.integration
    def test_duplicate_client_event_id_ignored(self, auth_client, sample_game):
        first = auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        assert first.status_code == 201
        first_id = json.loads(first.data)["id"]

        second = auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        assert second.status_code == 200
        data = json.loads(second.data)
        assert data["id"] == first_id
        assert data["duplicate"] is True
        assert GameEvent.query.filter_by(game_id=sample_game.id).count() == 1
        assert ShotEvent.query.filter_by(game_id=sample_game.id).count() == 1

    @pytest.mark.integration
    def test_requires_auth(self, client, sample_game):
        resp = client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        assert resp.status_code in (302, 401)

    @pytest.mark.integration
    def test_cross_team_game_denied(self, auth_client, db_session, default_team):
        other_org = Organization(name="Rival Org", slug="rival-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(
            name="Rival Team", organization_id=other_org.id, slug="rival-team"
        )
        db.session.add(other_team)
        db.session.flush()
        other_game = Game(
            date="18-02-2024",
            opponent="Rivals",
            team_score=70,
            opponent_score=70,
            result="W",
            game_type="Season",
            sort_date="2024-02-18",
            source="MANUAL",
            team_id=other_team.id,
        )
        db.session.add(other_game)
        db.session.commit()

        resp = auth_client.post(
            "/api/live-v2/events", json=_shot_payload(other_game.id)
        )
        assert resp.status_code == 403
        assert GameEvent.query.filter_by(game_id=other_game.id).count() == 0

    @pytest.mark.integration
    def test_unknown_game_404(self, auth_client):
        resp = auth_client.post(
            "/api/live-v2/events", json=_shot_payload(999999)
        )
        assert resp.status_code == 404


class TestPostEventValidation:
    @pytest.mark.integration
    @pytest.mark.parametrize(
        "payload, expected",
        [
            ({"event_type": "2PT MADE"}, "missing game_id"),
            ({"game_id": "abc", "event_type": "2PT MADE"}, "non-integer game_id"),
            ({"game_id": 1}, "missing event type"),
            ({"game_id": 1, "event_type": "DUNK"}, "unknown event type"),
            (
                {"game_id": 1, "event_type": "2PT MADE"},
                "missing player for shot",
            ),
            (
                {"game_id": 1, "event_type": "TIME OUT"},
                "team event without player is ok",
            ),
        ],
    )
    def test_validation_cases(self, auth_client, sample_game, payload, expected):
        body = dict(payload)
        if body.get("game_id") == 1:
            body["game_id"] = sample_game.id
        if expected == "team event without player is ok":
            body.setdefault("player_name", None)
        if "player_name" not in body and expected not in (
            "missing player for shot",
            "team event without player is ok",
        ):
            body["player_name"] = "John Doe"
        resp = auth_client.post("/api/live-v2/events", json=body)
        if expected == "team event without player is ok":
            assert resp.status_code == 201, expected
        else:
            assert resp.status_code == 400, expected
            assert "error" in json.loads(resp.data)

    @pytest.mark.integration
    def test_bad_period_clock_coords_zone_points(
        self, auth_client, sample_game
    ):
        base = _shot_payload(sample_game.id)
        bad_bodies = [
            dict(base, period=0),
            dict(base, period="Q1"),
            dict(base, clock="half"),
            dict(base, clock="9-30"),
            dict(base, x="left"),
            dict(base, y=None, x="NaN-ish"),
            dict(base, zone="DUNKER"),
            dict(base, points="many"),
            dict(base, points=9),
        ]
        for i, body in enumerate(bad_bodies):
            body["client_event_id"] = f"v2-bad-{i}"
            resp = auth_client.post("/api/live-v2/events", json=body)
            assert resp.status_code == 400, body
        assert GameEvent.query.filter_by(game_id=sample_game.id).count() == 0

    @pytest.mark.integration
    def test_non_json_body_400(self, auth_client, sample_game):
        resp = auth_client.post(
            "/api/live-v2/events",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400


class TestListEvents:
    @pytest.mark.integration
    def test_game_log_resync(self, auth_client, sample_game):
        auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        auth_client.post(
            "/api/live-v2/events",
            json=_shot_payload(
                sample_game.id,
                event_type="FOUL",
                client_event_id="v2-test-foul",
                x=None,
                y=None,
                zone=None,
                points=None,
            ),
        )
        resp = auth_client.get(f"/api/live-v2/events?game_id={sample_game.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["game_id"] == sample_game.id
        assert [e["event_type"] for e in data["events"]] == ["SHOT_2PT", "FOUL"]
        assert data["events"][0]["server_timestamp"]

    @pytest.mark.integration
    def test_list_requires_game_id(self, auth_client):
        assert auth_client.get("/api/live-v2/events").status_code == 400

    @pytest.mark.integration
    def test_list_cross_team_denied(self, auth_client, db_session):
        other_org = Organization(name="Rival Org 2", slug="rival-org-2")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(
            name="Rival Team 2", organization_id=other_org.id, slug="rival-team-2"
        )
        db.session.add(other_team)
        db.session.flush()
        other_game = Game(
            date="19-02-2024",
            opponent="Rivals",
            team_score=70,
            opponent_score=70,
            result="W",
            game_type="Season",
            sort_date="2024-02-19",
            source="MANUAL",
            team_id=other_team.id,
        )
        db.session.add(other_game)
        db.session.commit()
        resp = auth_client.get(f"/api/live-v2/events?game_id={other_game.id}")
        assert resp.status_code == 403


class TestUndo:
    @pytest.mark.integration
    def test_undo_pops_last_event(self, auth_client, sample_game):
        auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        second = auth_client.post(
            "/api/live-v2/events",
            json=_shot_payload(
                sample_game.id, event_type="STEAL", client_event_id="v2-test-steal"
            ),
        )
        second_id = json.loads(second.data)["id"]

        resp = auth_client.post(
            "/api/live-v2/undo", json={"game_id": sample_game.id}
        )
        assert resp.status_code == 200
        assert json.loads(resp.data)["undone_id"] == second_id
        assert GameEvent.query.get(second_id) is None
        remaining = GameEvent.query.filter_by(game_id=sample_game.id).all()
        assert len(remaining) == 1

    @pytest.mark.integration
    def test_undo_removes_matching_shot(self, auth_client, sample_game):
        auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        assert ShotEvent.query.filter_by(game_id=sample_game.id).count() == 1
        resp = auth_client.post(
            "/api/live-v2/undo", json={"game_id": sample_game.id}
        )
        assert resp.status_code == 200
        assert ShotEvent.query.filter_by(game_id=sample_game.id).count() == 0

    @pytest.mark.integration
    def test_undo_removes_shot_matching_type_and_result(
        self, auth_client, sample_game
    ):
        """Same player/quarter 2PT-made + 3PT-missed: undo pops the 3PT miss."""
        auth_client.post(
            "/api/live-v2/events", json=_shot_payload(sample_game.id)
        )
        auth_client.post(
            "/api/live-v2/events",
            json=_shot_payload(
                sample_game.id,
                event_type="3PT MISS",
                client_event_id="v2-test-3miss",
                points=0,
            ),
        )
        assert ShotEvent.query.filter_by(game_id=sample_game.id).count() == 2
        resp = auth_client.post(
            "/api/live-v2/undo", json={"game_id": sample_game.id}
        )
        assert resp.status_code == 200
        remaining = ShotEvent.query.filter_by(game_id=sample_game.id).all()
        assert len(remaining) == 1
        assert remaining[0].shot_type == "2pt"
        assert remaining[0].result == "made"

    @pytest.mark.integration
    def test_undo_empty_log_404(self, auth_client, sample_game):
        resp = auth_client.post(
            "/api/live-v2/undo", json={"game_id": sample_game.id}
        )
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_undo_requires_game_id(self, auth_client):
        assert auth_client.post("/api/live-v2/undo", json={}).status_code == 400

    @pytest.mark.integration
    def test_undo_cross_team_denied(self, auth_client, db_session):
        other_org = Organization(name="Rival Org 3", slug="rival-org-3")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(
            name="Rival Team 3", organization_id=other_org.id, slug="rival-team-3"
        )
        db.session.add(other_team)
        db.session.flush()
        other_game = Game(
            date="20-02-2024",
            opponent="Rivals",
            team_score=70,
            opponent_score=70,
            result="W",
            game_type="Season",
            sort_date="2024-02-20",
            source="MANUAL",
            team_id=other_team.id,
        )
        db.session.add(other_game)
        db.session.commit()
        resp = auth_client.post(
            "/api/live-v2/undo", json={"game_id": other_game.id}
        )
        assert resp.status_code == 403
