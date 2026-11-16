"""Organization export/import bundle: service round-trip and admin routes."""

import io
import json

import pytest

from core.models import (
    DevelopmentGoal,
    Game,
    GameEvent,
    Lineup,
    LineupSegment,
    Organization,
    OrganizationMembership,
    Player,
    PlayerLineupStats,
    PlayerStat,
    Play,
    PlaySequence,
    PlayType,
    Possession,
    Season,
    ShotEvent,
    Team,
    TrackedChampionship,
    TrainingAttendance,
    TrainingSegment,
    TrainingSegmentTemplate,
    TrainingSession,
    WhatsAppGroup,
    db,
)
from core.services.org_transfer_service import (
    EXPORT_FORMAT,
    OrgImportError,
    export_organizations,
    import_organizations,
)


def _build_org_graph(org, team):
    """Populate one org with at least one row of every exported entity."""
    season = Season(
        team_id=team.id, name="2025/26", start_date="2025-09-01",
        end_date="2026-06-30", is_active=True,
    )
    player = Player(
        team_id=team.id, name="Mario Rossi", email="mario@example.com",
        active=True,
    )
    play_type = PlayType(team_id=team.id, name="Motion")
    play = Play(
        team_id=team.id, name="Horns Twist", description="Test play",
        play_type="Offense", canvas_data={"frames": [1]},
    )
    lineup = Lineup(
        team_id=team.id, lineup_hash="lineup-hash-1",
        players=["Mario Rossi"], display_name="Starters",
        games_played=1, segment_count=1,
    )
    db.session.add_all([season, player, play_type, play, lineup])
    db.session.flush()

    sequence = PlaySequence(
        play_id=play.id, sequence_number=1, element_data={"x": 1},
        caption="First frame",
    )
    game = Game(
        team_id=team.id, season_id=season.id, date="01-10-2025",
        opponent="Rivals", team_score=80, opponent_score=70, result="W",
        game_type="Season", sort_date="2025-10-01", source="MANUAL",
    )
    db.session.add_all([sequence, game])
    db.session.flush()

    stat = PlayerStat(
        game_id=game.id, player_name="Mario Rossi", points=20, minutes="30:00",
        reb=5, ast=4,
    )
    event1 = GameEvent(
        game_id=game.id, event_type="shot", player_name="Mario Rossi",
        timestamp=1000,
    )
    event2 = GameEvent(
        game_id=game.id, event_type="rebound", player_name="Mario Rossi",
        timestamp=2000,
    )
    shot = ShotEvent(
        game_id=game.id, player_name="Mario Rossi", shot_type="2PT",
        result="Made", points=2, x_loc=1.5, y_loc=2.5, quarter=1,
        play_id=play.id,
    )
    segment = LineupSegment(
        game_id=game.id, start_timestamp=1000, end_timestamp=2000,
        quarter=1, players=["Mario Rossi"], lineup_hash="lineup-hash-1",
        lineup_id=lineup.id,
    )
    db.session.add_all([stat, event1, event2, shot, segment])
    db.session.flush()

    player_segment_stat = PlayerLineupStats(
        lineup_segment_id=segment.id, player_name="Mario Rossi", points=2,
    )
    possession = Possession(
        game_id=game.id, start_event_id=event1.id, end_event_id=event2.id,
        team_possession=True, quarter=1, points=2, play_id=play.id,
    )
    training = TrainingSession(
        team_id=team.id, title="Shooting practice", session_date="2025-10-02",
        focus="Offense", notes="Bring cones",
    )
    db.session.add_all([player_segment_stat, possession, training])
    db.session.flush()

    training_segment = TrainingSegment(
        session_id=training.id, position=1, title="Warm-up", duration_min=10,
        play_id=play.id,
    )
    attendance = TrainingAttendance(
        session_id=training.id, player_id=player.id, status="present",
    )
    template = TrainingSegmentTemplate(
        team_id=team.id, title="Warm-up", duration_min=10, play_id=play.id,
        category="Offense", usage_count=3,
    )
    tracked = TrackedChampionship(
        team_id=team.id, provider="fip_api", comitato_codice="MI",
        province_codice="MI", codice_campionato="123", codice_fase="1",
        codice_girone="A", season_label="2025/26", display_name="U19 A",
    )
    whatsapp = WhatsAppGroup(
        team_id=team.id, group_name="Team chat", group_wa_id="1203630",
    )
    goal = DevelopmentGoal(
        team_id=team.id, player_name="Mario Rossi", metric="ft_percent",
        target=75.0, window=5,
    )
    db.session.add_all([
        training_segment, attendance, template, tracked, whatsapp, goal,
    ])
    db.session.commit()
    return {
        "season": season, "player": player, "play": play, "lineup": lineup,
        "game": game, "event1": event1, "event2": event2, "shot": shot,
        "segment": segment, "training": training,
    }


