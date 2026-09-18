"""Slice N2 — season planner + drill suggester (+ coaching routes)."""

import json

from core.drill_suggester import suggest_drills, weakest_factor
from core.season_plan import build_season_plan, load_flag, month_column


class TestSeasonPlanPure:
    def test_month_columns(self):
        assert month_column(9) == 0
        assert month_column(6) == 9
        assert month_column(7) is None
        assert month_column(8) is None

    def test_load_flags(self):
        assert load_flag(10) == "high"
        assert load_flag(5) == "normal"
        assert load_flag(1) == "development"

    def test_calendar_shape_and_summary(self):
        plan = build_season_plan({10: 9, 3: 1}, season_label="2025/26")
        assert [m["month"] for m in plan["months"]][:2] == ["Sep", "Oct"]
        assert len(plan["months"]) == 10
        october = plan["months"][1]
        assert october["load"] == "high"
        assert "Rotate 10" in october["rotation_guidance"]
        assert plan["summary"]["total_games"] == 10
        assert plan["summary"]["peak_month"] == "Oct"
        assert "Mar" in plan["summary"]["development_months"]


class TestDrillSuggester:
    def test_weakest_factor_picks_shortfall(self):
        factors = {"efg_pct": 55.0, "tov_pct": 22.0,
                   "orb_pct": 30.0, "ft_rate": 0.30}
        assert weakest_factor(factors) == "tov_pct"

    def test_suggest_three_linked_drills(self):
        factors = {"efg_pct": 38.0, "tov_pct": 12.0,
                   "orb_pct": 30.0, "ft_rate": 0.30}
        result = suggest_drills(factors)
        assert result["weakest"] == "efg_pct"
        assert len(result["drills"]) == 2  # only 2 shooting drills in library
        assert all("play_types" in d for d in result["drills"])

    def test_empty_factors(self):
        assert suggest_drills({}) == {"weakest": None, "label": None, "drills": []}


class TestCoachingRoutes:
    def test_season_plan_route(self, admin_client, sample_games):
        resp = admin_client.get("/coaching/season-plan")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data["months"]) == 10
        assert data["summary"]["total_games"] == 3

    def test_drill_suggestions_no_games(self, admin_client):
        resp = admin_client.get("/coaching/drill-suggestions")
        assert resp.status_code == 200
        assert json.loads(resp.data)["drills"] == []

    def test_drill_suggestions_with_games(self, admin_client, sample_games,
                                          sample_player_stats):
        resp = admin_client.get("/coaching/drill-suggestions?last_n=5")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["games_used"] == 4  # 3 sample_games + sample_game
        assert data["weakest"] in ("efg_pct", "tov_pct", "orb_pct", "ft_rate")

    def test_play_effectiveness_empty(self, admin_client):
        resp = admin_client.get("/coaching/play-effectiveness")
        assert resp.status_code == 200
        assert json.loads(resp.data) == {"plays": [], "count": 0}

    def test_play_effectiveness_ranked(self, admin_client, db_session,
                                       default_team, sample_game):
        from core.models import Play, Possession
        play = Play(team_id=default_team.id, name="Horns",
                    play_type="Offense")
        db_session.add(play)
        db_session.flush()
        db_session.add_all([
            Possession(game_id=sample_game.id, start_event_id=1,
                       team_possession=True, quarter=1, points=2,
                       play_id=play.id),
            Possession(game_id=sample_game.id, start_event_id=2,
                       team_possession=True, quarter=2, points=0,
                       play_id=play.id),
        ])
        db_session.commit()
        resp = admin_client.get("/coaching/play-effectiveness")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] == 1
        row = data["plays"][0]
        assert row["ppp"] == 1.0
        assert row["by_quarter"]["1"]["ppp"] == 2.0
        assert row["verdict"] == "keep"
