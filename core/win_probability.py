"""Live win probability backend slice (live-v2 console).

Pure logistic model mapping (score margin, time remaining, possession,
period) to the home-team (``Game.team_id``) win probability, plus a
timeline reconstructor used by ``GET /api/live-v2/win-probability``.

Model
-----
``P(win) = sigmoid(z)`` with ``z = (margin + possession_bonus) / sigma`` and
``sigma = LEAD_SCALE * sqrt(effective_minutes + 0.5) + BASE_SIGMA``.

Constants (documented, heuristic, calibrated for amateur pace):

- ``REGULATION_PERIOD_SECONDS = 600`` — 4 x 10-minute quarters (FIBA
  amateur format). Source: FIBA Official Basketball Rules, game duration.
- ``OT_PERIOD_SECONDS = 300`` — 5-minute overtime periods (FIBA Art. 8).
- ``LEAD_SCALE = 3.0`` — points of uncertainty per sqrt(minute). Amateur
  pace (~60-70 possessions/team, higher turnover rate than NCAA/NBA) means
  wider variance than pro models; 3.0 keeps a 10-pt lead at tip ~0.62 and
  a 15-pt lead with 60s left ~0.97. Sanity anchors below encode this.
- ``BASE_SIGMA = 0.5`` — avoids division by zero at the buzzer and keeps
  the curve smooth in the final seconds.
- ``POSSESSION_BONUS = 0.6`` — expected marginal value of possession in
  points at amateur efficiency (~0.8-0.9 PPP; discounted since the
  possession may end scoreless). Added to the margin when the tracked
  team has the ball, subtracted when the opponent does.
- ``OT_TIME_FACTOR = 0.6`` — overtime urgency damping: fewer possessions
  remain per clock second (fouls/timeouts compress effective play), so the
  same margin is more decisive; effective time is scaled down, steepening
  the curve for ``period > 4``.
- ``MIN_PROB / MAX_PROB = 0.01 / 0.99`` — clamp so no live state ever
  reports absolute certainty.

Methodological sources (heuristic adaptation, not a fitted replica):

- Stern, H. S. (1994), "A Brownian Motion Model for the Progress of
  Sports Scores" — margin diffuses with variance growing in time
  remaining; win prob is a normal/logit CDF of margin over
  time-scaled volatility. Our ``sigma ~ sqrt(time)`` follows this.
- Deshpande, S. K. & Jensen, S. T. (2016), "Estimating an NBA player's
  impact on his team's chances of winning" — logistic win-probability
  form in (margin, time); we reuse the sigmoid structure.
- Pomeroy, K. (log5 / Pythagorean expectation literature) — margin-based
  strength mapping; informs the modest early-game slope (large early
  leads stay far from 1.0).

``score_margin`` convention: ``Game.team_score - opponent_score`` (positive
means the tracked team leads), matching ``GameEvent.score_margin``.
"""

import json
import math

# FIBA amateur game structure.
REGULATION_PERIOD_SECONDS = 600
OT_PERIOD_SECONDS = 300
REGULATION_PERIODS = 4

# Logistic-model calibration (see module docstring for rationale).
LEAD_SCALE = 3.0
BASE_SIGMA = 0.5
POSSESSION_BONUS = 0.6
OT_TIME_FACTOR = 0.6

MIN_PROB = 0.01
MAX_PROB = 0.99

# Per-minute sampling keeps live curves small: one point per minute of
# game time once the log is dense, every event while it is sparse.
SPARSE_EVENT_THRESHOLD = 60


def _possession_bonus(possession) -> float:
    """Map the ``possession`` flag to an effective-margin bonus."""
    if possession is None:
        return 0.0
    if isinstance(possession, str):
        token = possession.strip().lower()
        if token in ("home", "team", "ours", "true", "1", "yes"):
            return POSSESSION_BONUS
        if token in ("away", "opponent", "opp", "false", "0", "no"):
            return -POSSESSION_BONUS
        return 0.0
    if possession is True:
        return POSSESSION_BONUS
    if possession is False:
        return -POSSESSION_BONUS
    return 0.0