class TestOrgExportService:
    def test_bundle_shape(self, db_session, default_org, default_team):
        _build_org_graph(default_org, default_team)

        bundle = export_organizations([default_org.id])

        assert bundle["format"] == EXPORT_FORMAT
        assert bundle["version"] == 1
        assert len(bundle["organizations"]) == 1
        exported = bundle["organizations"][0]
        assert exported["name"] == default_org.name
        team = exported["teams"][0]
        assert len(team["seasons"]) == 1
        assert len(team["players"]) == 1
        assert len(team["plays"]) == 1
        assert len(team["plays"][0]["sequences"]) == 1
        assert len(team["games"]) == 1
        game = team["games"][0]
        assert len(game["player_stats"]) == 1
        assert len(game["events"]) == 2
        assert len(game["shots"]) == 1
        assert len(game["lineup_segments"]) == 1
        assert len(game["lineup_segments"][0]["player_stats"]) == 1
        assert len(game["possessions"]) == 1
        assert len(team["training_sessions"]) == 1
        assert len(team["training_sessions"][0]["attendance"]) == 1
        assert len(team["tracked_championships"]) == 1
        assert len(team["whatsapp_groups"]) == 1
        assert len(team["development_goals"]) == 1

    def test_import_round_trip_remaps_foreign_keys(
        self, db_session, default_org, default_team
    ):
        source = _build_org_graph(default_org, default_team)
        bundle = export_organizations([default_org.id])

        imported, warnings = import_organizations(bundle)

        # Importing into the same database legitimately collides on the two
        # global unique columns (player email and play-type name).
        assert all(
            "duplicate player email" in warning or "existing play type" in warning
            for warning in warnings
        )
        assert len(imported) == 1
        new_org = imported[0]
        assert new_org.id != default_org.id
        assert new_org.name == default_org.name
        assert new_org.slug == f"{default_org.slug}-2"

        new_team = Team.query.filter_by(organization_id=new_org.id).one()
        new_season = Season.query.filter_by(team_id=new_team.id).one()
        new_player = Player.query.filter_by(team_id=new_team.id).one()
        new_play = Play.query.filter_by(team_id=new_team.id).one()
        new_lineup = Lineup.query.filter_by(team_id=new_team.id).one()
        new_game = Game.query.filter_by(team_id=new_team.id).one()

        # Global uniqueness collisions get a suffix; relationships stay intact.
        assert new_player.name == "Mario Rossi (imported)"
        assert PlaySequence.query.filter_by(play_id=new_play.id).count() == 1
        assert new_game.season_id == new_season.id

        assert PlayerStat.query.filter_by(game_id=new_game.id).count() == 1
        assert ShotEvent.query.filter_by(game_id=new_game.id).count() == 1
        assert GameEvent.query.filter_by(game_id=new_game.id).count() == 2
        new_segment = LineupSegment.query.filter_by(game_id=new_game.id).one()
        assert new_segment.lineup_id == new_lineup.id
        assert PlayerLineupStats.query.filter_by(
            lineup_segment_id=new_segment.id
        ).count() == 1

        new_events = GameEvent.query.filter_by(game_id=new_game.id).all()
        assert all(e.lineup_segment_id is None for e in new_events)

        possession = Possession.query.filter_by(game_id=new_game.id).one()
        assert possession.start_event_id in {e.id for e in new_events}
        assert possession.end_event_id in {e.id for e in new_events}
        assert possession.play_id == new_play.id

        new_training = TrainingSession.query.filter_by(team_id=new_team.id).one()
        assert TrainingSegment.query.filter_by(
            session_id=new_training.id
        ).count() == 1
        attendance = TrainingAttendance.query.filter_by(
            session_id=new_training.id
        ).one()
        assert attendance.player_id == new_player.id
        assert TrainingSegmentTemplate.query.filter_by(
            team_id=new_team.id
        ).count() == 1
        assert TrackedChampionship.query.filter_by(
            team_id=new_team.id
        ).count() == 1
        assert WhatsAppGroup.query.filter_by(team_id=new_team.id).count() == 1
        assert DevelopmentGoal.query.filter_by(team_id=new_team.id).count() == 1

    def test_repeated_import_keeps_names_unique(
        self, db_session, default_org, default_team
    ):
        _build_org_graph(default_org, default_team)
        bundle = export_organizations([default_org.id])

        first, _ = import_organizations(bundle)
        second, warnings = import_organizations(bundle)

        assert first[0].slug == f"{default_org.slug}-2"
        assert second[0].slug == f"{default_org.slug}-3"
        names = {p.name for p in Player.query.all()}
        assert "Mario Rossi" in names
        assert "Mario Rossi (imported)" in names
        assert "Mario Rossi (imported) 2" in names
        assert any("duplicate player email" in w for w in warnings)

    def test_invalid_bundle_rejected_without_partial_rows(
        self, db_session, default_org, default_team
    ):
        before_orgs = Organization.query.count()
        before_teams = Team.query.count()
        with pytest.raises(OrgImportError):
            import_organizations({"format": EXPORT_FORMAT, "version": 999,
                                  "organizations": [{"name": "Nope"}]})
        assert Organization.query.count() == before_orgs
        assert Team.query.count() == before_teams

    def test_import_rolls_back_on_bad_row(
        self, db_session, default_org, default_team
    ):
        _build_org_graph(default_org, default_team)
        bundle = export_organizations([default_org.id])
        # Break a non-nullable column to force a database error mid-import.
        bundle["organizations"][0]["teams"][0]["games"][0]["result"] = None
        before = Organization.query.count()
        with pytest.raises(Exception):
            import_organizations(bundle)
        assert Organization.query.count() == before


