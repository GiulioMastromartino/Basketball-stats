from core.models import Game


def test_evolution_pdf_uses_schema4_builder_for_schema4_games(
    auth_client, db_session, mocker
):
    game = Game(
        date="05-03-2026",
        opponent="Schema 4 Route Opponent",
        team_score=80,
        opponent_score=70,
        result="W",
        game_type="Season",
        sort_date="2026-03-05",
        source="IMPORT_JSON",
        schema_version=4,
    )
    db_session.add(game)
    db_session.commit()

    report = mocker.Mock(
        game_id=game.id,
        opponent=game.opponent,
        date=game.date,
        result="W",
        final_team_score=80,
        final_opp_score=70,
        team_snapshots=[],
        player_snapshots={},
        quarter_summaries={},
        max_lead=10,
        max_deficit=0,
        lead_changes=0,
        scoring_runs=[],
        clutch_time=None,
    )

    mocker.patch(
        "web.routes.reports.Schema4EvolutionReportService.build_report",
        return_value=report,
    )
    legacy_builder = mocker.patch("web.routes.reports.EvolutionReportService.build_report")
    mocker.patch("web.routes.reports._render_pdf", return_value=("pdf", 200))

    response = auth_client.get(f"/reports/games/{game.id}/evolution.pdf")

    assert response.status_code == 200
    legacy_builder.assert_not_called()


def test_evolution_pdf_keeps_legacy_builder_for_old_schemas(
    auth_client, db_session, mocker
):
    game = Game(
        date="05-03-2026",
        opponent="Legacy Route Opponent",
        team_score=80,
        opponent_score=70,
        result="W",
        game_type="Season",
        sort_date="2026-03-05",
        source="IMPORT_JSON",
        schema_version=3,
    )
    db_session.add(game)
    db_session.commit()

    report = mocker.Mock(
        game_id=game.id,
        opponent=game.opponent,
        date=game.date,
        result="W",
        final_team_score=80,
        final_opp_score=70,
        team_snapshots=[],
        player_snapshots={},
        quarter_summaries={},
        max_lead=10,
        max_deficit=0,
        lead_changes=0,
        scoring_runs=[],
        clutch_time=None,
    )

    schema4_builder = mocker.patch("web.routes.reports.Schema4EvolutionReportService.build_report")
    mocker.patch(
        "web.routes.reports.EvolutionReportService.build_report",
        return_value=report,
    )
    mocker.patch("web.routes.reports._render_pdf", return_value=("pdf", 200))

    response = auth_client.get(f"/reports/games/{game.id}/evolution.pdf")

    assert response.status_code == 200
    schema4_builder.assert_not_called()
