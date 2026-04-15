import json

from core.models import Game, PlayerStat, LineupSegment, PlayerLineupStats
from core.services.analytics_service import AnalyticsService
from web.routes import reports as reports_module


def test_imported_player_metrics_keep_plus_minus(db_session):
    game = Game(
        date="10-03-2026",
        opponent="Import Opponent",
        team_score=78,
        opponent_score=70,
        result="W",
        game_type="Season",
        sort_date="2026-03-10",
        source="IMPORT",
    )
    db_session.add(game)
    db_session.flush()

    stat = PlayerStat(
        game_id=game.id,
        player_name="Imported Guard",
        minutes="22:00",
        points=14,
        fgm=5,
        fga=10,
        tpm=2,
        tpa=4,
        ftm=2,
        fta=2,
        oreb=1,
        dreb=3,
        reb=4,
        ast=4,
        stl=1,
        blk=0,
        tov=2,
        pf=2,
        plus_minus=7,
        reb_conceded=3,
    )
    db_session.add(stat)
    db_session.commit()

    report = AnalyticsService.calculate_player_metrics([stat], {game.id: game}, 1)
    box_detail = reports_module._build_player_box_detail([stat], 1)

    assert report["advanced"]["avg_plus_minus"] == 7.0
    assert report["game_logs"][0]["plus_minus"] == 7
    assert box_detail["totals"]["plus_minus"] == 7
    assert box_detail["totals"]["reb_conceded"] == 3


def test_imported_team_box_detail_keeps_plus_minus_and_reb_conceded(db_session):
    game = Game(
        date="11-03-2026",
        opponent="Team Import Opponent",
        team_score=81,
        opponent_score=73,
        result="W",
        game_type="Season",
        sort_date="2026-03-11",
        source="IMPORT",
    )
    db_session.add(game)
    db_session.flush()

    db_session.add_all(
        [
            PlayerStat(
                game_id=game.id,
                player_name="Player A",
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
                pf=2,
                plus_minus=5,
                reb_conceded=2,
            ),
            PlayerStat(
                game_id=game.id,
                player_name="Player B",
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
                pf=1,
                plus_minus=-1,
                reb_conceded=1,
            ),
        ]
    )
    db_session.commit()

    detail = reports_module._build_team_box_detail([game.id], [game])

    assert detail["live_plus_minus_total"] == 4
    assert detail["totals"]["reb_conceded"] == 3


def test_player_box_detail_falls_back_to_lineup_reb_conceded(db_session):
    game = Game(
        date="12-03-2026",
        opponent="Lineup Rebound Opponent",
        team_score=75,
        opponent_score=67,
        result="W",
        game_type="Season",
        sort_date="2026-03-12",
        source="IMPORT_JSON",
    )
    db_session.add(game)
    db_session.flush()

    stat = PlayerStat(
        game_id=game.id,
        player_name="Tracked Wing",
        minutes="20:00",
        points=12,
        fgm=5,
        fga=9,
        tpm=1,
        tpa=3,
        ftm=1,
        fta=2,
        oreb=1,
        dreb=4,
        reb=5,
        ast=2,
        stl=1,
        blk=0,
        tov=1,
        pf=2,
        plus_minus=3,
        reb_conceded=0,
    )
    db_session.add(stat)
    db_session.flush()

    segment = LineupSegment(
        game_id=game.id,
        start_timestamp=1,
        end_timestamp=2,
        quarter=1,
        players=["Tracked Wing", "A", "B", "C", "D"],
        lineup_hash="hash",
        reb_conceded=2,
    )
    db_session.add(segment)
    db_session.flush()

    db_session.add(
        PlayerLineupStats(
            lineup_segment_id=segment.id,
            player_name="Tracked Wing",
            reb_conceded=2,
        )
    )
    db_session.commit()

    detail = reports_module._build_player_box_detail([stat], 1)

    assert detail["totals"]["reb_conceded"] == 2
    assert detail["per_game"]["reb_conceded"] == 2.0


