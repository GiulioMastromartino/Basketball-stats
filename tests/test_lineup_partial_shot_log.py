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


def _rewind_to_event_derived(game_id):
    """Restore the pre-reconciliation segment totals.

    Import already reconciles, so tests exercising the shortfall path must put
    the segments back into their raw event-derived state. Recalculating from the
    event log is exactly that state - and unlike zeroing the column it keeps the
    free throws, which reconciliation never restores.
    """
    from core.services.lineup_service import calculate_segment_stats

    for segment in LineupSegment.query.filter_by(game_id=game_id).all():
        calculate_segment_stats(segment.id)
    from core.models import db

    db.session.commit()


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

    # 67 field-goal points in the box score (56 two-point + 5 three-point... as
    # recorded by shot_events), of which the log only credited part.
    assert summary["points_authoritative"] == 67

    # The real invariant: reconciled segment points never exceed the real score,
    # and a repeat pass has nothing left to add.
    scored = sum(
        s.points_scored or 0
        for s in LineupSegment.query.filter_by(game_id=game.id).all()
    )
    assert scored == game.team_score
    assert summary["points_added"] == 0

    # Rewinding and re-running reproduces the same total, never more.
    _rewind_to_event_derived(game.id)
    again = reconcile_orphan_shot_points(game.id)
    scored_again = sum(
        s.points_scored or 0
        for s in LineupSegment.query.filter_by(game_id=game.id).all()
    )
    assert again["points_added"] > 0
    assert scored_again == game.team_score


def test_reconciliation_credits_no_unlinked_events(db_session, default_team):
    """Events with no segment never reached a segment total.

    Counting them as already-credited would shrink the shortfall and silently
    reintroduce undercounting.
    """
    from core.models import GameEvent
    from core.services.lineup_service import reconcile_orphan_shot_points

    game = _import_partial_log_game(db_session, default_team)

    linked = (
        db_session.query(GameEvent)
        .filter(
            GameEvent.game_id == game.id,
            GameEvent.event_type.in_(("SHOT_2PT", "SHOT_3PT")),
            GameEvent.shot_attempt == "made",
            GameEvent.lineup_segment_id.isnot(None),
        )
        .count()
    )

    _rewind_to_event_derived(game.id)
    baseline = reconcile_orphan_shot_points(game.id)
    assert baseline["points_already_credited"] == 30

    # Detach the shot events: they contributed to no segment, so they must stop
    # counting as already-credited and the shortfall must grow to compensate.
    db_session.query(GameEvent).filter(
        GameEvent.game_id == game.id,
        GameEvent.event_type.in_(("SHOT_2PT", "SHOT_3PT")),
    ).update({"lineup_segment_id": None})
    db_session.commit()

    _rewind_to_event_derived(game.id)
    detached = reconcile_orphan_shot_points(game.id)
    assert detached["points_already_credited"] == 0
    assert detached["points_added"] == 67
    assert linked >= 0


def test_segment_possessions_reconcile_with_box_score(db_session, default_team):
    """Possessions must be corrected on the same basis as points.

    Reconciling points while leaving possessions at their partial event-derived
    values would mix a corrected numerator with an uncorrected denominator and
    inflate every lineup rate.
    """
    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)
    box_possessions = resolve_game_team_possessions(game, totals)

    tracked = sum(
        s.possessions or 0
        for s in LineupSegment.query.filter_by(game_id=game.id).all()
    )
    assert tracked == pytest.approx(round(box_possessions), abs=1)


def test_largest_remainder_splits_exactly_and_deterministically():
    from core.services.lineup_service import _largest_remainder

    weights = [100, 50, 25]
    for total in (0, 1, 7, 100):
        shares = _largest_remainder(total, weights)
        assert sum(shares) == total
        assert shares == _largest_remainder(total, weights)
        assert all(s >= 0 for s in shares)

    # Heavier stints receive at least as much as lighter ones.
    shares = _largest_remainder(100, weights)
    assert shares[0] >= shares[1] >= shares[2]

    # Zero weights fall back to an even spread rather than dividing by zero.
    even = _largest_remainder(5, [0, 0, 0])
    assert sum(even) == 5
    assert max(even) - min(even) <= 1

    assert _largest_remainder(5, []) == []


