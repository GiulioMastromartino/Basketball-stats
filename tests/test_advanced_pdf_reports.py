from core.advanced_pdf_reports import AdvancedPDFReports
from core.models import Game, PlayerStat, ShotEvent


def test_player_scouting_card_filters_shots_by_game_type(db_session, mocker):
    season_game = Game(
        date="20-03-2026",
        opponent="Season Opponent",
        team_score=70,
        opponent_score=60,
        result="W",
        game_type="Season",
        sort_date="2026-03-20",
        source="IMPORT_JSON",
    )
    friendly_game = Game(
        date="21-03-2026",
        opponent="Friendly Opponent",
        team_score=68,
        opponent_score=59,
        result="W",
        game_type="Friendly",
        sort_date="2026-03-21",
        source="IMPORT_JSON",
    )
    db_session.add_all([season_game, friendly_game])
    db_session.flush()

    db_session.add_all(
        [
            PlayerStat(
                game_id=season_game.id,
                player_name="Filter Me",
                minutes="20:00",
                points=10,
                fgm=4,
                fga=8,
                tpm=1,
                tpa=2,
                ftm=1,
                fta=2,
                oreb=1,
                dreb=3,
                reb=4,
                ast=2,
                stl=1,
                blk=0,
                tov=1,
                pf=1,
            ),
            PlayerStat(
                game_id=friendly_game.id,
                player_name="Filter Me",
                minutes="18:00",
                points=8,
                fgm=3,
                fga=7,
                tpm=0,
                tpa=1,
                ftm=2,
                fta=2,
                oreb=0,
                dreb=2,
                reb=2,
                ast=1,
                stl=0,
                blk=0,
                tov=1,
                pf=2,
            ),
            ShotEvent(
                game_id=season_game.id,
                player_name="Filter Me",
                shot_type="2pt",
                result="made",
                points=2,
                x_loc=250,
                y_loc=120,
                quarter=1,
            ),
            ShotEvent(
                game_id=friendly_game.id,
                player_name="Filter Me",
                shot_type="3pt",
                result="made",
                points=3,
                x_loc=430,
                y_loc=280,
                quarter=1,
            ),
        ]
    )
    db_session.commit()

    captured = {}

    def fake_render(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "<html></html>"

    html_instance = mocker.MagicMock()
    html_instance.write_pdf.return_value = b"pdf"

    mocker.patch("core.advanced_pdf_reports.render_template", side_effect=fake_render)
    mocker.patch("core.advanced_pdf_reports.HTML", return_value=html_instance)

    filename, pdf_bytes = AdvancedPDFReports.generate_player_scouting_card(
        "Filter Me", "Season"
    )

    assert filename is not None
    assert pdf_bytes == b"pdf"
    assert captured["template_name"] == "reports/player_scouting_card.html"
    assert captured["context"]["games_played"] == 1
    assert captured["context"]["shot_quality"]["total_shots"] == 1
    assert captured["context"]["has_shot_data"] is True
    assert captured["context"]["shot_chart"] == mocker.ANY


def test_season_trend_report_includes_players_with_fewer_than_three_games(
    db_session, mocker
):
    first_game = Game(
        date="22-03-2026",
        opponent="Trend One",
        team_score=66,
        opponent_score=58,
        result="W",
        game_type="Friendly",
        sort_date="2026-03-22",
        source="IMPORT_JSON",
    )
    second_game = Game(
        date="23-03-2026",
        opponent="Trend Two",
        team_score=71,
        opponent_score=63,
        result="W",
        game_type="Friendly",
        sort_date="2026-03-23",
        source="IMPORT_JSON",
    )
    db_session.add_all([first_game, second_game])
    db_session.flush()

    db_session.add_all(
        [
            PlayerStat(
                game_id=first_game.id,
                player_name="Short Sample",
                minutes="20:00",
                points=9,
                fgm=3,
                fga=8,
                tpm=1,
                tpa=3,
                ftm=2,
                fta=2,
                oreb=1,
                dreb=2,
                reb=3,
                ast=1,
                stl=1,
                blk=0,
                tov=1,
                pf=1,
            ),
            PlayerStat(
                game_id=second_game.id,
                player_name="Short Sample",
                minutes="19:00",
                points=12,
                fgm=4,
                fga=9,
                tpm=2,
                tpa=4,
                ftm=2,
                fta=2,
                oreb=0,
                dreb=3,
                reb=3,
                ast=2,
                stl=0,
                blk=0,
                tov=1,
                pf=2,
            ),
            PlayerStat(
                game_id=first_game.id,
                player_name="Second Player",
                minutes="18:00",
                points=7,
                fgm=3,
                fga=6,
                tpm=1,
                tpa=2,
                ftm=0,
                fta=0,
                oreb=1,
                dreb=1,
                reb=2,
                ast=3,
                stl=1,
                blk=0,
                tov=1,
                pf=1,
            ),
        ]
    )
    db_session.commit()

    captured = {}

    def fake_render(template_name, **context):
        captured["template_name"] = template_name
        captured["context"] = context
        return "<html></html>"

    html_instance = mocker.MagicMock()
    html_instance.write_pdf.return_value = b"pdf"

    mocker.patch("core.advanced_pdf_reports.render_template", side_effect=fake_render)
    mocker.patch("core.advanced_pdf_reports.HTML", return_value=html_instance)

    filename, pdf_bytes = AdvancedPDFReports.generate_season_trend_report(
        player_name="Short Sample",
        game_type="Friendly",
    )

    assert filename is not None
    assert pdf_bytes == b"pdf"
    assert captured["template_name"] == "reports/season_trend_report.html"
    assert captured["context"]["total_games"] == 2
    assert "Short Sample" in captured["context"]["player_trends"]
    assert "Second Player" in captured["context"]["player_trends"]
    assert captured["context"]["player_trends"]["Short Sample"]["games"] == 2
