"""Tests for the context-aware lineup optimizer backend slice.

Covers core.services.lineup_service.rank_lineups_for_context and the
GET /api/advanced/lineup-optimizer endpoint.
"""

import pytest

from core.models import Lineup, Organization, Team
from core.services.lineup_service import (
    OPTIMIZER_CONTEXTS,
    generate_lineup_hash,
    rank_lineups_for_context,
)


def make_lineup(db_session, team_id, players, possessions=45, net=5.0,
                ortg=115.0, drtg=110.0, fgm=20, fga=40, tpm=6,
                tov=5, ast=8, stl=3, blk=2, seconds=900):
    lineup = Lineup(
        lineup_hash=generate_lineup_hash(players),
        players=sorted(players),
        team_id=team_id,
        total_possessions=possessions,
        points_scored=100,
        points_allowed=95,
        ortg=ortg,
        drtg=drtg,
        net_rating=net,
        fgm=fgm,
        fga=fga,
        tpm=tpm,
        tpa=12,
        tov=tov,
        ast=ast,
        stl=stl,
        blk=blk,
        total_seconds=seconds,
        games_played=3,
        segment_count=4,
    )
    db_session.add(lineup)
    db_session.commit()
    return lineup


def make_other_team(db_session):
    org = Organization(name="Other Org", slug="other-org-opt")
    db_session.add(org)
    db_session.flush()
    team = Team(name="Other Team", slug="other-team-opt", organization_id=org.id)
    db_session.add(team)
    db_session.commit()
    return team


class TestRankLineupsForContext:
    @pytest.mark.integration
    def test_balanced_prefers_higher_net(self, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=15.0, possessions=50)
        make_lineup(db_session, default_team.id,
                    ["B1", "B2", "B3", "B4", "B5"], net=2.0, possessions=50)

        result = rank_lineups_for_context(default_team.id, "balanced")
        assert result["reason"] is None
        assert len(result["lineups"]) == 2
        assert result["lineups"][0]["net_rating"] == 15.0
        assert result["lineups"][1]["net_rating"] == 2.0
        assert "explanation" in result["lineups"][0]

    @pytest.mark.integration
    def test_minutes_floor_excludes_noise(self, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=40.0, possessions=5)
        good = make_lineup(db_session, default_team.id,
                           ["B1", "B2", "B3", "B4", "B5"], net=3.0, possessions=45)

        result = rank_lineups_for_context(default_team.id, "balanced")
        assert len(result["lineups"]) == 1
        assert result["lineups"][0]["lineup_id"] == good.id

    @pytest.mark.integration
    def test_each_context_returns_sensible_ordering(self, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=12.0, possessions=45,
                    ortg=120.0, drtg=108.0, fgm=22, fga=40, tpm=8,
                    tov=4, ast=10, stl=4, blk=2)
        make_lineup(db_session, default_team.id,
                    ["B1", "B2", "B3", "B4", "B5"], net=4.0, possessions=45,
                    ortg=106.0, drtg=102.0, fgm=16, fga=40, tpm=3,
                    tov=8, ast=5, stl=2, blk=1)

        for context in OPTIMIZER_CONTEXTS:
            result = rank_lineups_for_context(default_team.id, context)
            assert result["context"] == context
            assert result["reason"] is None
            assert len(result["lineups"]) == 2
            scores = [l["score"] for l in result["lineups"]]
            assert scores == sorted(scores, reverse=True)
            for entry in result["lineups"]:
                assert entry["explanation"]
                assert "net in" in entry["explanation"]
                assert "poss" in entry["explanation"]

    @pytest.mark.integration
    def test_context_flip_offense_vs_defense(self, db_session, default_team):
        # Same net (+15) so balanced ties; context weights must separate them.
        make_lineup(db_session, default_team.id,
                    ["O1", "O2", "O3", "O4", "O5"], net=15.0, possessions=50,
                    ortg=130.0, drtg=115.0, fgm=24, fga=40, tpm=9,
                    tov=6, ast=9, stl=2, blk=1)
        make_lineup(db_session, default_team.id,
                    ["D1", "D2", "D3", "D4", "D5"], net=15.0, possessions=50,
                    ortg=105.0, drtg=90.0, fgm=18, fga=40, tpm=3,
                    tov=5, ast=6, stl=6, blk=4)

        need_score = rank_lineups_for_context(default_team.id, "need_score")
        assert need_score["lineups"][0]["players"] == sorted(["O1", "O2", "O3", "O4", "O5"])

        need_stops = rank_lineups_for_context(default_team.id, "need_stops")
        assert need_stops["lineups"][0]["players"] == sorted(["D1", "D2", "D3", "D4", "D5"])

    @pytest.mark.integration
    def test_unknown_context_falls_back_to_balanced(self, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=7.0, possessions=30)
        result = rank_lineups_for_context(default_team.id, "not-a-context")
        assert result["context"] == "balanced"
        assert len(result["lineups"]) == 1

    @pytest.mark.integration
    def test_insufficient_data_returns_empty_with_reason(self, db_session, default_team):
        result = rank_lineups_for_context(default_team.id, "balanced")
        assert result["lineups"] == []
        assert result["reason"]

    @pytest.mark.integration
    def test_all_below_floor_returns_empty_with_reason(self, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=20.0, possessions=9)
        result = rank_lineups_for_context(default_team.id, "need_score")
        assert result["lineups"] == []
        assert result["reason"]

    @pytest.mark.integration
    def test_top_5_limit(self, db_session, default_team):
        for i in range(7):
            make_lineup(db_session, default_team.id,
                        [f"T{i}a", f"T{i}b", f"T{i}c", f"T{i}d", f"T{i}e"],
                        net=float(i), possessions=30)
        result = rank_lineups_for_context(default_team.id, "balanced")
        assert len(result["lineups"]) == 5
        assert result["lineups"][0]["net_rating"] == 6.0

    @pytest.mark.integration
    def test_team_scoping(self, db_session, default_team):
        other = make_other_team(db_session)
        make_lineup(db_session, other.id,
                    ["X1", "X2", "X3", "X4", "X5"], net=99.0, possessions=80)
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=5.0, possessions=40)

        result = rank_lineups_for_context(default_team.id, "balanced")
        assert len(result["lineups"]) == 1
        assert result["lineups"][0]["players"] == sorted(["A1", "A2", "A3", "A4", "A5"])


