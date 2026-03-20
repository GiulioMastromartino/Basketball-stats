import pytest

from core.models import Game, GameEvent, Play, PlayerStat, ShotEvent
from web.routes import reports as reports_module


@pytest.mark.integration
def test_generate_game_pdf_bytes_uses_summary_play_metrics(db_session, mocker):
    game = Game(
        date="20-03-2026",
        opponent="PDF Opponent",
        team_score=5,
        opponent_score=0,
        result="W",
        game_type="Season",
        sort_date="2026-03-20",
        source="MANUAL",
    )
    db_session.add(game)
    db_session.flush()

    play = Play(name="Horns", play_type="Offense", description="Horns action")
    db_session.add(play)
    db_session.flush()

    db_session.add(
        PlayerStat(
            game_id=game.id,
            player_name="Alice",
            minutes="20:00",
            points=5,
            fgm=1,
            fga=2,
            tpm=0,
            tpa=0,
            ftm=3,
            fta=3,
            oreb=0,
            dreb=1,
            reb=1,
            ast=0,
            stl=0,
            blk=0,
            tov=0,
            pf=0,
            plus_minus=5,
            fg_percent=50,
            tp_percent=0,
            ft_percent=100,
        )
    )
    db_session.add_all(
        [
            ShotEvent(
                game_id=game.id,
                player_name="Alice",
                shot_type="2pt",
                result="missed",
                points=0,
                quarter=1,
                play_id=play.id,
            ),
            ShotEvent(
                game_id=game.id,
                player_name="Alice",
                shot_type="2pt",
                result="made",
                points=2,
                quarter=1,
                play_id=play.id,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Alice",
                shot_attempt="missed",
                quarter=1,
                timestamp=1000,
                time_remaining="9:55",
                possession_number=1,
                play_id=play.id,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Alice",
                shot_attempt="made",
                quarter=1,
                timestamp=1010,
                time_remaining="9:45",
                possession_number=1,
                play_id=play.id,
            ),
            GameEvent(
                game_id=game.id,
                event_type="FT",
                player_name="Alice",
                detail='{"ftm": 3, "fta": 3}',
                shot_attempt="made",
                quarter=1,
                timestamp=1020,
                time_remaining="9:20",
                possession_number=2,
                play_id=play.id,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Alice",
                shot_attempt="made",
                quarter=1,
                timestamp=1030,
                time_remaining="9:10",
                possession_number=3,
                play_id=play.id,
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

    mocker.patch.object(reports_module, "render_template", side_effect=fake_render)
    mocker.patch.object(reports_module, "HTML", return_value=html_instance)

    filename, pdf_bytes = reports_module.generate_game_pdf_bytes(game.id)

    assert filename is not None
    assert pdf_bytes == b"pdf"
    assert captured["template_name"] == "game_summary_pdf.html"
    assert captured["context"]["plays_data"][0]["possessions"] == 2
    assert captured["context"]["plays_data"][0]["points"] == 5
    assert captured["context"]["plays_data"][0]["shot_attempts"] == 2
