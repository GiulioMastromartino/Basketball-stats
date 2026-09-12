"""Tests for multi-season support: model, service, routes, admin CRUD."""

import pytest

from core.models import Game, Season, db
from core.services.season_service import (
    create_season,
    delete_season,
    ensure_default_season,
    get_active_season,
    list_seasons,
    match_season_for_date,
    resolve_season_id,
    season_name_for_date,
    set_active_season,
)
from core.services.game_service import create_game_from_live_data


def _payload(date="2025-11-15", opponent="Season Opp"):
    return {
        "date": date,
        "opponent": opponent,
        "team_score": 70,
        "opponent_score": 60,
        "game_type": "Season",
        "player_stats": {},
        "shot_events": [],
        "game_events": [],
    }


class TestSeasonModel:
    @pytest.mark.integration
    def test_create_season(self, db_session, default_team):
        season = create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31",
            set_active=True,
        )
        assert season.id is not None
        assert season.is_active is True
        assert get_active_season(default_team.id).id == season.id

    @pytest.mark.integration
    def test_first_season_becomes_active(self, db_session, default_team):
        season = create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31"
        )
        assert season.is_active is True

    @pytest.mark.integration
    def test_duplicate_name_rejected(self, db_session, default_team):
        create_season(default_team.id, "2025/26", "2025-08-01", "2026-07-31")
        with pytest.raises(ValueError, match="already exists"):
            create_season(default_team.id, "2025/26", "2025-08-01", "2026-07-31")

    @pytest.mark.integration
    def test_bad_range_rejected(self, db_session, default_team):
        with pytest.raises(ValueError, match="start_date"):
            create_season(default_team.id, "2025/26", "2026-07-31", "2025-08-01")

    @pytest.mark.integration
    def test_set_active_switches(self, db_session, default_team):
        s1 = create_season(default_team.id, "2024/25", "2024-08-01", "2025-07-31")
        s2 = create_season(default_team.id, "2025/26", "2025-08-01", "2026-07-31")
        assert s1.is_active is True
        set_active_season(default_team.id, s2.id)
        assert get_active_season(default_team.id).id == s2.id
        assert Season.query.get(s1.id).is_active is False

    @pytest.mark.integration
    def test_delete_empty_season(self, db_session, default_team):
        s = create_season(default_team.id, "2025/26", "2025-08-01", "2026-07-31")
        other = create_season(
            default_team.id, "2026/27", "2026-08-01", "2027-07-31",
            set_active=True,
        )
        delete_season(default_team.id, s.id)
        assert Season.query.get(s.id) is None
        assert get_active_season(default_team.id).id == other.id

    @pytest.mark.integration
    def test_delete_season_with_games_rejected(self, db_session, default_team):
        s = create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31",
            set_active=True,
        )
        game = create_game_from_live_data(
            _payload(), team_id=default_team.id, season_id=s.id
        )
        assert game.season_id == s.id
        with pytest.raises(ValueError, match="has games"):
            delete_season(default_team.id, s.id)


class TestSeasonResolution:
    @pytest.mark.integration
    def test_match_by_date(self, db_session, default_team):
        s = create_season(default_team.id, "2025/26", "2025-08-01", "2026-07-31")
        assert match_season_for_date(default_team.id, "2025-11-15").id == s.id
        assert match_season_for_date(default_team.id, "2024-01-01") is None

    @pytest.mark.integration
    def test_explicit_wins(self, db_session, default_team):
        s1 = create_season(default_team.id, "2024/25", "2024-08-01", "2025-07-31")
        s2 = create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31",
            set_active=True,
        )
        # Date matches s1, but explicit s2 wins.
        assert resolve_season_id(default_team.id, s2.id, "2024-11-15") == s2.id
        assert s1.id != s2.id

    @pytest.mark.integration
    def test_date_match_beats_active(self, db_session, default_team):
        s1 = create_season(default_team.id, "2024/25", "2024-08-01", "2025-07-31")
        create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31",
            set_active=True,
        )
        assert resolve_season_id(default_team.id, None, "2024-11-15") == s1.id

    @pytest.mark.integration
    def test_falls_back_to_active(self, db_session, default_team):
        s = create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31",
            set_active=True,
        )
        assert resolve_season_id(default_team.id, None, "2030-01-01") == s.id

    @pytest.mark.integration
    def test_game_auto_assigned_by_date(self, db_session, default_team):
        create_season(default_team.id, "2025/26", "2025-08-01", "2026-07-31")
        game = create_game_from_live_data(_payload(), team_id=default_team.id)
        assert game.season_id is not None

    @pytest.mark.integration
    def test_ensure_default_season(self, db_session, default_team):
        season = ensure_default_season(default_team.id)
        assert season.id is not None
        assert season.is_active is True
        # Idempotent.
        assert ensure_default_season(default_team.id).id == season.id

    @pytest.mark.integration
    def test_season_name_follows_sept_june_convention(self):
        assert season_name_for_date("2025-10-16") == (
            "2025/2026", "2025-09-01", "2026-06-30",
        )
        assert season_name_for_date("2026-05-15") == (
            "2025/2026", "2025-09-01", "2026-06-30",
        )
        assert season_name_for_date("2026-09-01") == (
            "2026/2027", "2026-09-01", "2027-06-30",
        )
        assert season_name_for_date("2026-08-31") == (
            "2025/2026", "2025-09-01", "2026-06-30",
        )


