import pytest

from core.models import Game, GameEvent, Play, PlayerStat, ShotEvent


@pytest.mark.integration
def test_game_detail_renders_legacy_play_metrics(auth_client, db_session):
    game = Game(
        date="20-03-2026",
        opponent="Rendered Opponent",
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
        ]
    )
    db_session.commit()

    response = auth_client.get(f"/game/{game.id}")

    assert response.status_code == 200
    assert b"Horns" in response.data
    assert b"1.00" in response.data
    assert b"50.0%" in response.data
