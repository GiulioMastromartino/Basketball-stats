"""Regression tests: lineup segments from live/SUB-only event logs.

The Trecella Clovers game produced zero LineupSegments on import because
starter inference needed 5 distinct actors before the first SUB_IN (only
2 exist - opponent events carry no player). Starters now come from Q1
SUB_OUTs, and FT points count toward segment offense.
"""
import json

from core.models import GameEvent, LineupSegment
from core.services.lineup_service import (
    build_lineup_segments,
    infer_starting_lineup_from_events,
    parse_ft_event,
    process_game_lineups,
)


def _evt(db_session, game, **kw):
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


def test_parse_ft_event_variants():
    assert parse_ft_event({"ftm": 2, "fta": 2}) == (2, 2)
    assert parse_ft_event({"ftm": 0, "fta": 1}) == (0, 1)
    assert parse_ft_event('{"ftm": 2, "fta": 2}') == (2, 2)
    assert parse_ft_event("{'ftm': 1, 'fta': 1}") == (1, 1)
    # attempts absent: infer up to preserve the make count
    assert parse_ft_event({"ftm": 2}) == (2, 2)
    assert parse_ft_event({"ftm": 1}) == (1, 1)
    # make count absent: infer from the shot result (matches report timeline)
    assert parse_ft_event({"fta": 1}, shot_attempt="made") == (1, 1)
    assert parse_ft_event({"fta": 2}, shot_attempt="missed") == (0, 2)
    assert parse_ft_event({"points": 1}, shot_attempt="made") == (1, 1)
    assert parse_ft_event({"points": 0}, shot_attempt="missed") == (0, 1)
    assert parse_ft_event(None, shot_attempt="made") == (1, 1)
    assert parse_ft_event(None) == (0, 1)


def test_infer_ignores_opponent_events(db_session, sample_game):
    """Named opponent events never count as starters."""
    _evt(db_session, sample_game, event_type="OPP_SCORE", player_name="OppStar",
         detail='{"points": 2}', timestamp=1000)
    for i, s in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert infer_starting_lineup_from_events(events) == ["S1", "S2", "S3", "S4", "S5"]


def test_infer_uses_explicit_quarter_for_later_events(db_session, sample_game):
    """Events after an explicit Q2 marker infer Q2 even without quarter."""
    for i, s in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10)
    _evt(db_session, sample_game, event_type="SHOT_2PT", player_name="Q2A",
         quarter=2, timestamp=5000)
    _evt(db_session, sample_game, event_type="SUB_OUT", player_name="Q2B",
         quarter=None, timestamp=6000)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert infer_starting_lineup_from_events(events) == ["S1", "S2", "S3", "S4", "S5"]


def test_infer_starters_from_sub_outs(db_session, sample_game):
    for i, s in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 2)
        _evt(db_session, sample_game, event_type="SUB_IN", player_name=f"B{i}",
             timestamp=2001 + i * 2)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert infer_starting_lineup_from_events(events) == ["S1", "S2", "S3", "S4", "S5"]


def test_infer_ignores_bench_enter_and_leave(db_session, sample_game):
    for i, s in enumerate(["S1", "S2", "S3"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i)
    _evt(db_session, sample_game, event_type="SUB_IN", player_name="BENCH",
         timestamp=2010)
    _evt(db_session, sample_game, event_type="SUB_OUT", player_name="BENCH",
         timestamp=2020)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert infer_starting_lineup_from_events(events) == []


def test_infer_counts_shooters_before_first_sub(db_session, sample_game):
    """Starters who shoot before any substitution still count, even if one
    never leaves in Q1 (previous behavior preserved)."""
    for i, s in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        _evt(db_session, sample_game, event_type="SHOT_2PT", player_name=s,
             shot_attempt="made", timestamp=1000 + i * 10)
    for i, s in enumerate(["S1", "S2", "S3", "S4"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10)
        _evt(db_session, sample_game, event_type="SUB_IN",
             player_name=f"B{i}", timestamp=2001 + i * 10)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert infer_starting_lineup_from_events(events) == ["S1", "S2", "S3", "S4", "S5"]


def test_infer_uses_next_quarter_for_missing_quarters(db_session, sample_game):
    """Q2 SUB_OUTs with a missing quarter field must not leak into Q1
    starters once a NEXT_QUARTER marker passed."""
    for i, s in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10)
    _evt(db_session, sample_game, event_type="NEXT_QUARTER", timestamp=5000,
         game_seconds=600)
    _evt(db_session, sample_game, event_type="SUB_OUT", player_name="Q2BENCH",
         quarter=None, timestamp=6000, game_seconds=700)
    db_session.commit()
    events = GameEvent.query.filter_by(game_id=sample_game.id).all()
    assert infer_starting_lineup_from_events(events) == ["S1", "S2", "S3", "S4", "S5"]


def test_build_segments_without_explicit_starters(db_session, sample_game):
    """SUB-only live log (no SHOT actors before first sub) still segments."""
    starters = ["S1", "S2", "S3", "S4", "S5"]
    for i, s in enumerate(starters):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10, game_seconds=300 + i * 10)
        _evt(db_session, sample_game, event_type="SUB_IN",
             player_name=f"B{i}", timestamp=2001 + i * 10,
             game_seconds=300 + i * 10)
    db_session.commit()
    events = (
        GameEvent.query.filter_by(game_id=sample_game.id)
        .order_by(GameEvent.timestamp).all()
    )
    ids = build_lineup_segments(sample_game.id, events, None, sample_game.team_id)
    assert len(ids) == 6  # starting unit + one per substitution
    first = LineupSegment.query.get(ids[0])
    assert sorted(first.players) == sorted(starters)


