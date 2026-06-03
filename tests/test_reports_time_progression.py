import json

from web import create_app, db
from web.routes.reports import _build_time_progression
from core.models import Game, GameEvent, PlayType


def test_build_time_progression_counts_team_field_goals_in_runs():
    app = create_app("testing")

    with app.app_context():
        db.create_all()
        if PlayType.query.count() == 0:
            db.session.add_all(
                [
                    PlayType(name="Offense"),
                    PlayType(name="Defense"),
                    PlayType(name="Special"),
                ]
            )

        game = Game(
            date="01/01/2024",
            opponent="TestOpp",
            team_score=5,
            opponent_score=2,
            result="W",
            game_type="Season",
            sort_date="2024-01-01",
            source="MANUAL",
        )
        db.session.add(game)
        db.session.flush()

        events = [
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Player1",
                quarter=1,
                timestamp=1000,
                shot_attempt="made",
                time_remaining="9:50",
                game_seconds=10,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_3PT",
                player_name="Player1",
                quarter=1,
                timestamp=2000,
                shot_attempt="made",
                time_remaining="9:30",
                game_seconds=30,
            ),
            GameEvent(
                game_id=game.id,
                event_type="OPP_SCORE",
                quarter=1,
                timestamp=3000,
                time_remaining="9:10",
                game_seconds=50,
                detail=json.dumps({"points": 2}),
                score_margin=3,
            ),
        ]
        db.session.add_all(events)
        db.session.commit()

        progression = _build_time_progression(events, game)

        assert len(progression["runs"]) == 1
        assert progression["runs"][0]["type"] == "team"
        assert progression["runs"][0]["points"] == 5

        db.session.remove()
        db.drop_all()
