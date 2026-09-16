"""Tests for the isolated external championship cache (SQLite sidecar)."""

import pytest

from core import external_store as store


@pytest.fixture
def conn(tmp_path):
    connection = store.connect(tmp_path / "cache.db")
    yield connection
    connection.close()


SAMPLE = {
    "meta": {"competition": "DR4 Test", "girone": "M", "season": "2025/2026",
             "comitato": "RLO", "campionato": "DR4", "fase": "1",
             "source_url": "https://example.test/"},
    "games": [
        {"turno": "Andata 1", "data": "16/10", "casa": "Team A",
         "ospite": "Team B", "pc": "68", "po": "60"},
        {"turno": "Andata 1", "data": "16/10", "casa": "Team C",
         "ospite": "Team D", "pc": "-1", "po": "-1"},
    ],
    "standings": [
        {"pos": 1, "team": "Team A", "pts": 4, "g": 2, "w": 2, "l": 0,
         "pf": 140, "ps": 120},
    ],
}


class TestExternalStore:
    def test_seed_snapshot(self, conn):
        result = store.seed_from_snapshot(conn, SAMPLE)
        assert result["added"] == 2
        assert result["standings"] == 1
        games = store.list_games(conn, result["championship_id"])
        assert len(games) == 2
        played = [g for g in games if g["home_score"] is not None]
        assert len(played) == 1
        assert played[0]["home_score"] == 68

    def test_seed_idempotent(self, conn):
        first = store.seed_from_snapshot(conn, SAMPLE)
        second = store.seed_from_snapshot(conn, SAMPLE)
        assert second["added"] == 0
        assert second["championship_id"] == first["championship_id"]
        assert len(store.list_games(conn, first["championship_id"])) == 2

    def test_score_update_detected(self, conn):
        result = store.seed_from_snapshot(conn, SAMPLE)
        champ_id = result["championship_id"]
        outcome = store.upsert_game(conn, champ_id,
                                   {"round": "Andata 1", "data": "16/10",
                                    "casa": "Team C",
                                    "ospite": "Team D", "pc": "70",
                                    "po": "65", "stato": "ufficioso"})
        assert outcome == "updated"
        games = store.list_games(conn, champ_id)
        finished = [g for g in games if g["home"] == "Team C"][0]
        assert (finished["home_score"], finished["away_score"]) == (70, 65)

    def test_team_filter(self, conn):
        result = store.seed_from_snapshot(conn, SAMPLE)
        games = store.list_games(conn, result["championship_id"],
                                 team_filter="team a")
        assert len(games) == 1
        assert games[0]["home"] == "Team A"

    def test_new_since(self, conn):
        result = store.seed_from_snapshot(conn, SAMPLE)
        assert len(store.new_since(conn, result["championship_id"],
                                   "2000-01-01T00:00:00+00:00")) == 2
        assert store.new_since(conn, result["championship_id"],
                               "2999-01-01T00:00:00+00:00") == []

    def test_sync_log(self, conn):
        result = store.seed_from_snapshot(conn, SAMPLE)
        log_id = store.log_sync(conn, result["championship_id"],
                                fetched=2, added=2)
        assert log_id > 0


class TestPostponementIdentity:
    def test_same_teams_round_survives_date_change(self, conn):
        from core import external_store as store
        champ = store.upsert_championship(
            conn, provider="playbasket_html", campionato="DR4", fase="1",
            girone="M", season="2025/2026")
        assert store.upsert_game(
            conn, champ, {"round": "Andata 3", "data": "28/10",
                          "casa": "Team A", "ospite": "Team B",
                          "pc": "49", "po": "73"}) == "added"
        # Postponed to a new date, same round+teams: same fixture,
        # but stored date must update (not stay stale).
        assert store.upsert_game(
            conn, champ, {"round": "Andata 3", "data": "04/11",
                          "casa": "Team A", "ospite": "Team B",
                          "pc": "49", "po": "73"}) == "updated"
        games = store.list_games(conn, champ)
        assert len(games) == 1
        assert games[0]["game_date"] == "04/11"

    def test_numbered_identity_ignores_date(self, conn):
        from core import external_store as store
        champ = store.upsert_championship(
            conn, provider="fip_api", comitato="NAZ",
            campionato="A1/M", fase="1", girone="85160",
            season="2026/2027")
        assert store.upsert_game(
            conn, champ, {"game_number": "000003", "date": "2026-09-26",
                          "home": "Team A", "away": "Team B",
                          "home_score": -1, "away_score": -1}) == "added"
        assert store.upsert_game(
            conn, champ, {"game_number": "000003", "date": "2026-09-27",
                          "home": "Team A", "away": "Team B",
                          "home_score": 100, "away_score": 80}) == "updated"
