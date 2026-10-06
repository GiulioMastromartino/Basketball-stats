"""
Regression tests for the save-live-game fixes.

Covers:
- auditor POST /live-game/save -> 403, no Game created
- generic 500 hides exception text, includes request_id
- cross-tenant play_id is never hijacked; whitespace play_name creates no Play
- strict validation (impossible date, missing opponent, garbage scores,
  non-dict rows, duplicate guard)
"""

import copy
import json

import pytest

from core.models import (
    Game,
    GameEvent,
    OrganizationMembership,
    Play,
    ShotEvent,
    Team,
    TeamAssignment,
    User,
)


def _base_payload(opponent="Regression Opp", date="2024-03-10"):
    """Minimal valid LIVE-style payload with unique opponent/date."""
    return {
        "date": date,
        "opponent": opponent,
        "team_score": 75,
        "opponent_score": 68,
        "game_type": "Season",
        "player_stats": {
            "John Doe": {
                "points": 18,
                "fgm": 7,
                "fga": 14,
                "tpm": 2,
                "tpa": 5,
                "ftm": 2,
                "fta": 3,
                "oreb": 1,
                "dreb": 4,
                "ast": 3,
                "stl": 2,
                "blk": 1,
                "tov": 2,
                "pf": 3,
                "plus_minus": 8,
                "minutes": "24:30",
            }
        },
        "shot_locations": [
            {
                "shooter": "John Doe",
                "type": "2pt",
                "result": "made",
                "points": 2,
                "x": 250,
                "y": 100,
                "quarter": 1,
                "play_id": None,
            }
        ],
        "game_events": [
            {
                "type": "SHOT_2PT",
                "player": "John Doe",
                "quarter": 1,
                "clockSeconds": 90,
                "time_remaining": "8:30",
                "score_margin": 2,
                "game_seconds": 90,
                "possession_number": 1,
                "timestamp": 1708176000000,
            }
        ],
    }


class TestAuditorSaveBlocked:
    """Auditors have read-only access to the live-game save endpoint."""

    @pytest.mark.integration
    def test_auditor_post_save_403_no_game(
        self, client, db_session, default_org, default_team, live_game_payload
    ):
        auditor = User(
            username="auditor_save",
            email="auditor_save@test.com",
            organization_id=default_org.id,
            is_auditor=True,
        )
        auditor.set_password("password123")
        db_session.add(auditor)
        db_session.flush()
        db_session.add(
            OrganizationMembership(
                user_id=auditor.id,
                organization_id=default_org.id,
                is_gm=False,
            )
        )
        db_session.add(
            TeamAssignment(
                user_id=auditor.id, team_id=default_team.id, is_coach=False
            )
        )
        db_session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(auditor.id)
            sess["_fresh"] = True
            sess["current_team_id"] = default_team.id
            sess["current_team_name"] = default_team.name

        response = client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        assert response.status_code == 403
        assert "read-only" in response.get_data(as_text=True).lower()
        assert Game.query.filter_by(opponent="Test Team").first() is None


class TestGeneric500:
    """Unexpected failures return a generic body without leaking internals."""

    @pytest.mark.integration
    def test_500_hides_exception_and_has_request_id(
        self, auth_client, live_game_payload, monkeypatch
    ):
        import web.routes.main as main_routes

        def _boom(*args, **kwargs):
            raise RuntimeError("secret")

        monkeypatch.setattr(
            main_routes, "create_game_from_live_data", _boom
        )

        response = auth_client.post(
            "/live-game/save", json=live_game_payload, content_type="application/json"
        )

        assert response.status_code == 500
        body_text = response.get_data(as_text=True)
        data = json.loads(response.data)
        assert "Failed to save game" in body_text
        assert "secret" not in body_text
        assert "request_id" in data