def test_reconciliation_skips_players_with_no_stint(db_session, default_team):
    """A shooter with no stint in a quarter has no defensible segment."""
    from core.models import ShotEvent
    from core.services.lineup_service import reconcile_orphan_shot_points

    game = _import_partial_log_game(db_session, default_team)

    # Give one shot an impossible quarter so no stint can match it, and rewind
    # the segments so there is a shortfall to distribute.
    orphan = (
        ShotEvent.query.filter_by(game_id=game.id, result="made")
        .order_by(ShotEvent.id)
        .first()
    )
    assert orphan is not None
    original_quarter = orphan.quarter
    orphan.quarter = 99
    db_session.commit()
    _rewind_to_event_derived(game.id)

    summary = reconcile_orphan_shot_points(game.id)
    assert summary["unattributable_players"] >= 1

    orphan.quarter = original_quarter
    db_session.commit()


def test_backfill_recalculation_does_not_revert_the_fix(
    db_session, default_team
):
    """calculate_segment_stats() rebuilds from the log alone.

    Any path that recalculates segments must re-run reconciliation, or the fix
    is silently reverted.
    """
    from core.services.lineup_service import (
        calculate_segment_stats,
        reconcile_orphan_shot_points,
    )

    game = _import_partial_log_game(db_session, default_team)

    def total_points():
        return sum(
            s.points_scored or 0
            for s in LineupSegment.query.filter_by(game_id=game.id).all()
        )

    reconciled = total_points()
    assert reconciled == game.team_score

    for segment in LineupSegment.query.filter_by(game_id=game.id).all():
        calculate_segment_stats(segment.id)
    assert total_points() < game.team_score, "recalculation drops the fix"

    reconcile_orphan_shot_points(game.id)
    assert total_points() == game.team_score


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


def test_web_and_pdf_select_the_same_lineups(db_session, default_team, mocker):
    """The detail page and the PDF must not disagree about the best unit.

    Previously the page passed min_possessions=10 while the PDF passed nothing
    and silently inherited the 2.0 default, so each ranked different lineups.
    This drives both production builders and compares what they hand the
    template, rather than re-calling the ranking helper twice.
    """
    from core.services.analytics_service import AnalyticsService
    from core.services import report_service

    game = _import_partial_log_game(db_session, default_team)

    captured = {}

    def spy(*args, **kwargs):
        captured.setdefault("calls", []).append(kwargs)
        return []

    # Both modules import LineupAnalytics lazily inside the function, so the
    # single shared definition in core.advanced_analytics is the patch point.
    mocker.patch(
        "core.advanced_analytics.LineupAnalytics.get_game_lineup_rankings",
        side_effect=spy,
    )
    # Isolate the surrounding report rendering.
    mocker.patch.object(
        report_service, "render_template", return_value="<html></html>"
    )
    mocker.patch.object(report_service.HTML, "write_pdf", return_value=b"pdf")

    AnalyticsService.build_game_detail(game.id)
    web_calls = list(captured["calls"])
    captured["calls"] = []
    report_service.generate_game_pdf_bytes(game.id)
    pdf_calls = list(captured["calls"])

    assert web_calls, "detail page did not rank any lineups"
    assert pdf_calls, "PDF did not rank any lineups"

    # Both must apply the same qualification threshold...
    for call in web_calls + pdf_calls:
        assert call.get("min_possessions") == MIN_GAME_LINEUP_POSSESSIONS

    # ...and the same possessions baseline.
    web_poss = {c.get("total_possessions_override") for c in web_calls}
    pdf_poss = {c.get("total_possessions_override") for c in pdf_calls}
    assert web_poss == pdf_poss

    # The baseline must be the box score, not the partial segment sum.
    totals = _team_totals(game.id)
    expected = resolve_game_team_possessions(game, totals)
    for value in web_poss | pdf_poss:
        assert value == pytest.approx(expected)