class TestOrgTransferRoutes:
    def test_admin_panel_transfer_section(self, admin_client):
        resp = admin_client.get("/admin/transfer")
        assert resp.status_code == 200
        assert b"Export / Import organizations" in resp.data

    def test_export_route_returns_json_attachment(
        self, admin_client, db_session, default_org, default_team
    ):
        _build_org_graph(default_org, default_team)

        resp = admin_client.get(f"/admin/orgs/export?org_id={default_org.id}")

        assert resp.status_code == 200
        assert resp.mimetype == "application/json"
        assert "attachment" in resp.headers["Content-Disposition"]
        payload = json.loads(resp.data)
        assert payload["format"] == EXPORT_FORMAT
        assert payload["organizations"][0]["name"] == default_org.name

    def test_export_route_without_selection_exports_visible_orgs(
        self, admin_client, db_session, default_org
    ):
        resp = admin_client.get("/admin/orgs/export")

        assert resp.status_code == 200
        payload = json.loads(resp.data)
        assert [o["name"] for o in payload["organizations"]] == [default_org.name]

    def test_export_route_rejects_foreign_org(
        self, admin_client, db_session
    ):
        other = Organization(name="Other", slug="other")
        db.session.add(other)
        db.session.commit()

        resp = admin_client.get(f"/admin/orgs/export?org_id={other.id}",
                                follow_redirects=True)

        assert resp.status_code == 200
        assert b"Select at least one organization" in resp.data

    def test_import_route_creates_org_and_membership(
        self, admin_client, db_session, admin_user, default_org, default_team
    ):
        _build_org_graph(default_org, default_team)
        bundle = export_organizations([default_org.id])

        resp = admin_client.post(
            "/admin/orgs/import",
            data={"org_file": (
                io.BytesIO(json.dumps(bundle).encode("utf-8")), "org.json"
            )},
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert resp.status_code == 200
        assert b"Imported 1 organization" in resp.data
        imported = Organization.query.filter_by(slug=f"{default_org.slug}-2").one()
        membership = OrganizationMembership.query.filter_by(
            user_id=admin_user.id, organization_id=imported.id
        ).one()
        assert membership.is_gm is True

    def test_import_route_rejects_bad_json(self, admin_client, db_session):
        before = Organization.query.count()
        resp = admin_client.post(
            "/admin/orgs/import",
            data={"org_file": (io.BytesIO(b"not json"), "org.json")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert b"not valid JSON" in resp.data
        assert Organization.query.count() == before

    def test_editor_cannot_import(
        self, auth_client, db_session, default_org, default_team
    ):
        _build_org_graph(default_org, default_team)
        bundle = export_organizations([default_org.id])
        before = Organization.query.count()
        resp = auth_client.post(
            "/admin/orgs/import",
            data={"org_file": (
                io.BytesIO(json.dumps(bundle).encode("utf-8")), "org.json"
            )},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert Organization.query.count() == before
