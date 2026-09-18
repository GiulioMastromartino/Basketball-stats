"""Platform health — aggregate cache, usage metering, sync probe, GDPR."""

import json

import pytest

from core.aggregate_cache import cached_four_factors, invalidate
from core.models import Player, PlayerStat, db
from core.usage_meter import COUNTERS, bump, get_usage


class TestAggregateCache:
    def test_cached_same_object(self, db_session, sample_game,
                                sample_player_stats):
        invalidate()
        first = cached_four_factors([sample_game.id])
        second = cached_four_factors([sample_game.id])
        assert first is second
        assert "efg_pct" in first

    def test_different_key_recomputes(self, db_session, sample_game,
                                      sample_player_stats):
        invalidate()
        one = cached_four_factors([sample_game.id])
        other = cached_four_factors([sample_game.id, sample_game.id + 999])
        assert one is not other

    def test_invalidate_clears(self, db_session, sample_game,
                               sample_player_stats):
        invalidate()
        first = cached_four_factors([sample_game.id])
        invalidate()
        assert cached_four_factors([sample_game.id]) is not first
        assert cached_four_factors([sample_game.id]) == first

    def test_empty_games(self, db_session):
        invalidate()
        assert cached_four_factors([]) == {}


class TestUsageMeter:
    def test_bump_and_read(self, db_session):
        before = get_usage()["halftime_shares"]
        assert bump("halftime_shares") == before + 1
        assert get_usage()["halftime_shares"] == before + 1

    def test_all_counters_present(self, db_session):
        assert set(get_usage()) == set(COUNTERS)

    def test_unknown_counter(self, db_session):
        with pytest.raises(ValueError):
            bump("nope")


class TestSyncProbe:
    def test_shape(self, client):
        resp = client.get("/health/sync")
        assert resp.status_code in (200, 503)
        data = json.loads(resp.data)
        assert data["status"] in ("ok", "stale", "unknown")

    def test_check_script_runs(self, capsys):
        from jobs.check_sync_health import main
        rc = main(["--championship", "999999"])
        assert rc == 2  # unknown id must not report healthy
        assert "championships" in capsys.readouterr().out

    def test_usage_scoped_per_team(self, db_session, default_org,
                                   default_team):
        from core.models import Organization, Team
        from core.usage_meter import bump, get_usage
        org_b = Organization(name="Org B", slug="org-b")
        db_session.add(org_b)
        db_session.flush()
        team_b = Team(name="Team B", organization_id=org_b.id, slug="team-b")
        db_session.add(team_b)
        db_session.commit()
        assert bump("halftime_shares", team_id=default_team.id) == 1
        assert bump("halftime_shares", team_id=default_team.id) == 2
        assert bump("halftime_shares", team_id=team_b.id) == 1
        assert get_usage(team_id=default_team.id)["halftime_shares"] == 2
        assert get_usage(team_id=team_b.id)["halftime_shares"] == 1

    def test_ambiguous_player_name_refused(self, client, mocker):
        import core.models as models
        from web.routes.api_v1 import _ambiguous_player_name
        from types import SimpleNamespace
        mock_query = mocker.MagicMock()
        mock_query.filter.return_value.first.return_value = object()
        mocker.patch.object(models, "Player")
        models.Player.query = mock_query
        resp, status = _ambiguous_player_name(
            SimpleNamespace(id=1, name="Dup"), team_id=1)
        assert status == 409
        assert "shared" in resp.get_json()["error"]

    def test_unambiguous_player_name_passes(self, client, db_session,
                                            default_team):
        from core.models import Player
        from web.routes.api_v1 import _ambiguous_player_name
        player = Player(team_id=default_team.id, name="Solo Solo")
        db_session.add(player)
        db_session.commit()
        assert _ambiguous_player_name(player, default_team.id) is None


class TestGdpr:
    def _player(self, db_session, default_team):
        player = Player(team_id=default_team.id, name="Erased Ernie",
                        email="ernie@t.com")
        db_session.add(player)
        db_session.commit()
        return player

    def test_export_gm(self, admin_client, db_session, default_team,
                       sample_game, sample_player_stats):
        player = self._player(db_session, default_team)
        resp = admin_client.get(f"/api/v1/players/{player.id}/export")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["player"]["email"] == "ernie@t.com"
        assert data["games_played"] == 0

    def test_export_includes_stats(self, admin_client, db_session,
                                   default_team, sample_game):
        from core.models import Game
        game = Game.query.get(sample_game.id)
        db_session.add(PlayerStat(game_id=game.id, player_name="Erased Ernie",
                                  points=7, minutes="10:00"))
        player = self._player(db_session, default_team)
        db_session.commit()
        data = json.loads(admin_client.get(
            f"/api/v1/players/{player.id}/export").data)
        assert data["games_played"] == 1

    def test_export_forbidden_for_coach(self, auth_client, db_session,
                                        default_team):
        player = self._player(db_session, default_team)
        assert auth_client.get(
            f"/api/v1/players/{player.id}/export").status_code == 403

    def test_export_404(self, admin_client):
        assert admin_client.get(
            "/api/v1/players/999999/export").status_code == 404

    def test_delete_removes_player_and_stats(self, admin_client, db_session,
                                             default_team, sample_game):
        from core.models import Game
        game = Game.query.get(sample_game.id)
        db_session.add(PlayerStat(game_id=game.id, player_name="Erased Ernie",
                                  points=7, minutes="10:00"))
        player = self._player(db_session, default_team)
        db_session.commit()
        resp = admin_client.delete(f"/api/v1/players/{player.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data == {"success": True, "player": "Erased Ernie",
                        "stats_removed": 1}
        assert Player.query.get(player.id) is None
        assert PlayerStat.query.filter_by(
            player_name="Erased Ernie").count() == 0

    def test_delete_audited(self, admin_client, db_session, default_team):
        from core.models import AdminAudit
        player = self._player(db_session, default_team)
        admin_client.delete(f"/api/v1/players/{player.id}")
        entry = AdminAudit.query.filter_by(
            action="player.gdpr_delete").first()
        assert entry is not None
        assert "Erased Ernie" in entry.summary