class TestLineupOptimizerAPI:
    @pytest.mark.integration
    def test_endpoint_returns_ranked_list(self, auth_client, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=11.0, possessions=45)
        resp = auth_client.get("/api/advanced/lineup-optimizer?context=need_score")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["context"] == "need_score"
        assert len(data["lineups"]) == 1
        assert "+11.0 net in 45 poss" in data["lineups"][0]["explanation"]

    @pytest.mark.integration
    def test_endpoint_default_context_balanced(self, auth_client, db_session, default_team):
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=6.0, possessions=30)
        resp = auth_client.get("/api/advanced/lineup-optimizer")
        assert resp.status_code == 200
        assert resp.get_json()["context"] == "balanced"

    @pytest.mark.integration
    def test_endpoint_invalid_context_400(self, auth_client):
        resp = auth_client.get("/api/advanced/lineup-optimizer?context=bogus")
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    @pytest.mark.integration
    def test_endpoint_empty_data(self, auth_client):
        resp = auth_client.get("/api/advanced/lineup-optimizer?context=vs_zone")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["lineups"] == []
        assert data["reason"]

    @pytest.mark.integration
    def test_endpoint_cross_team_denied(self, auth_client, db_session, default_team):
        other = make_other_team(db_session)
        make_lineup(db_session, other.id,
                    ["X1", "X2", "X3", "X4", "X5"], net=99.0, possessions=80)
        make_lineup(db_session, default_team.id,
                    ["A1", "A2", "A3", "A4", "A5"], net=5.0, possessions=40)

        # Attempt to switch into the other team via query param: the user is
        # not assigned there, so the decorator must ignore it (team-scoped).
        resp = auth_client.get(f"/api/advanced/lineup-optimizer?team_id={other.id}")
        assert resp.status_code == 200
        data = resp.get_json()
        players_seen = [p for l in data["lineups"] for p in l["players"]]
        assert "X1" not in players_seen
        assert "A1" in players_seen

    @pytest.mark.integration
    def test_endpoint_requires_auth(self, client, sample_game):
        resp = client.get("/api/advanced/lineup-optimizer")
        assert resp.status_code in [302, 401]
