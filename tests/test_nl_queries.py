"""Slice N4 — NL queries, play suggester, development goals."""

import json

from core.dev_goals import goal_progress, validate_goal


def _ask(client, query, game_type="Season"):
    return client.post("/coaching/nl-query",
                       data=json.dumps({"query": query, "game_type": game_type}),
                       content_type="application/json")


class TestNLQueries:
    def test_empty_query_400(self, admin_client):
        resp = admin_client.post("/coaching/nl-query",
                                 data=json.dumps({}),
                                 content_type="application/json")
        assert resp.status_code == 400

    def test_unknown_returns_examples(self, admin_client):
        data = json.loads(_ask(admin_client, "tell me a joke").data)
        assert data["intent"] == "unknown"
        assert data["data"]["examples"]

    def test_no_data_answers_gracefully(self, admin_client):
        for q in ("best lineup vs zone", "who is our top scorer?",
                  "how is our shooting?", "turnover problem?",
                  "how is our rebounding?", "recent form?"):
            resp = _ask(admin_client, q, game_type="ALL")
            assert resp.status_code == 200
            assert json.loads(resp.data)["answer"]

    def test_top_scorer(self, admin_client, sample_game, sample_player_stats):
        data = json.loads(_ask(admin_client, "who scores most?").data)
        assert data["intent"] == "top_scorer"
        assert data["data"]["player"] == "Jane Smith"

    def test_form(self, admin_client, sample_games):
        data = json.loads(_ask(admin_client, "how is our recent form?",
                               game_type="ALL").data)
        assert data["intent"] == "form"
        assert data["data"]["wins"] == 3

    def test_lineup_context_mapping(self, admin_client, sample_game):
        data = json.loads(_ask(admin_client, "best 5 to protect a lead").data)
        assert data["intent"] == "lineup"
        assert data["data"]["context"] == "protect_lead"


class TestPlaySuggester:
    def test_untried_plays_listed(self, admin_client, db_session, default_team):
        from core.models import Play
        db_session.add(Play(team_id=default_team.id, name="Horns",
                            play_type="Offense"))
        db_session.commit()
        resp = admin_client.get("/coaching/play-suggestions?situation=vs+zone")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["plays"][0]["verdict"] == "untried"
        assert "No tracked possessions" in data["plays"][0]["reason"]

    def test_ranked_by_ppp(self, admin_client, db_session, default_team,
                           sample_game):
        from core.models import Play, Possession
        good = Play(team_id=default_team.id, name="Winner", play_type="Offense")
        bad = Play(team_id=default_team.id, name="Loser", play_type="Offense")
        db_session.add_all([good, bad])
        db_session.flush()
        db_session.add_all([
            Possession(game_id=sample_game.id, start_event_id=1,
                       quarter=1, points=2, play_id=good.id),
            Possession(game_id=sample_game.id, start_event_id=2,
                       quarter=1, points=0, play_id=bad.id),
        ])
        db_session.commit()
        data = json.loads(admin_client.get(
            "/coaching/play-suggestions").data)
        assert [p["name"] for p in data["plays"]] == ["Winner", "Loser"]

    def test_bad_quarter_400(self, admin_client):
        assert admin_client.get(
            "/coaching/play-suggestions?quarter=late").status_code == 400


class TestDevGoals:
    def test_validate(self):
        assert validate_goal("Anna", "ft_percent", 75, 5) == []
        assert "player_name is required" in validate_goal("", "ft_percent", 75, 5)
        assert any("metric must be" in e
                   for e in validate_goal("Anna", "dunks", 3, 5))
        assert any("window must be" in e
                   for e in validate_goal("Anna", "points", 10, 99))

    def test_crud_and_progress(self, admin_client, sample_game,
                               sample_player_stats):
        # Jane avg over sample_game: check via progress after create.
        resp = admin_client.post(
            "/coaching/dev-goals",
            data=json.dumps({"player_name": "Jane Smith",
                             "metric": "points", "target": 20, "window": 5}),
            content_type="application/json")
        assert resp.status_code == 201
        created = json.loads(resp.data)
        assert created["current"] == 22.0
        assert created["achieved"] is True
        goal_id = created["goal_id"]

        data = json.loads(admin_client.get("/coaching/dev-goals").data)
        assert len(data["goals"]) == 1

        assert admin_client.delete(
            f"/coaching/dev-goals/{goal_id}").status_code == 200
        assert json.loads(admin_client.get(
            "/coaching/dev-goals").data)["goals"] == []

    def test_lower_is_better(self, db_session, default_team, sample_game,
                             sample_player_stats):
        from core.models import DevelopmentGoal
        goal = DevelopmentGoal(team_id=default_team.id, player_name="John Doe",
                               metric="tov", target=3, window=5)
        db_session.add(goal)
        db_session.commit()
        progress = goal_progress(goal)
        assert progress["current"] == 2.0
        assert progress["achieved"] is True

    def test_invalid_create_400(self, admin_client):
        resp = admin_client.post(
            "/coaching/dev-goals",
            data=json.dumps({"player_name": "Anna", "metric": "dunks",
                             "target": 3}),
            content_type="application/json")
        assert resp.status_code == 400

    def test_auditor_cannot_create(self, client, db_session, default_org,
                                   default_team):
        from core.models import User, OrganizationMembership, TeamAssignment
        auditor = User(username="nl_auditor", email="nl_auditor@t.com",
                       organization_id=default_org.id, is_auditor=True)
        auditor.set_password("password123")
        db_session.add(auditor)
        db_session.flush()
        db_session.add(OrganizationMembership(
            user_id=auditor.id, organization_id=default_org.id, is_gm=False))
        db_session.add(TeamAssignment(user_id=auditor.id, team_id=default_team.id))
        db_session.commit()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(auditor.id)
            sess["_fresh"] = True
            sess["current_team_id"] = default_team.id
        resp = client.post("/coaching/dev-goals",
                           data=json.dumps({"player_name": "Anna",
                                            "metric": "points", "target": 10}),
                           content_type="application/json")
        assert resp.status_code == 403