def test_production_paths_rank_identical_lineups(
    db_session, default_team, mocker
):
    """End-to-end: both surfaces must produce the same ordering and ratings."""
    from core.services.analytics_service import AnalyticsService
    from core.services import report_service

    game = _import_partial_log_game(db_session, default_team)
    totals = _team_totals(game.id)
    team_poss = resolve_game_team_possessions(game, totals)
    original_rank = LineupAnalytics.get_game_lineup_rankings

    detail_ctx = AnalyticsService.build_game_detail(game.id)
    web = detail_ctx.get("top_game_lineups_off") or []
    assert web, "detail page produced no lineups"

    # Capture the PDF's arguments, keeping the offensive and defensive calls
    # apart so neither overwrites the other.
    seen = {"offensive": None, "defensive": None}

    def capture(*args, **kwargs):
        rank_by = kwargs.get("rank_by", "overall")
        if rank_by in seen:
            seen[rank_by] = kwargs
        return original_rank(*args, **kwargs)

    mocker.patch(
        "core.advanced_analytics.LineupAnalytics.get_game_lineup_rankings",
        side_effect=capture,
    )
    mocker.patch.object(
        report_service, "render_template", return_value="<html></html>"
    )
    mocker.patch.object(report_service.HTML, "write_pdf", return_value=b"pdf")
    report_service.generate_game_pdf_bytes(game.id)

    pdf_args = seen["offensive"]
    assert pdf_args, "PDF did not rank offensive lineups"

    # Assert the production arguments against independently-derived expectations
    # rather than against the PDF's own captured values.
    assert pdf_args["min_possessions"] == MIN_GAME_LINEUP_POSSESSIONS
    assert pdf_args["total_pts_scored_override"] == game.team_score
    assert pdf_args["total_pts_allowed_override"] == game.opponent_score
    assert pdf_args["total_possessions_override"] == pytest.approx(team_poss)

    pdf = original_rank(game_id=game.id, **pdf_args)

    assert [r["players"] for r in web] == [r["players"] for r in pdf]
    assert [r["ortg"] for r in web] == [r["ortg"] for r in pdf]
    assert [r["impact"]["offense_delta"] for r in web] == [
        r["impact"]["offense_delta"] for r in pdf
    ]


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

def test_segment_quarter_spans_cover_quarters_they_overlap():
    """A stint crossing a quarter break must be a candidate for both.

    Deriving the span from elapsed duration would misfire on overtime or any
    non-standard quarter length, so it is derived from the events that fall
    inside the segment.
    """
    from core.services.lineup_service import _segment_quarters

    class _Seg:
        def __init__(self, sid, start, end, quarter):
            self.id = sid
            self.start_timestamp = start
            self.end_timestamp = end
            self.quarter = quarter

    class _Ev:
        def __init__(self, ts, quarter):
            self.timestamp = ts
            self.quarter = quarter

    segments = [_Seg(1, 1_000, 5_000, 1), _Seg(2, 5_000, 9_000, 2)]
    # A quarter break at timestamp 6_000, inside the second segment's span.
    events = [_Ev(1_000, 1), _Ev(6_000, 2), _Ev(9_000, 2)]

    spans = _segment_quarters(segments, events)

    assert spans[1] == {1}
    assert spans[2] == {1, 2}, "segment crossing the break must span both"


def test_resolve_game_team_possessions_reports_zero_rather_than_flooring():
    """The resolver stays pure; callers apply their own policy."""
    class _Game:
        id = 999

    empty = resolve_game_team_possessions(
        _Game(), {"fga": 0, "fta": 0, "oreb": 0, "tov": 0}
    )
    assert empty == 0.0