def test_segment_counts_shot_and_ft_points(db_session, sample_game):
    starters = ["S1", "S2", "S3", "S4", "S5"]
    _evt(db_session, sample_game, event_type="SHOT_2PT", player_name="S1",
         shot_attempt="made", timestamp=1000, game_seconds=60,
         possession_number=1)
    _evt(db_session, sample_game, event_type="FT", player_name="S2",
         detail=json.dumps({"ftm": 2, "fta": 2}), timestamp=1100,
         game_seconds=120, possession_number=2)
    _evt(db_session, sample_game, event_type="OPP_SCORE",
         detail=json.dumps({"points": 3, "shot_type": "3pt", "result": "made"}),
         timestamp=1200, game_seconds=180, possession_number=3)
    for i, s in enumerate(starters):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10, game_seconds=300 + i * 10)
        _evt(db_session, sample_game, event_type="SUB_IN",
             player_name=f"B{i}", timestamp=2001 + i * 10,
             game_seconds=300 + i * 10)
    db_session.commit()
    events = (
        GameEvent.query.filter_by(game_id=sample_game.id)
        .order_by(GameEvent.timestamp).all()
    )
    process_game_lineups(sample_game.id, events, None, sample_game.team_id)
    seg = (
        LineupSegment.query.filter_by(game_id=sample_game.id)
        .order_by(LineupSegment.start_timestamp).first()
    )
    assert sorted(seg.players) == sorted(starters)
    assert seg.points_scored == 4  # 2 (FG) + 2 (FT detail)
    assert seg.points_allowed == 3
    assert seg.possessions == 2
    assert seg.duration_seconds and seg.duration_seconds > 0


def test_segment_infers_team_points_without_shot_events(db_session, sample_game):
    """Split-format log (no SHOT_2PT/SHOT_3PT events): segment offense comes
    from net score_margin movement; possessions from possession ids."""
    _evt(db_session, sample_game, event_type="OPP_SCORE",
         detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
         score_margin=-2, timestamp=100, game_seconds=100, possession_number=1)
    _evt(db_session, sample_game, event_type="OPP_SCORE",
         detail=json.dumps({"points": 0, "shot_type": "2pt", "result": "missed"}),
         score_margin=1, timestamp=200, game_seconds=200, possession_number=2)
    _evt(db_session, sample_game, event_type="OPP_SCORE",
         detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
         score_margin=1, timestamp=300, game_seconds=300, possession_number=3)
    for i, s in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        _evt(db_session, sample_game, event_type="SUB_OUT", player_name=s,
             timestamp=2000 + i * 10, game_seconds=600 + i * 10)
        _evt(db_session, sample_game, event_type="SUB_IN",
             player_name=f"B{i}", timestamp=2001 + i * 10,
             game_seconds=600 + i * 10)
    db_session.commit()
    events = (
        GameEvent.query.filter_by(game_id=sample_game.id)
        .order_by(GameEvent.timestamp).all()
    )
    process_game_lineups(sample_game.id, events, None, sample_game.team_id)
    seg = (
        LineupSegment.query.filter_by(game_id=sample_game.id)
        .order_by(LineupSegment.start_timestamp).first()
    )
    # implied team: 0 -> 3 -> 5, so 5 points; allowed 2 + 0 + 2 = 4
    assert seg.points_scored == 5
    assert seg.points_allowed == 4
    # 3 distinct possession ids -> round(3/2) = 2 team possessions
    assert seg.possessions == 2
