"""
Tests for the Trend Alerts slice (dashboard performance deltas).

Covers AnalyticsService.compute_trend_alerts and the
GET /api/advanced/trend-alerts endpoint.
"""

import pytest

from core.models import Game, PlayerStat
from core.services.analytics_service import AnalyticsService


def _add_game(db_session, team, idx, stat):
    """Create one game with a single aggregated player-stat row."""
    game = Game(
        date=f"{10 + idx:02d}-03-2024",
        opponent=f"Trend Opp {idx}",
        team_score=stat["points"],
        opponent_score=60,
        result="W",
        game_type="Season",
        sort_date=f"2024-03-{10 + idx:02d}",
        source="MANUAL",
        team_id=team.id,
    )
    db_session.add(game)
    db_session.flush()
    db_session.add(
        PlayerStat(
            game_id=game.id,
            player_name="Trend Player",
            minutes="20:00",
            points=stat["points"],
            fgm=stat["fgm"],
            fga=stat["fga"],
            tpm=stat["tpm"],
            tpa=stat["tpa"],
            ftm=stat["ftm"],
            fta=stat["fta"],
            oreb=stat["oreb"],
            dreb=stat["dreb"],
            reb=stat["oreb"] + stat["dreb"],
            ast=5,
            stl=1,
            blk=0,
            tov=stat["tov"],
            pf=2,
            plus_minus=5,
        )
    )
    db_session.commit()
    return game


GOOD = {
    "points": 80,
    "fgm": 30,
    "fga": 60,
    "tpm": 10,
    "tpa": 25,
    "ftm": 10,
    "fta": 12,
    "oreb": 12,
    "dreb": 28,
    "tov": 5,
}
BAD = {
    "points": 55,
    "fgm": 20,
    "fga": 60,
    "tpm": 2,
    "tpa": 25,
    "ftm": 8,
    "fta": 12,
    "oreb": 6,
    "dreb": 28,
    "tov": 15,
}


def _seed_decline(db_session, team):
    """Six games: 3 older good games, 3 recent bad games."""
    for i in range(3):
        _add_game(db_session, team, i, GOOD)
    for i in range(3, 6):
        _add_game(db_session, team, i, BAD)


def _by_metric(alerts):
    return {a["metric"]: a for a in alerts}


class TestComputeTrendAlerts:
    @pytest.mark.integration
    def test_alerts_fire_on_declining_data(self, db_session, default_team):
        _seed_decline(db_session, default_team)
        alerts = AnalyticsService.compute_trend_alerts(default_team.id, last_n=3)
        assert len(alerts) >= 3
        by_metric = _by_metric(alerts)

        efg = by_metric["efg_pct"]
        assert efg["direction"] == "down"
        assert efg["magnitude"] >= 4.0
        assert efg["recent"] < efg["prior"]

        tov = by_metric["tov_pct"]
        assert tov["direction"] == "up"
        assert tov["magnitude"] >= 3.0

        pts = by_metric["pts"]
        assert pts["direction"] == "down"
        assert pts["magnitude"] >= 5.0

        for alert in alerts:
            for key in (
                "metric",
                "label",
                "recent",
                "prior",
                "delta",
                "direction",
                "magnitude",
                "message",
            ):
                assert key in alert

    @pytest.mark.integration
    def test_empty_on_insufficient_history(self, db_session, default_team):
        for i in range(3):
            _add_game(db_session, team=default_team, idx=i, stat=GOOD)
        assert AnalyticsService.compute_trend_alerts(default_team.id, last_n=3) == []

    @pytest.mark.integration
    def test_empty_with_no_games(self, db_session, default_team):
        assert AnalyticsService.compute_trend_alerts(default_team.id, last_n=3) == []

    @pytest.mark.integration
    def test_thresholds_sane_small_noise_no_alerts(self, db_session, default_team):
        base = dict(GOOD)
        noisy = dict(GOOD)
        noisy["fgm"] = GOOD["fgm"] - 1  # ~1.7pt eFG wobble, below the 4pt threshold
        noisy["points"] = GOOD["points"] - 1
        for i in range(3):
            _add_game(db_session, default_team, i, base)
        for i in range(3, 6):
            _add_game(db_session, default_team, i, noisy)
        alerts = AnalyticsService.compute_trend_alerts(default_team.id, last_n=3)
        assert "efg_pct" not in _by_metric(alerts)
        assert "pts" not in _by_metric(alerts)
        assert alerts == []


class TestTrendAlertsAPI:
    @pytest.mark.integration
    def test_endpoint_200_returns_alerts(self, auth_client, db_session, default_team):
        _seed_decline(db_session, default_team)
        response = auth_client.get("/api/advanced/trend-alerts")
        assert response.status_code == 200
        data = response.get_json()
        assert data["team_id"] == default_team.id
        assert isinstance(data["alerts"], list)
        assert len(data["alerts"]) >= 3

    @pytest.mark.integration
    def test_endpoint_empty_on_insufficient_history(
        self, auth_client, db_session, default_team
    ):
        _add_game(db_session, default_team, 0, GOOD)
        response = auth_client.get("/api/advanced/trend-alerts")
        assert response.status_code == 200
        assert response.get_json()["alerts"] == []

    @pytest.mark.integration
    def test_endpoint_team_scoping_cross_team_denied(
        self, auth_client, db_session, default_team, default_org
    ):
        from core.models import Team

        other = Team(
            name="Other Team",
            organization_id=default_org.id,
            slug="other-team-trends",
        )
        db_session.add(other)
        db_session.commit()
        # Declining data exists ONLY for the other team.
        _seed_decline(db_session, other)

        # Session team (default_team) has no games -> no leak from other team.
        response = auth_client.get("/api/advanced/trend-alerts")
        assert response.status_code == 200
        data = response.get_json()
        assert data["team_id"] == default_team.id
        assert data["alerts"] == []

        # Unassigned users cannot pivot the session via ?team_id=.
        response = auth_client.get(f"/api/advanced/trend-alerts?team_id={other.id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["team_id"] == default_team.id
        assert data["alerts"] == []

    @pytest.mark.integration
    def test_endpoint_requires_auth(self, client, db_session, default_team):
        _seed_decline(db_session, default_team)
        response = client.get("/api/advanced/trend-alerts")
        assert response.status_code in [302, 401]