class TestCrossTenantPlay:
    """A payload must never resolve events to another team's Play."""

    @pytest.mark.integration
    def test_cross_team_play_id_not_hijacked(
        self, auth_client, db_session, default_org, default_team
    ):
        team_b = Team(
            name="Team B", organization_id=default_org.id, slug="team-b-x"
        )
        db_session.add(team_b)
        db_session.commit()
        play_b = Play(
            name="Secret Play",
            team_id=team_b.id,
            play_type="Offense",
            source="manual",
        )
        db_session.add(play_b)
        db_session.commit()
        play_b_id = play_b.id

        payload = _base_payload(opponent="Cross Tenant Opp", date="2024-03-01")
        payload["shot_locations"][0]["play_id"] = play_b_id
        payload["game_events"][0]["play_id"] = play_b_id

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        game = Game.query.filter_by(opponent="Cross Tenant Opp").first()
        assert game is not None
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        event = GameEvent.query.filter_by(game_id=game.id).first()
        assert shot is not None
        assert event is not None
        assert shot.play_id != play_b_id
        assert event.play_id != play_b_id
        for resolved_id in (shot.play_id, event.play_id):
            if resolved_id is not None:
                owner = Play.query.filter_by(id=resolved_id).first()
                assert owner is not None
                assert owner.team_id == default_team.id

    @pytest.mark.integration
    def test_whitespace_play_name_creates_no_play(self, auth_client, db_session):
        payload = _base_payload(opponent="Whitespace Play Opp", date="2024-03-02")
        payload["shot_locations"][0]["play_name"] = "   "
        payload["game_events"][0]["detail"] = {"play_name": "   "}

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        game = Game.query.filter_by(opponent="Whitespace Play Opp").first()
        assert game is not None
        shot = ShotEvent.query.filter_by(game_id=game.id).first()
        assert shot is not None
        assert shot.play_id is None
        assert Play.query.filter_by(name="").first() is None
        assert Play.query.filter_by(name="   ").first() is None


class TestSaveValidation:
    """Strict validation: bad dates/opponents rejected, garbage never 500s."""

    @pytest.mark.integration
    def test_impossible_date_400(self, auth_client):
        payload = _base_payload(opponent="Bad Date Opp", date="2024-13-40")

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code == 400

    @pytest.mark.integration
    def test_missing_opponent_400(self, auth_client):
        payload = _base_payload(opponent="Will Be Removed", date="2024-03-04")
        payload.pop("opponent")

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code == 400

        blank = _base_payload(opponent="   ", date="2024-03-05")
        response = auth_client.post(
            "/live-game/save", json=blank, content_type="application/json"
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_garbage_scores_do_not_500(self, auth_client, db_session):
        payload = _base_payload(opponent="Garbage Score Opp", date="2024-03-06")
        payload["team_score"] = "abc"
        payload["opponent_score"] = "xyz"

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code != 500
        assert response.status_code in [200, 201, 400]
        if response.status_code in [200, 201]:
            game = Game.query.filter_by(opponent="Garbage Score Opp").first()
            assert game is not None
            assert game.team_score == 0
            assert game.opponent_score == 0

    @pytest.mark.integration
    def test_non_dict_rows_skipped(self, auth_client, db_session):
        payload = _base_payload(opponent="Non Dict Opp", date="2024-03-07")
        payload["player_stats"]["Ghost"] = "garbage"
        payload["shot_locations"].extend(["garbage", 42, None])
        payload["game_events"].extend(["junk", None, 42])

        response = auth_client.post(
            "/live-game/save", json=payload, content_type="application/json"
        )

        assert response.status_code in [200, 201]
        game = Game.query.filter_by(opponent="Non Dict Opp").first()
        assert game is not None
        assert len(ShotEvent.query.filter_by(game_id=game.id).all()) == 1
        assert len(GameEvent.query.filter_by(game_id=game.id).all()) == 1

    @pytest.mark.integration
    def test_duplicate_post_rejected(self, auth_client):
        payload = _base_payload(opponent="Dupe Opp", date="2024-03-08")

        first = auth_client.post(
            "/live-game/save", json=copy.deepcopy(payload),
            content_type="application/json",
        )
        assert first.status_code in [200, 201]

        second = auth_client.post(
            "/live-game/save", json=copy.deepcopy(payload),
            content_type="application/json",
        )

        assert second.status_code in [400, 409]
        assert "already exists" in second.get_data(as_text=True).lower()
