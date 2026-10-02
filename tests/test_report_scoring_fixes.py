"""Regression tests for game-summary computation fixes (Trecella Clovers game).

Covers:
- quarterly points use tracked FTs per quarter (not proportional distribution)
- top-performer dict shape matches the PDF templates
- starting lineup comes from first Q1 SUB_OUTs (starters), not SUB_INs
- opponent live FTs ({"points": ..} detail) count toward FTM/PTS
- scoring runs see team baskets inferred from score_margin jumps
"""
import json

from core.models import GameEvent, PlayerStat, ShotEvent
from core.services.analytics_service import AnalyticsService
from core.services.report_service import (
    _build_time_progression,
    _get_opponent_box_score_from_events,
    _get_shot_scoring_data,
    _get_starting_lineup_from_events,
)


def _game_event(db_session, game, **kw):
    base = dict(
        game_id=game.id,
        quarter=1,
        timestamp=1000,
        game_seconds=60,
        time_remaining="9:00",
        score_margin=0,
    )
    base.update(kw)
    evt = GameEvent(**base)
    db_session.add(evt)
    return evt


def test_quarterly_points_use_actual_ft_quarter(db_session, sample_game):
    """FT points must land in the quarter of the FT event (Q3=15/Q4=13 case)."""
    db_session.add(
        PlayerStat(
            game_id=sample_game.id, player_name="A", minutes="20:00",
            points=27, fgm=12, fga=24, tpm=0, tpa=0, ftm=3, fta=4,
            oreb=0, dreb=0, reb=0, ast=0, stl=0, blk=0, tov=0, pf=0,
        )
    )
    # Q3: 14 FG pts, Q4: 10 FG pts (mirrors the Trecella split)
    for i in range(7):
        db_session.add(
            ShotEvent(game_id=sample_game.id, player_name="A", shot_type="2pt",
                      result="made", points=2, quarter=3)
        )
    for i in range(5):
        db_session.add(
            ShotEvent(game_id=sample_game.id, player_name="A", shot_type="2pt",
                      result="made", points=2, quarter=4)
        )
    # Actual FTs: 1 in Q3, 2 in Q4 (proportional split would give 2/1)
    _game_event(db_session, sample_game, event_type="FT", quarter=3,
                detail=json.dumps({"ftm": 1, "fta": 2}), game_seconds=1700)
    _game_event(db_session, sample_game, event_type="FT", quarter=4,
                detail=json.dumps({"ftm": 2, "fta": 2}), game_seconds=1900)
    db_session.commit()

    data = _get_shot_scoring_data(sample_game.id)
    assert data["quarterly_points"][3] == 15
    assert data["quarterly_points"][4] == 12


def test_top_performers_match_pdf_template_keys(db_session, sample_game):
    db_session.add(
        PlayerStat(
            game_id=sample_game.id, player_name="Top Scorer", minutes="20:00",
            points=22, fgm=8, fga=14, tpm=4, tpa=6, ftm=2, fta=2,
            oreb=2, dreb=4, reb=6, ast=1, stl=1, blk=1, tov=1, pf=2,
        )
    )
    db_session.add(
        PlayerStat(
            game_id=sample_game.id, player_name="Role Player", minutes="10:00",
            points=2, fgm=1, fga=3, tpm=0, tpa=1, ftm=0, fta=0,
            oreb=0, dreb=1, reb=1, ast=1, stl=0, blk=0, tov=1, pf=1,
        )
    )
    db_session.commit()
    stats = PlayerStat.query.filter_by(game_id=sample_game.id).all()
    swm = AnalyticsService.calculate_game_stats(stats)
    leaders = AnalyticsService.get_game_top_performers(swm)
    assert leaders["points"]["player_name"] == "Top Scorer"
    assert leaders["points"]["points"] == 22
    assert leaders["rebounds"]["player_name"] == "Top Scorer"
    assert leaders["rebounds"]["reb"] == 6
    assert leaders["efficiency"]["player_name"]
    assert leaders["efficiency"]["eff"] is not None


