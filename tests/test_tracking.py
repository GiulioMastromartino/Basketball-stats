"""Tests for tracked championships (GM config) and the sync job."""

from core.models import Team, TrackedChampionship, db


class TestTracking:
    def test_track_from_dashboard(self, admin_client, db_session,
                                  default_org, default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/track",
            data={"provider": "playbasket_html", "comitato_codice": "RLO",
                  "codice_campionato": "DR4", "codice_fase": "1",
                  "codice_girone": "M", "season_label": "2025/2026",
                  "display_name": "DR4 Girone M",
                  "next": "/gm/dashboard"},
            follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert resp.headers["Location"].endswith("/gm/dashboard")
        row = TrackedChampionship.query.filter_by(
            team_id=default_team.id).first()
        assert row is not None and row.active is True

    def test_track_idempotent(self, admin_client, db_session, default_team):
        from core import championship_catalog as catalog_mod
        data = {"provider": "fip_api", "comitato_codice": "NAZ",
                "codice_campionato": "A1/M", "codice_fase": "1",
                "codice_girone": "85160",
                "season_label": catalog_mod.current_season_label(),
                "display_name": "Serie A"}
        for _ in range(2):
            admin_client.post(f"/teams/{default_team.id}/track",
                              data=data, follow_redirects=True)
        assert TrackedChampionship.query.filter_by(
            team_id=default_team.id).count() == 1

    def test_track_cross_org_blocked(self, admin_client, db_session):
        from core.models import Organization
        other = Organization(name="Far", slug="far-track")
        db.session.add(other)
        db.session.flush()
        team = Team(name="Far Team", organization_id=other.id,
                    slug="far-team")
        db.session.add(team)
        db.session.commit()
        resp = admin_client.post(
            f"/teams/{team.id}/track", data={"provider": "fip_api"},
            follow_redirects=True)
        assert resp.status_code == 200
        assert TrackedChampionship.query.filter_by(
            team_id=team.id).first() is None

    def test_fip_real_codes_validate(self):
        from core import championship_catalog as catalog_mod
        ok, error, norm = catalog_mod.validate("fip_api", {
            "comitato_codice": "RLO", "codice_campionato": "1DM",
            "codice_fase": "1", "sesso": "M", "codice_girone": "85405",
            "season_label": "2026/2027"})
        assert ok, error
        assert norm["codice_girone"] == "85405"

    def test_fip_guess_codes_rejected(self):
        from core import championship_catalog as catalog_mod
        ok, error, _ = catalog_mod.validate("fip_api", {
            "comitato_codice": "RLO", "codice_campionato": "DR3",
            "codice_fase": "1", "sesso": "M", "codice_girone": "M",
            "season_label": "2026/2027"})
        assert not ok
        assert "DR3" in (error or "")

    def test_gironi_lookup_endpoint(self, admin_client, monkeypatch):
        from jobs.adapters import fip_api
        monkeypatch.setattr(
            fip_api, "discover_gironi",
            lambda *a, **k: [{"code": "85405", "label": "Girone H"}])
        resp = admin_client.get(
            "/teams/championship-gironi?provider=fip_api"
            "&comitato_codice=RLO&codice_campionato=1DM"
            "&codice_fase=1&sesso=M")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["gironi"] == [{"code": "85405", "label": "Girone H"}]

    def test_gironi_lookup_rejects_non_lombardia(self, admin_client,
                                                monkeypatch):
        # The live scrape only knows the Lombardy region code; do not
        # silently return another region's options.
        resp = admin_client.get(
            "/teams/championship-gironi?provider=fip_api"
            "&comitato_codice=RPI&codice_campionato=1DM"
            "&codice_fase=1&sesso=M")
        body = resp.get_json()
        assert body["ok"] is False
        assert "lombardi" in body["message"]

    def test_all_zero_girone_is_rejected(self):
        from core import championship_catalog as catalog_mod
        ok, error, _ = catalog_mod.validate("fip_api", {
            "comitato_codice": "RLO", "codice_campionato": "1DM",
            "codice_fase": "1", "sesso": "M", "codice_girone": "000000",
            "season_label": "2026/2027"})
        assert not ok
        assert "Girone" in (error or "")

    def test_validate_tolerates_non_string_fields(self):
        from core import championship_catalog as catalog_mod
        ok, error, norm = catalog_mod.validate("fip_api", {
            "comitato_codice": "RLO", "codice_campionato": "1DM",
            "codice_fase": 1, "sesso": "M", "codice_girone": 85405,
            "season_label": "2026/2027"})
        assert ok, error
        assert norm["codice_fase"] == "1"
        assert norm["codice_girone"] == "85405"

    def test_verify_requires_gm(self, auth_client, default_team):
        resp = auth_client.post(
            f"/teams/{default_team.id}/track/verify",
            json={"provider": "fip_api"})
        assert resp.status_code == 403
        assert resp.get_json()["ok"] is False

    def test_verify_rejects_non_object_json(self, admin_client,
                                             default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/track/verify", json=["nope"])
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_track_rejects_non_current_fip_season(self, admin_client,
                                                   db_session,
                                                   default_team):
        from core import championship_catalog as catalog_mod
        current = catalog_mod.current_season_label()
        old = "2023/2024" if current != "2023/2024" else "2024/2025"
        resp = admin_client.post(
            f"/teams/{default_team.id}/track",
            data={"provider": "fip_api", "comitato_codice": "RLO",
                  "codice_campionato": "1DM", "codice_fase": "1",
                  "sesso": "M", "codice_girone": "85405",
                  "season_label": old},
            follow_redirects=True)
        assert resp.status_code == 200
        assert TrackedChampionship.query.filter_by(
            team_id=default_team.id).count() == 0

    def test_track_both_sexes_for_same_configuration(
            self, admin_client, db_session, default_team):
        from core import championship_catalog as catalog_mod
        season = catalog_mod.current_season_label()
        data = {"provider": "fip_api", "comitato_codice": "RLO",
                "codice_campionato": "1DM", "codice_fase": "1",
                "sesso": "M", "codice_girone": "85405",
                "season_label": season}
        admin_client.post(f"/teams/{default_team.id}/track", data=data,
                          follow_redirects=True)
        data["sesso"] = "F"
        admin_client.post(f"/teams/{default_team.id}/track", data=data,
                          follow_redirects=True)
        rows = TrackedChampionship.query.filter_by(
            team_id=default_team.id).all()
        assert len(rows) == 2
        assert {row.sesso for row in rows} == {"M", "F"}

    def test_verify_playbasket_dry_run(self, admin_client, default_team,
                                       monkeypatch):
        from jobs.adapters import playbasket_html as pb
        monkeypatch.setattr(
            pb, "fetch_championship",
            lambda **kw: ([{"home": "A", "away": "B"}],
                          [{"team": "A"}], "fp"))
        resp = admin_client.post(
            f"/teams/{default_team.id}/track/verify",
            json={"provider": "playbasket_html", "comitato_codice": "RLO",
                  "province_codice": "MI", "codice_campionato": "DR4",
                  "codice_fase": "1", "codice_girone": "M",
                  "season_label": "2025/2026"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["games"] == 1
        assert body["standings"] == 1

    def test_verify_rejects_unknown_fip_codes(self, admin_client,
                                              default_team):
        resp = admin_client.post(
            f"/teams/{default_team.id}/track/verify",
            json={"provider": "fip_api", "comitato_codice": "RLO",
                  "codice_campionato": "DR3", "codice_fase": "1",
                  "sesso": "M", "codice_girone": "M",
                  "season_label": "2026/2027"})
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_track_fip_stores_sesso(self, admin_client, db_session,
                                    default_team):
        from core import championship_catalog as catalog_mod
        admin_client.post(
            f"/teams/{default_team.id}/track",
            data={"provider": "fip_api", "comitato_codice": "RLO",
                  "codice_campionato": "1DM", "codice_fase": "1",
                  "sesso": "F", "codice_girone": "85405",
                  "season_label": catalog_mod.current_season_label()},
            follow_redirects=True)
        row = TrackedChampionship.query.filter_by(
            team_id=default_team.id).one()
        assert row.sesso == "F"

    def test_toggle_and_delete(self, admin_client, db_session,
                               default_team):
        row = TrackedChampionship(team_id=default_team.id,
                                  provider="fip_api",
                                  display_name="Serie A")
        db.session.add(row)
        db.session.commit()
        admin_client.post(f"/tracked/{row.id}/toggle",
                          data={"next": "/gm/dashboard"},
                          follow_redirects=True)
        assert TrackedChampionship.query.get(row.id).active is False
        admin_client.post(f"/tracked/{row.id}/delete",
                          follow_redirects=True)
        assert TrackedChampionship.query.get(row.id) is None

    def test_dashboard_shows_tracked(self, admin_client, db_session,
                                     default_team):
        db.session.add(TrackedChampionship(
            team_id=default_team.id, provider="playbasket_html",
            display_name="DR4 Girone M"))
        db.session.commit()
        resp = admin_client.get("/gm/dashboard")
        assert b"DR4 Girone M" in resp.data


class TestSyncJob:
    def test_bootstrap_seeds_snapshot(self, tmp_path, monkeypatch):
        from core import external_store as store
        monkeypatch.setenv("EXT_CACHE_PATH", str(tmp_path / "cache.db"))
        # Exercises the same seed path sync_once uses when no
        # championships are tracked yet.
        conn = store.connect()
        try:
            from pathlib import Path
            seed = (Path("data") / "playbasket_dr4_2025_26.json")
            result = store.seed_from_snapshot_file(conn, seed)
            assert result["added"] == 132
            assert result["standings"] == 12
            assert len(store.list_championships(conn)) == 1
        finally:
            conn.close()

    def test_unsupported_playbasket_config_rejected(self):
        from jobs.adapters import playbasket_html as pb
        try:
            pb.league_url(championship="SERIE_X")
            assert False, "should have raised"
        except ValueError:
            pass
        try:
            pb.fetch_championship(girone="ZZ")
            assert False, "should have raised"
        except ValueError:
            pass

    def test_fip_api_failure_raises_when_empty(self, monkeypatch):
        from jobs.adapters import fip_api
        monkeypatch.setattr(fip_api, "_get",
                            lambda params: (_ for _ in ()).throw(
                                TimeoutError("down")))
        try:
            fip_api.fetch_games("NAZ", "A1/M", "1", "85160", sleep=0)
            assert False, "should have raised"
        except RuntimeError:
            pass
