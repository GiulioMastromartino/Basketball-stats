import pytest

from core.models import Game, GameEvent, Play, PlayerStat, ShotEvent
from core.play_analytics import (
    get_play_player_stats,
    get_play_stats,
    get_player_play_stats,
    get_summary_play_player_stats,
    get_summary_play_stats,
    get_summary_player_play_stats,
)


def _seed_game_with_player(db_session):
    game = Game(
        date="20-03-2026",
        opponent="Analytics Opponent",
        team_score=7,
        opponent_score=0,
        result="W",
        game_type="Season",
        sort_date="2026-03-20",
        source="MANUAL",
    )
    db_session.add(game)
    db_session.flush()

    player = PlayerStat(
        game_id=game.id,
        player_name="Alice",
        minutes="20:00",
        points=7,
        fgm=2,
        fga=3,
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
        tov=1,
        pf=0,
        plus_minus=7,
        fg_percent=66.7,
        tp_percent=0,
        ft_percent=100,
    )
    db_session.add(player)

    horns = Play(name="Horns", play_type="Offense", description="Horns action")
    delay = Play(name="Delay", play_type="Offense", description="Delay action")
    db_session.add_all([horns, delay])
    db_session.flush()

    db_session.add_all(
        [
            ShotEvent(
                game_id=game.id,
                player_name="Alice",
                shot_type="2pt",
                result="missed",
                points=0,
                quarter=1,
                play_id=horns.id,
            ),
            ShotEvent(
                game_id=game.id,
                player_name="Alice",
                shot_type="2pt",
                result="made",
                points=2,
                quarter=1,
                play_id=horns.id,
            ),
            ShotEvent(
                game_id=game.id,
                player_name="Alice",
                shot_type="2pt",
                result="made",
                points=2,
                quarter=1,
                play_id=delay.id,
            ),
        ]
    )
    db_session.add_all(
        [
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Alice",
                shot_attempt="missed",
                quarter=1,
                timestamp=1000,
                time_remaining="9:55",
                possession_number=1,
                play_id=horns.id,
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
                play_id=horns.id,
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
                play_id=horns.id,
            ),
            GameEvent(
                game_id=game.id,
                event_type="TURNOVER",
                player_name="Alice",
                quarter=1,
                timestamp=1030,
                time_remaining="9:00",
                possession_number=3,
                play_id=delay.id,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Alice",
                shot_attempt="made",
                quarter=1,
                timestamp=1040,
                time_remaining="8:40",
                possession_number=4,
                play_id=delay.id,
            ),
        ]
    )
    db_session.commit()
    return game, horns, delay


@pytest.mark.integration
def test_game_page_play_stats_use_legacy_shot_driven_semantics(db_session):
    game, horns, delay = _seed_game_with_player(db_session)

    plays = get_play_stats(game.id)
    horns_row = next(play for play in plays if play["id"] == horns.id)
    delay_row = next(play for play in plays if play["id"] == delay.id)

    assert horns_row["possessions"] == 2
    assert horns_row["points"] == 2
    assert horns_row["ppp"] == 1.0
    assert horns_row["fg_pct"] == 50.0
    assert horns_row["efg_pct"] == 50.0
    assert horns_row["score_pct"] == 50.0

    assert delay_row["possessions"] == 2
    assert delay_row["points"] == 2
    assert delay_row["turnovers"] == 1
    assert delay_row["tov_pct"] == 50.0
    assert delay_row["score_pct"] == 50.0


@pytest.mark.integration
def test_game_page_player_breakdowns_ignore_standalone_event_shots(db_session):
    game, horns, _delay = _seed_game_with_player(db_session)

    play_players = get_play_player_stats(game.id)
    player_plays = get_player_play_stats(game.id)

    horns_players = next(play for play in play_players if play["id"] == horns.id)
    alice_from_play = horns_players["players"][0]

    alice = next(player for player in player_plays if player["player_name"] == "Alice")
    horns_from_player = next(play for play in alice["plays"] if play["id"] == horns.id)

    assert alice_from_play["possessions"] == 2
    assert alice_from_play["points"] == 2
    assert horns_from_player["possessions"] == 2
    assert horns_from_player["points"] == 2