def test_starting_lineup_uses_first_sub_outs(db_session, sample_game):
    """First Q1 SUB_OUTs are the starters; first SUB_INs are the bench."""
    starters = ["S1", "S2", "S3", "S4", "S5"]
    bench = ["B1", "B2", "B3", "B4", "B5"]
    for i, (s, b) in enumerate(zip(starters, bench)):
        _game_event(db_session, sample_game, event_type="SUB_OUT",
                    player_name=s, timestamp=2000 + i * 2, game_seconds=300 + i)
        _game_event(db_session, sample_game, event_type="SUB_IN",
                    player_name=b, timestamp=2001 + i * 2, game_seconds=300 + i)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert _get_starting_lineup_from_events(events) == starters


def test_starting_lineup_ignores_bench_enter_and_leave(db_session, sample_game):
    """A bench player who SUB_INs then SUB_OUTs in Q1 is not a starter;
    with fewer than 5 identified starters the segment fallback applies."""
    for i, s in enumerate(["S1", "S2", "S3"]):
        _game_event(db_session, sample_game, event_type="SUB_OUT",
                    player_name=s, timestamp=2000 + i * 2, game_seconds=300 + i)
    _game_event(db_session, sample_game, event_type="SUB_IN",
                player_name="BENCH", timestamp=2010, game_seconds=310)
    _game_event(db_session, sample_game, event_type="SUB_OUT",
                player_name="BENCH", timestamp=2020, game_seconds=320)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert _get_starting_lineup_from_events(events) == []


def test_opponent_live_free_throws_counted(db_session, sample_game):
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=4,
                detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
                score_margin=-2)
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=4,
                detail=json.dumps({"points": 1, "shot_type": "ft", "result": "made"}),
                score_margin=-3)
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=4,
                detail=json.dumps({"points": 0, "shot_type": "ft", "result": "missed"}),
                score_margin=-3)
    db_session.commit()
    box = _get_opponent_box_score_from_events(sample_game.id)
    assert box.pts == 3
    assert box.ftm == 1
    assert box.fta == 2


def test_scoring_runs_see_team_baskets(db_session, sample_game):
    """Team points inferred from margin jumps must create team runs and
    break opponent runs (no phantom 29-0)."""
    sample_game.team_score = 12
    sample_game.opponent_score = 10
    # Opp scores 2 (margin 0 -> -2), then team answers 5 across two
    # OPP_SCORE events recorded with rising margins, then opp scores 2.
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=1,
                detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
                score_margin=-2, game_seconds=100)
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=1,
                detail=json.dumps({"points": 0, "shot_type": "2pt", "result": "missed"}),
                score_margin=0, game_seconds=200)
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=1,
                detail=json.dumps({"points": 0, "shot_type": "3pt", "result": "missed"}),
                score_margin=3, game_seconds=300)
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=1,
                detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
                score_margin=1, game_seconds=400)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    tp = _build_time_progression(events, sample_game)
    types = {r["type"] for r in tp["runs"]}
    assert "team" in types
    assert ("team", 5) in {(r["type"], r["points"]) for r in tp["runs"]}
    assert tp["max_lead"]["team"] == 3
    assert tp["max_lead"]["opp"] == 2
    for run in tp["runs"]:
        # margins here swing -2..+3, so no run can exceed 5 points
        assert run["points"] <= 5


def test_lead_change_within_single_event(db_session, sample_game):
    """Inferred team points are recorded before the opponent's points, so
    a lead change inside one OPP_SCORE event is counted and the transient
    max lead is tracked."""
    sample_game.team_score = 11
    sample_game.opponent_score = 12
    # Opp trails 8-10, team inferred +3 takes the lead 11-10, opp +2 retakes.
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=1,
                detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
                score_margin=-2, game_seconds=100)
    _game_event(db_session, sample_game, event_type="OPP_SCORE", quarter=1,
                detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
                score_margin=-1, game_seconds=200)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    tp = _build_time_progression(events, sample_game)
    # opp -> team (inferred +3) -> opp: two genuine lead changes, and the
    # transient 1-pt team lead is tracked as max lead.
    assert tp["lead_changes"] == 2
    assert tp["max_lead"]["team"] == 1
    assert tp["max_lead"]["opp"] == 2