def test_team_box_detail_falls_back_to_lineup_reb_conceded(db_session):
    game = Game(
        date="13-03-2026",
        opponent="Team Lineup Rebound Opponent",
        team_score=68,
        opponent_score=60,
        result="W",
        game_type="Season",
        sort_date="2026-03-13",
        source="IMPORT_JSON",
    )
    db_session.add(game)
    db_session.flush()

    db_session.add(
        PlayerStat(
            game_id=game.id,
            player_name="Player A",
            minutes="18:00",
            points=8,
            fgm=3,
            fga=7,
            tpm=0,
            tpa=1,
            ftm=2,
            fta=2,
            oreb=1,
            dreb=3,
            reb=4,
            ast=1,
            stl=0,
            blk=0,
            tov=1,
            pf=2,
            plus_minus=2,
            reb_conceded=0,
        )
    )
    db_session.flush()

    db_session.add(
        LineupSegment(
            game_id=game.id,
            start_timestamp=1,
            end_timestamp=2,
            quarter=1,
            players=["Player A", "B", "C", "D", "E"],
            lineup_hash="hash2",
            reb_conceded=3,
        )
    )
    db_session.commit()

    detail = reports_module._build_team_box_detail([game.id], [game])

    assert detail["totals"]["reb_conceded"] == 3
    assert detail["per_game"]["reb_conceded"] == 3.0


def test_player_box_detail_uses_tracked_game_count_for_tracked_stats(db_session):
    tracked_game = Game(
        date="14-03-2026",
        opponent="Tracked Opponent",
        team_score=70,
        opponent_score=61,
        result="W",
        game_type="Season",
        sort_date="2026-03-14",
        source="IMPORT_JSON",
        schema_version=4,
    )
    untracked_game = Game(
        date="15-03-2026",
        opponent="Legacy Opponent",
        team_score=65,
        opponent_score=60,
        result="W",
        game_type="Season",
        sort_date="2026-03-15",
        source="MANUAL",
        schema_version=1,
    )
    db_session.add_all([tracked_game, untracked_game])
    db_session.flush()

    tracked_stat = PlayerStat(
        game_id=tracked_game.id,
        player_name="Schema Aware",
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
        pf=2,
        plus_minus=6,
        reb_conceded=0,
    )
    untracked_stat = PlayerStat(
        game_id=untracked_game.id,
        player_name="Schema Aware",
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
        pf=1,
        plus_minus=0,
        reb_conceded=0,
    )
    db_session.add_all([tracked_stat, untracked_stat])
    db_session.flush()

    segment = LineupSegment(
        game_id=tracked_game.id,
        start_timestamp=1,
        end_timestamp=2,
        quarter=1,
        players=["Schema Aware", "B", "C", "D", "E"],
        lineup_hash="tracked-schema-hash",
        reb_conceded=4,
    )
    db_session.add(segment)
    db_session.flush()
    db_session.add(
        PlayerLineupStats(
            lineup_segment_id=segment.id,
            player_name="Schema Aware",
            reb_conceded=4,
        )
    )
    db_session.commit()

    detail = reports_module._build_player_box_detail([tracked_stat, untracked_stat], 2)

    assert detail["tracked_plus_minus_games"] == 1
    assert detail["tracked_reb_conceded_games"] == 1
    assert detail["per_game"]["plus_minus"] == 6.0
    assert detail["per_game"]["reb_conceded"] == 4.0


def test_live_game_save_persists_reb_conceded_and_plus_minus(auth_client, db_session):
    payload = {
        "opponent": "Tracked Save Opponent",
        "date": "2026-03-12",
        "game_type": "Friendly",
        "team_score": 66,
        "opponent_score": 61,
        "player_stats": {
            "Tracked Player": {
                "minutes": "15:00",
                "points": 9,
                "fgm": 4,
                "fga": 7,
                "tpm": 1,
                "tpa": 2,
                "ftm": 0,
                "fta": 0,
                "oreb": 1,
                "dreb": 2,
                "reb": 3,
                "ast": 2,
                "tov": 1,
                "stl": 1,
                "blk": 0,
                "pf": 2,
                "plus_minus": 6,
                "reb_conceded": 4,
            }
        },
        "events": [],
    }

    response = auth_client.post(
        "/live-game/save",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 201

    game = Game.query.filter_by(opponent="Tracked Save Opponent").first()
    stat = PlayerStat.query.filter_by(game_id=game.id, player_name="Tracked Player").one()

    assert stat.plus_minus == 6
    assert stat.reb_conceded == 4
