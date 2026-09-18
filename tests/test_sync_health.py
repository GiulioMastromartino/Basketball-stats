"""Deeper sync — diffs, cross-checks, sync-health page, import webhook."""

import json

from core.sync_diff import (
    cross_check_game_scores,
    diff_games,
    diff_standings,
    roster_cross_check,
)


def _standing(team, pos, pts=10, won=5, lost=1):
    return {"team": team, "position": pos, "points": pts,
            "won": won, "lost": lost, "scored": 400, "conceded": 350}


class TestDiffStandings:
    def test_moved_and_score_changes(self):
        old = [_standing("Alpha", 1, pts=12), _standing("Beta", 2, pts=10)]
        new = [_standing("Beta", 1, pts=12), _standing("Alpha", 2, pts=12)]
        diff = diff_standings(old, new)
        assert diff["added"] == [] and diff["removed"] == []
        assert {m["team"]: m["delta"] for m in diff["moved"]} == {
            "Beta": 1, "Alpha": -1}
        assert any(c["team"] == "Beta" and c["field"] == "points"
                   for c in diff["score_changes"])

    def test_added_removed(self):
        diff = diff_standings([_standing("Alpha", 1)], [_standing("Gamma", 1)])
        assert [r["team"] for r in diff["added"]] == ["Gamma"]
        assert [r["team"] for r in diff["removed"]] == ["Alpha"]

    def test_empty(self):
        assert diff_standings([], []) == {"added": [], "removed": [],
                                          "moved": [], "score_changes": []}


class TestDiffGames:
    def test_score_correction(self):
        old = [{"game_date": "2026-01-10", "home": "A", "away": "B",
                "home_score": 78, "away_score": 70}]
        new = [{"game_date": "2026-01-10", "home": "A", "away": "B",
                "home_score": 80, "away_score": 70}]
        diff = diff_games(old, new)
        assert diff["corrections"] == [{"game": "2026-01-10|a|b",
                                        "old": "78-70", "new": "80-70"}]

    def test_unplayed_scores_ignored(self):
        old = [{"game_date": "2026-01-10", "home": "A", "away": "B",
                "home_score": None, "away_score": None}]
        new = [{"game_date": "2026-01-10", "home": "A", "away": "B",
                "home_score": 80, "away_score": 70}]
        assert diff_games(old, new)["corrections"] == []


class TestRosterCheck:
    def test_stat_only_and_without_stats(self):
        result = roster_cross_check(["Anna", "Bea", "Cid"],
                                    ["anna", "Bea", "Zed"])
        assert result["matched"] == ["Anna", "Bea"]
        assert result["stat_only"] == ["Zed"]
        assert result["without_stats"] == ["Cid"]


class TestScoreCrossCheck:
    def test_mismatch_found(self):
        internal = [{"date": "10/01/2026", "opponent": "Rivals",
                     "team_score": 78, "opponent_score": 70}]
        external = [{"data": "10/01/2026", "casa": "Sharks", "ospite": "Rivals",
                     "pc": 80, "po": 70}]
        mism = cross_check_game_scores("Sharks", internal, external)
        assert len(mism) == 1
        assert mism[0]["internal"] == "78-70"
        assert mism[0]["external"] == "80-70"

    def test_match_no_mismatch(self):
        internal = [{"date": "2026-01-10", "opponent": "Rivals",
                     "team_score": 80, "opponent_score": 70}]
        external = [{"game_date": "2026-01-10", "home": "Sharks",
                     "away": "Rivals", "home_score": 80, "away_score": 70}]
        assert cross_check_game_scores("Sharks", internal, external) == []


class TestSyncHealthRoute:
    def test_page_returns_all_sections(self, admin_client, sample_game):
        resp = admin_client.get("/analytics/championship/sync-health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        for key in ("health", "standings_diff", "games_diff",
                    "score_mismatches", "roster_check"):
            assert key in data

    def test_roster_check_flags_stat_only(self, admin_client, sample_game,
                                          sample_player_stat):
        data = json.loads(admin_client.get(
            "/analytics/championship/sync-health").data)
        assert "John Doe" in data["roster_check"]["stat_only"]


class TestImportWebhook:
    def _body(self):
        return {
            "game": {"date": "17-02-2024", "sort_date": "2024-02-17",
                     "opponent": "Webhook Rivals", "team_score": 80,
                     "opponent_score": 70, "result": "W",
                     "game_type": "Season"},
            "player_stats": [{"player_name": "Anna", "points": 20}],
        }

    def test_import_201(self, admin_client):
        resp = admin_client.post("/api/v1/games/import",
                                 data=json.dumps(self._body()),
                                 content_type="application/json")
        assert resp.status_code == 201
        assert json.loads(resp.data)["opponent"] == "Webhook Rivals"

    def test_duplicate_409(self, admin_client):
        admin_client.post("/api/v1/games/import",
                          data=json.dumps(self._body()),
                          content_type="application/json")
        resp = admin_client.post("/api/v1/games/import",
                                 data=json.dumps(self._body()),
                                 content_type="application/json")
        assert resp.status_code == 409

    def test_missing_fields_400(self, admin_client):
        resp = admin_client.post("/api/v1/games/import",
                                 data=json.dumps({"game": {}}),
                                 content_type="application/json")
        assert resp.status_code == 400

    def test_auditor_blocked(self, client, db_session, default_org,
                             default_team):
        from core.models import User, OrganizationMembership, TeamAssignment
        auditor = User(username="sync_auditor", email="sync_auditor@t.com",
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
        resp = client.post("/api/v1/games/import",
                           data=json.dumps(self._body()),
                           content_type="application/json")
        assert resp.status_code == 403