def win_probability(score_margin, seconds_remaining, possession=None, period=1) -> float:
    """Return the tracked-team win probability in [0.01, 0.99].

    Args:
        score_margin: tracked-team lead in points (negative when trailing).
        seconds_remaining: clock time left in the game (clamped at >= 0).
        possession: None (unknown), truthy/"home" (our ball → bonus),
            falsy/"away" (opponent ball → penalty).
        period: 1-based period; values > 4 are overtime and scale the
            effective time down via ``OT_TIME_FACTOR``.
    """
    try:
        margin = float(score_margin)
    except (TypeError, ValueError):
        margin = 0.0
    try:
        remaining = float(seconds_remaining)
    except (TypeError, ValueError):
        remaining = REGULATION_PERIODS * REGULATION_PERIOD_SECONDS
    if remaining < 0:
        remaining = 0.0
    try:
        period_no = int(period)
    except (TypeError, ValueError):
        period_no = 1
    if period_no < 1:
        period_no = 1

    # Buzzer state: with no time left the scoreboard is the outcome.
    if remaining <= 0:
        if margin > 0:
            return MAX_PROB
        if margin < 0:
            return MIN_PROB
        return 0.5

    if period_no > REGULATION_PERIODS:
        remaining = remaining * OT_TIME_FACTOR

    effective_minutes = remaining / 60.0
    sigma = LEAD_SCALE * math.sqrt(effective_minutes + 0.5) + BASE_SIGMA
    z = (margin + _possession_bonus(possession)) / sigma
    # Guard against overflow for extreme amateur margins (|margin| <= ~150).
    if z > 20:
        prob = 1.0
    elif z < -20:
        prob = 0.0
    else:
        prob = 1.0 / (1.0 + math.exp(-z))
    return max(MIN_PROB, min(MAX_PROB, prob))


def _parse_clock_to_seconds(value) -> int | None:
    """Parse an ``M:SS``/``MM:SS`` time-remaining clock; None when unusable."""
    if value is None or value == "":
        return None
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        return None
    try:
        minutes = int(parts[0])
        seconds = int(parts[1])
    except (TypeError, ValueError):
        return None
    if minutes < 0 or seconds < 0 or seconds > 59:
        return None
    return minutes * 60 + seconds


