from core.models import Game, PlayerStat


def test_evolution_pdf_uses_schema4_builder_for_schema4_games(
    auth_client, db_session, default_team, mocker
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
        team_id=default_team.id,
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
    auth_client, db_session, default_team, mocker
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
        team_id=default_team.id,
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


def test_download_all_reports_filters_players_by_selected_game_type(
    auth_client, db_session, default_team, mocker
):
    season_game = Game(
        date="06-03-2026",
        opponent="Season Opponent",
        team_score=70,
        opponent_score=60,
        result="W",
        game_type="Season",
        sort_date="2026-03-06",
        source="MANUAL",
        team_id=default_team.id,
    )
    friendly_game = Game(
        date="07-03-2026",
        opponent="Friendly Opponent",
        team_score=65,
        opponent_score=55,
        result="W",
        game_type="Friendly",
        sort_date="2026-03-07",
        source="MANUAL",
        team_id=default_team.id,
    )
    db_session.add_all([season_game, friendly_game])
    db_session.flush()

    db_session.add_all(
        [
            PlayerStat(
                game_id=season_game.id,
                player_name="Season Only",
                minutes="20:00",
                points=10,
                fgm=4,
                fga=8,
                tpm=1,
                tpa=2,
                ftm=1,
                fta=2,
                oreb=1,
                dreb=2,
                reb=3,
                ast=2,
                stl=1,
                blk=0,
                tov=1,
                pf=1,
                plus_minus=5,
            ),
            PlayerStat(
                game_id=friendly_game.id,
                player_name="Friendly Only",
                minutes="18:00",
                points=8,
                fgm=3,
                fga=7,
                tpm=0,
                tpa=1,
                ftm=2,
                fta=2,
                oreb=0,
                dreb=3,
                reb=3,
                ast=1,
                stl=0,
                blk=0,
                tov=1,
                pf=2,
                plus_minus=2,
            ),
        ]
    )
    db_session.commit()

    generated_players = []

    mocker.patch("web.routes.reports._build_team_report_context", return_value={})
    mocker.patch("web.routes.reports.render_template", return_value="<html></html>")
    html_instance = mocker.MagicMock()
    html_instance.write_pdf.return_value = b"pdf"
    mocker.patch("web.routes.reports.HTML", return_value=html_instance)

    def fake_generate_player_report_data(player_name, *args, **kwargs):
        generated_players.append(player_name)
        return {}

    mocker.patch(
        "web.routes.reports._generate_player_report_data",
        side_effect=fake_generate_player_report_data,
    )

    response = auth_client.get("/reports/download-all?game_type=Season")

    assert response.status_code == 200
    assert generated_players == ["Season Only"]


def test_advanced_game_summary_pdf_handles_invalid_minutes(
    auth_client, db_session, default_team, mocker
):
    game = Game(
        date="08-03-2026",
        opponent="Invalid Minutes Opponent",
        team_score=72,
        opponent_score=61,
        result="W",
        game_type="Season",
        sort_date="2026-03-08",
        source="MANUAL",
        team_id=default_team.id,
    )
    db_session.add(game)
    db_session.flush()

    db_session.add(
        PlayerStat(
            game_id=game.id,
            player_name="Needs Parsing",
            minutes="DNP",
            points=0,
            fgm=0,
            fga=0,
            tpm=0,
            tpa=0,
            ftm=0,
            fta=0,
            oreb=0,
            dreb=0,
            reb=0,
            ast=0,
            stl=0,
            blk=0,
            tov=0,
            pf=0,
            plus_minus=0,
        )
    )
    db_session.commit()

    captured = {}

    def fake_build_advanced_game_report(**kwargs):
        captured["players"] = kwargs["players"]
        return {"team": {}, "opp": {}, "players": []}

    mocker.patch(
        "web.routes.reports.build_advanced_game_report",
        side_effect=fake_build_advanced_game_report,
    )
    mocker.patch("web.routes.reports.render_template", return_value="<html></html>")
    mocker.patch("web.routes.reports._render_pdf", return_value=("pdf", 200))

    response = auth_client.get(f"/reports/games/{game.id}/advanced_summary.pdf")

    assert response.status_code == 200
    assert captured["players"][0].minutes == 0.0