class TestSeasonRoutes:
    @pytest.mark.integration
    def _two_season_games(self, db_session, default_team):
        s1 = create_season(default_team.id, "2024/25", "2024-08-01", "2025-07-31")
        s2 = create_season(
            default_team.id, "2025/26", "2025-08-01", "2026-07-31",
            set_active=True,
        )
        g1 = create_game_from_live_data(
            _payload("2024-11-15", "Old Opp"), team_id=default_team.id
        )
        g2 = create_game_from_live_data(
            _payload("2025-11-15", "New Opp"), team_id=default_team.id
        )
        assert g1.season_id == s1.id
        assert g2.season_id == s2.id
        return s1, s2, g1, g2

    def test_players_page_filters_by_season(
        self, auth_client, db_session, default_team
    ):
        from core.models import PlayerStat

        s1, s2, g1, g2 = self._two_season_games(db_session, default_team)
        db_session.add(PlayerStat(
            game_id=g1.id, player_name="Old Star", minutes="20:00",
            points=10, fgm=1, fga=2,
        ))
        db_session.add(PlayerStat(
            game_id=g2.id, player_name="New Star", minutes="20:00",
            points=30, fgm=3, fga=4,
        ))
        db_session.commit()
        all_resp = auth_client.get("/players")
        assert all_resp.status_code == 200
        assert b"Old Star" in all_resp.data
        assert b"New Star" in all_resp.data
        s1_resp = auth_client.get(f"/players?season={s1.id}")
        assert s1_resp.status_code == 200
        assert b"Old Star" in s1_resp.data
        assert b"New Star" not in s1_resp.data
        s2_resp = auth_client.get(f"/players?season={s2.id}")
        assert s2_resp.status_code == 200
        assert b"New Star" in s2_resp.data
        assert b"Old Star" not in s2_resp.data

    def test_player_detail_respects_season(
        self, auth_client, db_session, default_team
    ):
        from core.models import PlayerStat

        s1, s2, g1, g2 = self._two_season_games(db_session, default_team)
        for game, pts in ((g1, 10), (g2, 30)):
            db_session.add(
                PlayerStat(game_id=game.id, player_name="Season Player",
                           minutes="20:00", points=pts, fgm=1, fga=2)
            )
        db_session.commit()
        r_all = auth_client.get("/player/Season%20Player")
        assert r_all.status_code == 200
        r_s1 = auth_client.get(f"/player/Season%20Player?season={s1.id}")
        assert r_s1.status_code == 200
        assert b"10.0" in r_s1.data
        assert b"30.0" not in r_s1.data

    def test_switch_season_route(self, auth_client, db_session, default_team):
        s, _, _, _ = self._two_season_games(db_session, default_team)
        resp = auth_client.get(f"/season/switch?season={s.id}", follow_redirects=False)
        assert resp.status_code == 302
        with auth_client.session_transaction() as sess:
            assert sess.get("current_season_id") == s.id
        resp = auth_client.get("/season/switch?season=ALL", follow_redirects=False)
        assert resp.status_code == 302
        with auth_client.session_transaction() as sess:
            assert sess.get("current_season_id") == "ALL"

    def test_admin_crud_seasons(self, admin_client, db_session, default_team):
        # Create.
        resp = admin_client.post(
            "/seasons/create",
            data={"name": "2026/27", "start_date": "2026-08-01",
                  "end_date": "2027-07-31", "set_active": "on"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        created = Season.query.filter_by(
            team_id=default_team.id, name="2026/27"
        ).first()
        assert created is not None
        assert created.is_active is True
        # Admin panel lists it.
        resp = admin_client.get("/admin/seasons")
        assert resp.status_code == 200
        assert b"2026/27" in resp.data
        # Delete (empty).
        resp = admin_client.post(
            f"/seasons/{created.id}/delete", follow_redirects=True
        )
        assert resp.status_code == 200
        assert Season.query.get(created.id) is None

    def test_admin_season_crud_denied_for_editor(
        self, auth_client, db_session, default_team
    ):
        resp = auth_client.post(
            "/seasons/create",
            data={"name": "X", "start_date": "2026-08-01",
                  "end_date": "2027-07-31"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 403)
        assert Season.query.filter_by(team_id=default_team.id, name="X").first() is None