@pytest.mark.integration
def test_summary_play_stats_use_true_possessions_and_free_throws(db_session):
    game, horns, delay = _seed_game_with_player(db_session)

    plays = get_summary_play_stats(game.id)
    horns_row = next(play for play in plays if play["id"] == horns.id)
    delay_row = next(play for play in plays if play["id"] == delay.id)

    assert horns_row["possessions"] == 2
    assert horns_row["points"] == 5
    assert horns_row["ppp"] == 2.5
    assert horns_row["fg_pct"] == 50.0
    assert horns_row["efg_pct"] == 50.0
    assert horns_row["score_pct"] == 100.0
    assert horns_row["estimated_possessions"] is False

    assert delay_row["possessions"] == 2
    assert delay_row["turnovers"] == 1
    assert delay_row["tov_pct"] == 50.0
    assert delay_row["score_pct"] == 50.0


@pytest.mark.integration
def test_summary_player_breakdowns_share_summary_metrics(db_session):
    game, horns, _delay = _seed_game_with_player(db_session)

    play_players = get_summary_play_player_stats(game.id)
    player_plays = get_summary_player_play_stats(game.id)

    horns_players = next(play for play in play_players if play["id"] == horns.id)
    alice_from_play = horns_players["players"][0]

    alice = next(player for player in player_plays if player["player_name"] == "Alice")
    horns_from_player = next(play for play in alice["plays"] if play["id"] == horns.id)

    assert alice_from_play["possessions"] == 2
    assert alice_from_play["points"] == 5
    assert horns_from_player["possessions"] == 2
    assert horns_from_player["points"] == 5
    assert horns_from_player["score_pct"] == 100.0


@pytest.mark.integration
def test_summary_play_stats_ignore_unmatched_shot_game_events(db_session):
    game, horns, _delay = _seed_game_with_player(db_session)
    db_session.add(
        GameEvent(
            game_id=game.id,
            event_type="SHOT_2PT",
            player_name="Alice",
            shot_attempt="made",
            quarter=1,
            timestamp=2000,
            time_remaining="7:00",
            possession_number=5,
            play_id=horns.id,
        )
    )
    db_session.commit()

    plays = get_summary_play_stats(game.id)
    horns_row = next(play for play in plays if play["id"] == horns.id)

    assert horns_row["possessions"] == 2
    assert horns_row["shot_attempts"] == 2
    assert horns_row["points"] == 5


@pytest.mark.integration
def test_summary_play_stats_fall_back_when_possession_numbers_are_missing(db_session):
    game = Game(
        date="20-03-2026",
        opponent="Fallback Opponent",
        team_score=2,
        opponent_score=0,
        result="W",
        game_type="Season",
        sort_date="2026-03-20",
        source="MANUAL",
    )
    db_session.add(game)
    db_session.flush()

    play = Play(name="Chicago", play_type="Offense", description="Chicago action")
    db_session.add(play)
    db_session.flush()

    db_session.add(
        PlayerStat(
            game_id=game.id,
            player_name="Alice",
            minutes="10:00",
            points=2,
            fgm=1,
            fga=1,
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
            plus_minus=2,
            fg_percent=100,
            tp_percent=0,
            ft_percent=0,
        )
    )
    db_session.add(
        ShotEvent(
            game_id=game.id,
            player_name="Alice",
            shot_type="2pt",
            result="made",
            points=2,
            quarter=1,
            play_id=play.id,
        )
    )
    db_session.add(
        GameEvent(
            game_id=game.id,
            event_type="SHOT_2PT",
            player_name="Alice",
            shot_attempt="made",
            quarter=1,
            timestamp=1000,
            time_remaining="9:50",
            possession_number=None,
            play_id=play.id,
        )
    )
    db_session.commit()

    plays = get_summary_play_stats(game.id)
    assert len(plays) == 1
    assert plays[0]["possessions"] == 1
    assert plays[0]["points"] == 2
    assert plays[0]["estimated_possessions"] is True
