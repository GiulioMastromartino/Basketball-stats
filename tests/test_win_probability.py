"""Win probability backend slice tests (model + curve + endpoint)."""

import json

import pytest

from core.models import Game, GameEvent, Organization, Team, db
from core.win_probability import build_win_curve, win_probability


def _event(game_id, event_type, margin=None, quarter=1, clock="09:00",
           shot_attempt=None, detail=None, game_seconds=None):
    event = GameEvent(
        game_id=game_id,
        event_type=event_type,
        player_name="John Doe",
        quarter=quarter,
        time_remaining=clock,
        score_margin=margin,
        game_seconds=game_seconds,
        shot_attempt=shot_attempt,
        detail=detail,
        timestamp=1000,
    )
    db.session.add(event)
    return event


class TestWinProbabilityModel:
    @pytest.mark.unit
    def test_tied_late_is_coin_flip(self):
        assert win_probability(0, 60) == pytest.approx(0.5)

    @pytest.mark.unit
    def test_big_lead_late_is_certain(self):
        assert win_probability(15, 60) > 0.9

    @pytest.mark.unit
    def test_big_deficit_late_is_doomed(self):
        assert win_probability(-15, 60) < 0.1

    @pytest.mark.unit
    def test_symmetry(self):
        assert win_probability(8, 300) == pytest.approx(
            1 - win_probability(-8, 300)
        )

    @pytest.mark.unit
    def test_clamps(self):
        assert win_probability(150, 0) == 0.99
        assert win_probability(-150, 0) == 0.01
        assert win_probability(40, 2400) <= 0.99
        assert win_probability(-40, 2400) >= 0.01

    @pytest.mark.unit
    def test_possession_bonus_orders(self):
        assert (
            win_probability(0, 300, possession=True)
            > win_probability(0, 300)
            > win_probability(0, 300, possession=False)
        )

    @pytest.mark.unit
    def test_ot_steepens_curve_for_leader(self):
        assert win_probability(8, 300, period=5) > win_probability(8, 300, period=4)

    @pytest.mark.unit
    def test_ot_steepens_curve_for_trailer(self):
        assert win_probability(-8, 300, period=5) < win_probability(-8, 300, period=4)

    @pytest.mark.unit
    def test_lead_grows_with_margin(self):
        assert win_probability(10, 600) > win_probability(5, 600) > win_probability(0, 600)

    @pytest.mark.unit
    def test_buzzer_state_is_certain(self):
        assert win_probability(1, 0) == 0.99
        assert win_probability(-1, 0) == 0.01
        assert win_probability(0, 0) == 0.5


class TestBuildWinCurve:
    @pytest.mark.integration
    def test_curve_from_stored_margins_ends_at_outcome(self, db_session, sample_game):
        sample_game.team_score = 80
        sample_game.opponent_score = 70
        db.session.add(_event(sample_game.id, "SHOT_2PT", margin=2, clock="09:00", shot_attempt="made"))
        db.session.add(_event(sample_game.id, "SHOT_3PT", margin=5, clock="07:30", shot_attempt="made"))
        db.session.add(_event(sample_game.id, "OPP_SCORE", margin=3, clock="06:00",
                              detail=json.dumps({"points": 2})))
        db.session.add(_event(sample_game.id, "SHOT_2PT", margin=5, clock="04:00", shot_attempt="made"))
        db.session.commit()

        curve = build_win_curve(sample_game.id, sample_game.team_id)
        assert len(curve) == 4
        assert all(set(p) == {"clock_label", "margin", "prob"} for p in curve)
        # Book score wins: final point resynced to the actual +10 outcome.
        assert curve[-1]["margin"] == 10
        assert curve[-1]["prob"] == 0.99
        # Monotonic-ish: leader's probability never collapses mid-game.
        assert all(p["prob"] > 0.5 for p in curve)

    @pytest.mark.integration
    def test_curve_derives_margins_from_live_v2_scoring_events(
        self, db_session, sample_game
    ):
        """Live-v2 rows store no score_margin: deltas must reconstruct it."""
        sample_game.team_score = 4
        sample_game.opponent_score = 2
        db.session.add(_event(sample_game.id, "SHOT_2PT", clock="09:00", shot_attempt="made"))
        db.session.add(_event(sample_game.id, "OPP_SCORE", clock="08:00",
                              detail=json.dumps({"points": 2})))
        db.session.add(_event(sample_game.id, "SHOT_2PT", clock="07:00", shot_attempt="made"))
        db.session.commit()

        curve = build_win_curve(sample_game.id, sample_game.team_id)
        assert [p["margin"] for p in curve] == [2, 0, 2]
        assert curve[-1]["margin"] == 2  # resynced to the 4-2 book score
        assert curve[-1]["prob"] == round(win_probability(2, 0), 4) == 0.99

    @pytest.mark.integration
    def test_curve_falls_back_to_final_score_only(self, db_session, sample_game):
        final_margin = sample_game.team_score - sample_game.opponent_score
        curve = build_win_curve(sample_game.id, sample_game.team_id)
        assert curve == [
            {
                "clock_label": "Final",
                "margin": final_margin,
                "prob": round(win_probability(final_margin, 0), 4),
            }
        ]

    @pytest.mark.integration
    def test_curve_rejects_cross_team_lookup(self, db_session, sample_game):
        with pytest.raises(LookupError):
            build_win_curve(sample_game.id, team_id=sample_game.team_id + 9999)

    @pytest.mark.integration
    def test_curve_rejects_unknown_game(self, db_session, default_team):
        with pytest.raises(LookupError):
            build_win_curve(999999, default_team.id)


class TestWinProbabilityEndpoint:
    @pytest.mark.integration
    def test_endpoint_returns_curve(self, auth_client, sample_game):
        resp = auth_client.get(f"/api/live-v2/win-probability?game_id={sample_game.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["game_id"] == sample_game.id
        assert data["curve"]
        assert data["current_prob"] == data["curve"][-1]["prob"]
        assert set(data["curve"][0]) == {"clock_label", "margin", "prob"}

    @pytest.mark.integration
    def test_endpoint_missing_game_id_400(self, auth_client):
        assert auth_client.get("/api/live-v2/win-probability").status_code == 400

    @pytest.mark.integration
    def test_endpoint_bad_game_id_400(self, auth_client):
        assert (
            auth_client.get("/api/live-v2/win-probability?game_id=abc").status_code == 400
        )

    @pytest.mark.integration
    def test_endpoint_unknown_game_404(self, auth_client):
        assert (
            auth_client.get("/api/live-v2/win-probability?game_id=999999").status_code
            == 404
        )

    @pytest.mark.integration
    def test_endpoint_cross_team_game_404(self, auth_client, db_session):
        other_org = Organization(name="WP Rival Org", slug="wp-rival-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(
            name="WP Rival Team", organization_id=other_org.id, slug="wp-rival-team"
        )
        db.session.add(other_team)
        db.session.flush()
        other_game = Game(
            date="21-02-2024",
            opponent="Rivals",
            team_score=70,
            opponent_score=70,
            result="W",
            game_type="Season",
            sort_date="2024-02-21",
            source="MANUAL",
            team_id=other_team.id,
        )
        db.session.add(other_game)
        db.session.commit()
        assert (
            auth_client.get(
                f"/api/live-v2/win-probability?game_id={other_game.id}"
            ).status_code
            == 404
        )

    @pytest.mark.integration
    def test_endpoint_requires_auth(self, client, sample_game):
        assert (
            client.get(
                f"/api/live-v2/win-probability?game_id={sample_game.id}"
            ).status_code
            in (302, 401)
        )