def _seconds_remaining(period, time_remaining, game_seconds) -> float:
    """Best-effort seconds left in the game for a timeline event."""
    try:
        period_no = int(period) if period is not None else 1
    except (TypeError, ValueError):
        period_no = 1
    if period_no < 1:
        period_no = 1

    clock_secs = _parse_clock_to_seconds(time_remaining)
    if clock_secs is None and game_seconds is not None:
        try:
            elapsed = int(game_seconds)
        except (TypeError, ValueError):
            elapsed = None
        if elapsed is not None and elapsed >= 0:
            period_len = (
                REGULATION_PERIOD_SECONDS
                if period_no <= REGULATION_PERIODS
                else OT_PERIOD_SECONDS
            )
            clock_secs = max(0, period_len - elapsed)
    if clock_secs is None:
        # No clock info: assume mid-game of the recorded period.
        if period_no <= REGULATION_PERIODS:
            return float(
                (REGULATION_PERIODS - period_no) * REGULATION_PERIOD_SECONDS
                + REGULATION_PERIOD_SECONDS // 2
            )
        return float(OT_PERIOD_SECONDS // 2)
    if period_no <= REGULATION_PERIODS:
        return float(
            (REGULATION_PERIODS - period_no) * REGULATION_PERIOD_SECONDS + clock_secs
        )
    # Overtime: only the current extra period's clock is knowable locally.
    return float(max(0, clock_secs))


def _clock_label(period, time_remaining) -> str:
    try:
        period_no = int(period) if period is not None else 1
    except (TypeError, ValueError):
        period_no = 1
    clock = str(time_remaining).strip() if time_remaining not in (None, "") else "--:--"
    prefix = f"Q{period_no}" if period_no <= REGULATION_PERIODS else f"OT{period_no - REGULATION_PERIODS}"
    return f"{prefix} {clock}"


def _score_delta(event) -> int:
    """Margin delta introduced by one event (tracked-team perspective)."""
    event_type = getattr(event, "event_type", None)
    if event_type == "SHOT_2PT" and getattr(event, "shot_attempt", None) == "made":
        return 2
    if event_type == "SHOT_3PT" and getattr(event, "shot_attempt", None) == "made":
        return 3
    if event_type == "FT_MADE":
        return 1
    if event_type == "OPP_SCORE":
        try:
            detail = json.loads(getattr(event, "detail", None) or "{}")
        except (TypeError, ValueError):
            detail = {}
        points = detail.get("points", 0) if isinstance(detail, dict) else 0
        try:
            return -int(points or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def build_win_curve(game_id, team_id):
    """Reconstruct the win-probability timeline for a game.

    Margin truth per event: an explicit ``GameEvent.score_margin`` wins;
    otherwise margins accumulate from scoring deltas starting at 0:0
    (live-v2 rows never store ``score_margin``, so this fallback is what
    makes console-captured games produce a curve).

    Returns:
        List of ``{"clock_label": str, "margin": int, "prob": float}``
        sampled per minute once dense (every event while sparse). With no
        usable events the curve falls back to the final score only.
    """
    from core.models import Game, GameEvent

    game = Game.query.get(game_id)
    if game is None or game.team_id != team_id:
        raise LookupError("Game not found")

    events = GameEvent.query.filter_by(game_id=game.id).order_by(GameEvent.id.asc()).all()

    points = []
    running_margin = 0
    for event in events:
        stored = getattr(event, "score_margin", None)
        if stored is not None:
            try:
                running_margin = int(stored)
            except (TypeError, ValueError):
                running_margin += _score_delta(event)
        else:
            running_margin += _score_delta(event)
            # Skip non-scoring rows without stored margins: they carry no
            # new information and would only duplicate the previous point.
            if _score_delta(event) == 0:
                continue
        period = getattr(event, "quarter", None) or 1
        remaining = _seconds_remaining(
            period, getattr(event, "time_remaining", None), getattr(event, "game_seconds", None)
        )
        points.append(
            {
                "clock_label": _clock_label(period, getattr(event, "time_remaining", None)),
                "margin": running_margin,
                "prob": round(win_probability(running_margin, remaining, period=period), 4),
                "_remaining": remaining,
            }
        )

    final_margin = (game.team_score or 0) - (game.opponent_score or 0)
    final_period = REGULATION_PERIODS

    if not points:
        return [
            {
                "clock_label": "Final",
                "margin": final_margin,
                "prob": round(win_probability(final_margin, 0, period=final_period), 4),
            }
        ]

    # Sample per minute when dense; keep every event when sparse.
    sampled = points
    if len(points) > SPARSE_EVENT_THRESHOLD:
        by_minute = {}
        for point in points:
            minute = int(point["_remaining"] // 60)
            by_minute[minute] = point  # last event in the minute wins
        sampled = [by_minute[m] for m in sorted(by_minute, reverse=True)]

    curve = [
        {"clock_label": p["clock_label"], "margin": p["margin"], "prob": p["prob"]}
        for p in sampled
    ]
    last = curve[-1]
    if last["margin"] != final_margin:
        last["margin"] = final_margin
        last["prob"] = round(win_probability(final_margin, 0, period=final_period), 4)
    else:
        # Buzzer state: probability must reflect the actual outcome.
        last["prob"] = round(win_probability(final_margin, 0, period=final_period), 4)
    return curve
