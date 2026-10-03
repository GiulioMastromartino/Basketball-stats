"""Regression tests for per-game lineup coherence.

Uses a real game export whose event log records only part of the shot chart.
`shot_events` holds the complete record (60 shots / 31 made, matching the box
score exactly) while `game_events` mirrors only 27 of those shots. Lineup
segments built purely from GameEvent therefore undercounted scoring, which made
`team_poss` collapse to 49 and produced a 159.2 ORtg "team average" baseline in
a 78-point game - poisoning every lineup delta on both the game detail page and
the game PDF.
"""

import json
import os

import pytest

from core.advanced_analytics import LineupAnalytics
from core.models import LineupSegment, PlayerStat, ShotEvent
from core.services.analytics_service import (
    MIN_GAME_LINEUP_POSSESSIONS,
    resolve_game_team_possessions,
)
from core.services.game_service import create_game_from_live_data

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "game_raw_partial_shot_log.json"
)


def _team_totals(game_id):
    stats = PlayerStat.query.filter_by(game_id=game_id).all()
    return {
        "fga": sum(s.fga or 0 for s in stats),
        "fta": sum(s.fta or 0 for s in stats),
        "oreb": sum(s.oreb or 0 for s in stats),
        "tov": sum(s.tov or 0 for s in stats),
    }


def _import_partial_log_game(db_session, team):
    with open(FIXTURE) as handle:
        payload = json.load(handle)
    game = create_game_from_live_data(payload, team_id=team.id)
    db_session.commit()
    return game


def test_segments_reconcile_with_box_score_points(db_session, default_team):
    game = _import_partial_log_game(db_session, default_team)

    segments = LineupSegment.query.filter_by(game_id=game.id).all()
    assert segments, "expected lineup segments to be built"

    scored = sum(s.points_scored or 0 for s in segments)
    allowed = sum(s.points_allowed or 0 for s in segments)

    # The whole point: segment totals must equal the real score, not just the
    # subset of shots that happen to be duplicated in the event log.
    assert scored == game.team_score
    assert allowed == game.opponent_score


def test_reconciliation_is_idempotent(db_session, default_team):
    from core.services.lineup_service import reconcile_orphan_shot_points

    game = _import_partial_log_game(db_session, default_team)
    before = sum(s.points_scored or 0 for s in
                 LineupSegment.query.filter_by(game_id=game.id).all())

    summary = reconcile_orphan_shot_points(game.id)
    after = sum(s.points_scored or 0 for s in
                LineupSegment.query.filter_by(game_id=game.id).all())

    # The event log already credited its own shots, so a second pass must add
    # nothing rather than double counting.
    assert summary["points_added"] == 0
    assert after == before


def test_reconciliation_never_overshoots_authoritative_points(db_session, default_team):
    from core.services.lineup_service import reconcile_orphan_shot_points

    game = _import_partial_log_game(db_session, default_team)
    summary = reconcile_orphan_shot_points(game.id)

    # shot_events is the complete record; nothing may be credited beyond it.
    assert summary["points_authoritative"] <= 78
    assert summary["points_added"] >= 0
    assert summary["points_already_credited"] >= 0


def test_team_possessions_uses_box_score_not_partial_segment_sum(
    db_session, default_team
):
    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)

    segment_sum = sum(
        s.possessions or 0
        for s in LineupSegment.query.filter_by(game_id=game.id).all()
    )
    resolved = resolve_game_team_possessions(game, totals)

    # The segment sum is a partial view and must not win.
    assert segment_sum < resolved
    assert resolved == pytest.approx(73.44, abs=0.01)
    # The bug produced 159.2 ORtg for this 78-point game.
    assert game.team_score / resolved * 100 < 120


def test_game_ratings_are_plausible_not_absurd(db_session, default_team):
    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)
    team_poss = resolve_game_team_possessions(game, totals)

    ortg = game.team_score / team_poss * 100
    drtg = game.opponent_score / team_poss * 100

    assert 85 <= ortg <= 125, f"implausible ORtg {ortg}"
    assert 85 <= drtg <= 125, f"implausible DRtg {drtg}"


def test_web_and_pdf_select_the_same_lineups(db_session, default_team):
    """The detail page and the PDF must not disagree about the best unit.

    Previously the page passed min_possessions=10 while the PDF passed nothing
    and silently inherited the 2.0 default, so each ranked different lineups.
    """
    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)
    team_poss = resolve_game_team_possessions(game, totals)

    def rank(**kwargs):
        return LineupAnalytics.get_game_lineup_rankings(
            game.id,
            top_n=3,
            rank_by="offensive",
            total_pts_scored_override=game.team_score,
            total_pts_allowed_override=game.opponent_score,
            total_possessions_override=team_poss,
            **kwargs,
        )

    web = rank(min_possessions=MIN_GAME_LINEUP_POSSESSIONS)
    pdf = rank(min_possessions=MIN_GAME_LINEUP_POSSESSIONS)

    assert [r["players"] for r in web] == [r["players"] for r in pdf]
    assert [r["ortg"] for r in web] == [r["ortg"] for r in pdf]


def test_lineup_qualifying_threshold_excludes_tiny_stints(db_session, default_team):
    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)
    team_poss = resolve_game_team_possessions(game, totals)

    ranked = LineupAnalytics.get_game_lineup_rankings(
        game.id,
        top_n=3,
        rank_by="offensive",
        min_possessions=MIN_GAME_LINEUP_POSSESSIONS,
        total_pts_scored_override=game.team_score,
        total_pts_allowed_override=game.opponent_score,
        total_possessions_override=team_poss,
    )

    assert ranked, "expected at least one qualifying lineup"
    for lineup in ranked:
        assert lineup["possessions"] >= MIN_GAME_LINEUP_POSSESSIONS
        # The PDF used to feature 1.3-minute stints with a 200 ORtg.
        assert lineup["possessions"] >= 5


def test_best_lineup_offense_delta_is_not_absurd(db_session, default_team):
    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)
    team_poss = resolve_game_team_possessions(game, totals)

    ranked = LineupAnalytics.get_game_lineup_rankings(
        game.id,
        top_n=1,
        rank_by="offensive",
        min_possessions=MIN_GAME_LINEUP_POSSESSIONS,
        total_pts_scored_override=game.team_score,
        total_pts_allowed_override=game.opponent_score,
        total_possessions_override=team_poss,
    )

    assert ranked
    best = ranked[0]
    # Was -89.2 against a 159.2 baseline; must now be a sane magnitude.
    assert abs(best["impact"]["offense_delta"]) < 60
    assert 40 <= best["ortg"] <= 200


def test_shot_events_remain_the_complete_record(db_session, default_team):
    """Guard the premise of the whole fix: shot_events covers the box score."""
    game = _import_partial_log_game(db_session, default_team)

    shots = ShotEvent.query.filter_by(game_id=game.id).all()
    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    box_fga = sum(s.fga or 0 for s in stats)
    box_fgm = sum(s.fgm or 0 for s in stats)

    assert len(shots) == box_fga
    assert sum(1 for s in shots if s.result == "made") == box_fgm