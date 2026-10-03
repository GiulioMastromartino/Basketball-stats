"""
Lineup Segment Processing Service

Handles all lineup segment processing including:
- Generating lineup hashes
- Building lineup segments from game events
- Linking events to segments
- Calculating segment statistics
- Populating player lineup stats
"""

from core import rust_analytics
from core.models import (
    db,
    GameEvent,
    Lineup,
    LineupSegment,
    Organization,
    PlayerLineupStats,
    Team,
)


def resolve_team_id(team_id: int = None) -> int:
    """Return explicit team_id, falling back to the default team.

    Production callers always pass an explicit team. The fallback exists so
    scripts and tests that create games without team context keep working
    instead of violating the NOT NULL constraint on team_id. When no team
    exists at all, a default organization/team is provisioned (mirroring
    the production migration behavior).
    """
    if team_id is not None:
        return team_id
    team = Team.query.order_by(Team.id).first()
    if team is None:
        org = Organization.query.first()
        if org is None:
            org = Organization(name="Default Organization", slug="default-organization")
            db.session.add(org)
            db.session.flush()
        team = Team(name="Default Team", slug="default-team", organization_id=org.id)
        db.session.add(team)
        db.session.flush()
    return team.id

def generate_lineup_hash(players: list) -> str:
    """Use high-performance Rust implementation for lineup hashing."""
    return rust_analytics.calculate_lineup_hash(players)


def calculate_segment_duration(segment_events: list) -> int:
    """
    Calculate the duration in seconds for a lineup segment based on game_seconds.
    Optimized to use pre-filtered segment events.
    """
    if not segment_events:
        return 0

    game_secs = [e.game_seconds for e in segment_events if e.game_seconds is not None]

    if len(game_secs) >= 2:
        return max(game_secs) - min(game_secs)
    elif len(game_secs) == 1:
        return 60

    return 0


def get_or_create_lineup(players: list, is_starting: bool = False, team_id: int = None):
    """
    Get existing lineup or create new one.

    Args:
        players: List of 5 player names
        is_starting: Whether this is a starting lineup
        team_id: Team ID to associate the lineup with

    Returns:
        Lineup object (existing or newly created)
    """
    if len(players) != 5:
        return None

    team_id = resolve_team_id(team_id)
    lineup_hash = generate_lineup_hash(players)
    lineup = Lineup.query.filter_by(team_id=team_id, lineup_hash=lineup_hash).first()

    if not lineup:
        lineup = Lineup(
            lineup_hash=lineup_hash, players=sorted(players), is_starting=is_starting, team_id=team_id
        )
        db.session.add(lineup)
        db.session.flush()

    return lineup


def update_lineup_cached_stats(lineup_id: int):
    """Update cached stats for a lineup by aggregating all segments."""
    from datetime import datetime
    from core.models import Game

    lineup = Lineup.query.get(lineup_id)
    if not lineup:
        return

    # Only this team's segments contribute: legacy shared lineups may
    # still have segments from other teams pointing at this row until
    # repair_shared_lineups() splits them.
    segments = (
        LineupSegment.query.join(Game, LineupSegment.game_id == Game.id)
        .filter(
            LineupSegment.lineup_id == lineup_id,
            Game.team_id == lineup.team_id,
        )
        .all()
    )

    total_seconds = 0
    total_possessions = 0
    points_scored = 0
    points_allowed = 0
    games = set()

    total_fgm = 0
    total_fga = 0
    total_tpm = 0
    total_tpa = 0
    total_ftm = 0
    total_fta = 0
    total_oreb = 0
    total_dreb = 0
    total_ast = 0
    total_stl = 0
    total_blk = 0
    total_tov = 0
    total_reb_conceded = 0

    for segment in segments:
        total_seconds += segment.duration_seconds or 0
        total_possessions += segment.possessions or 0
        points_scored += segment.points_scored or 0
        points_allowed += segment.points_allowed or 0
        total_reb_conceded += segment.reb_conceded or 0
        games.add(segment.game_id)

        player_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id
        ).all()
        for ps in player_stats:
            total_fgm += ps.fgm or 0
            total_fga += ps.fga or 0
            total_tpm += ps.tpm or 0
            total_tpa += ps.tpa or 0
            total_ftm += ps.ftm or 0
            total_fta += ps.fta or 0
            total_oreb += ps.oreb or 0
            total_dreb += ps.dreb or 0
            total_ast += ps.ast or 0
            total_stl += ps.stl or 0
            total_blk += ps.blk or 0
            total_tov += ps.tov or 0

    lineup.total_seconds = total_seconds
    lineup.total_possessions = total_possessions
    lineup.points_scored = points_scored
    lineup.points_allowed = points_allowed
    lineup.games_played = len(games)
    lineup.segment_count = len(segments)

    lineup.fgm = total_fgm
    lineup.fga = total_fga
    lineup.tpm = total_tpm
    lineup.tpa = total_tpa
    lineup.ftm = total_ftm
    lineup.fta = total_fta
    lineup.oreb = total_oreb
    lineup.dreb = total_dreb
    lineup.ast = total_ast
    lineup.stl = total_stl
    lineup.blk = total_blk
    lineup.tov = total_tov
    lineup.reb_conceded = total_reb_conceded

    if total_possessions > 0:
        lineup.ortg = round((points_scored / total_possessions) * 100, 1)
        lineup.drtg = round((points_allowed / total_possessions) * 100, 1)
        lineup.net_rating = round(lineup.ortg - lineup.drtg, 1)
    else:
        lineup.ortg = 0
        lineup.drtg = 0
        lineup.net_rating = 0

    lineup.last_updated = datetime.utcnow()
    db.session.commit()


def _parse_opp_score_points(detail) -> int:
    """Points on an OPP_SCORE event. Shared by points_allowed accounting
    and margin inference so both paths always agree."""
    import json as _json
    import logging as _logging

    _log = _logging.getLogger(__name__)

    if isinstance(detail, str) and (
        detail.startswith("{") or detail.startswith("[")
    ):
        try:
            parsed = _json.loads(detail)
        except (ValueError, TypeError):
            _log.debug("Unparseable OPP_SCORE detail %r, defaulting to 2", detail)
            return 2
        if isinstance(parsed, dict):
            try:
                return int(parsed.get("points", 2))
            except (TypeError, ValueError):
                _log.debug("OPP_SCORE detail %r has no points, defaulting to 2", detail)
                return 2
        try:
            return int(parsed)
        except (TypeError, ValueError):
            _log.debug("OPP_SCORE detail %r not numeric, defaulting to 2", detail)
            return 2
    if detail is None or detail == "":
        return 2
    try:
        return int(detail)
    except (ValueError, TypeError):
        _log.debug("OPP_SCORE detail %r not numeric, defaulting to 2", detail)
        return 2


def parse_ft_event(detail, shot_attempt=None) -> tuple:
    """Interpret one FT/FT_MADE/FT_MISS event as (makes, attempts).

    Single source of truth for free-throw accounting across the lineup
    stat paths (batch processing, calculate_segment_stats,
    populate_player_lineup_stats). Accepts JSON and Python-literal dict
    strings. Explicit ftm/fta keys are authoritative; the made-shot
    fallback applies only when the keys are absent. The make count is
    always preserved: missing or degenerate attempts infer up to it.
    """
    import ast as _ast
    import json as _json

    if isinstance(detail, str):
        stripped = detail.strip()
        try:
            parsed = _json.loads(stripped)
        except (ValueError, TypeError):
            try:
                parsed = _ast.literal_eval(stripped)
            except (ValueError, TypeError, SyntaxError):
                parsed = {}
    elif isinstance(detail, dict):
        parsed = detail
    else:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    def _to_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    if "ftm" in parsed or "fta" in parsed:
        ftm_raw = parsed.get("ftm", None)
        fta_raw = parsed.get("fta", None)
        if ftm_raw is None:
            # No make count: infer from the shot result, like the report
            # timeline does (a made FT without ftm still scored).
            ftm = 1 if shot_attempt == "made" else 0
        else:
            ftm = _to_int(ftm_raw)
        if fta_raw is None or _to_int(fta_raw) <= 0:
            fta = max(ftm, 1)
        else:
            # Degenerate attempts below makes: trust the make count.
            fta = max(_to_int(fta_raw), ftm, 1)
        return max(0, min(ftm, fta)), fta
    if shot_attempt == "made":
        return 1, 1
    return 0, 1


def infer_starting_lineup_from_events(events, quarter_of=None) -> list:
    """Infer the 5 starters (players on court at tip-off) from Q1 events.

    A player counts as a starter when their first Q1 appearance is anything
    other than a SUB_IN: a SUB_OUT, shot, rebound, foul, turnover, etc. all
    prove court presence, while a bench player who enters (SUB_IN) and later
    leaves or shoots in Q1 is excluded. Opponent events (OPP_SCORE, OPP_OREB,
    ...) never count, even when they name an opponent player. Returns []
    unless 5 starters are identified so callers fall back to another source
    instead of reporting bench players or opponents.

    Args:
        events: GameEvent-like objects with timestamp/quarter/event_type/
            player_name (and .id when quarter_of needs it).
        quarter_of: Optional callable mapping an event to its quarter number.
            Defaults to a NEXT_QUARTER-aware walk over timestamp order (with
            explicit quarter values preserved), so events with a missing
            quarter are not all misattributed to Q1.
    """
    if quarter_of is None:
        ordered = sorted(events, key=lambda e: e.timestamp or 0)
        running = {}
        current = 1
        for event in ordered:
            if event.quarter is not None:
                current = event.quarter
            elif event.event_type == "NEXT_QUARTER":
                current += 1
            # Stable key: DB primary key when persisted, object identity
            # for transient (pre-flush) or duck-typed events without an id.
            # The map is built and consumed within this call, so both are
            # unambiguous here.
            _db_id = getattr(event, "id", None)
            _key = ("db", _db_id) if _db_id is not None else ("obj", id(event))
            running[_key] = (
                event.quarter if event.quarter is not None else current
            )

        def quarter_of(event, _running=running):
            _db_id = getattr(event, "id", None)
            _key = ("db", _db_id) if _db_id is not None else ("obj", id(event))
            return _running.get(_key, event.quarter or 1)

    q1 = sorted(
        (
            event
            for event in events
            if quarter_of(event) == 1 and getattr(event, "player_name", None)
        ),
        key=lambda event: event.timestamp or 0,
    )
    entered = set()
    seen = []
    for event in q1:
        event_type = event.event_type or ""
        if event_type.startswith("OPP_"):
            continue
        name = event.player_name
        if event_type == "SUB_IN":
            entered.add(name)
        elif name not in entered and name not in seen:
            seen.append(name)
            if len(seen) == 5:
                return seen
    return []


def build_lineup_segments(
    game_id: int, events: list, starting_lineup: list = None, team_id: int = None
) -> list:
    """Process events chronologically to create LineupSegment records.

    When no explicit starting lineup is given it is inferred from Q1
    events; existing segments are only replaced once a 5-player lineup is
    available, never deleted speculatively.
    """
    if team_id is None:
        from core.models import Game as _GameForTeam

        _g = _GameForTeam.query.get(game_id)
        team_id = _g.team_id if _g is not None else resolve_team_id(None)

    if not events:
        return []

    try:
        current_lineup = []

        if starting_lineup:
            current_lineup = list(starting_lineup)
        else:
            current_lineup = infer_starting_lineup_from_events(events)

        if len(current_lineup) < 5:
            return []

        # Only replace existing segments once a valid lineup is available.
        LineupSegment.query.filter_by(game_id=game_id).delete()
        db.session.flush()

        segment_ids = []
        current_segment = None
        segment_start_timestamp = None
        current_quarter = None

        # Optimization: Pre-filter SUB_IN events to speed up matching
        sub_in_events = [e for e in events if e.event_type == "SUB_IN"]

        for i, event in enumerate(events):
            if current_segment is None:
                segment_start_timestamp = event.timestamp
                current_quarter = event.quarter
                lineup = get_or_create_lineup(
                    current_lineup, is_starting=True, team_id=team_id
                )

                current_segment = LineupSegment(
                    game_id=game_id,
                    start_timestamp=segment_start_timestamp,
                    end_timestamp=None,
                    quarter=current_quarter,
                    players=list(current_lineup),
                    lineup_hash=generate_lineup_hash(current_lineup),
                    points_scored=0,
                    points_allowed=0,
                    possessions=0,
                    lineup_id=lineup.id if lineup else None,
                )
                db.session.add(current_segment)
                db.session.flush()
                segment_ids.append(current_segment.id)

            if event.event_type == "SUB_OUT" and event.player_name in current_lineup:
                current_lineup.remove(event.player_name)

                # Find matching SUB_IN that happens at the same time or immediately after
                sub_in_event = None
                for next_event in sub_in_events:
                    if (
                        next_event.timestamp >= event.timestamp
                        and next_event.player_name not in current_lineup
                    ):
                        sub_in_event = next_event
                        break

                if sub_in_event and len(current_lineup) == 4:
                    current_segment.end_timestamp = sub_in_event.timestamp
                    db.session.flush()

                    current_lineup.append(sub_in_event.player_name)

                    lineup = get_or_create_lineup(current_lineup, team_id=team_id)

                    current_segment = LineupSegment(
                        game_id=game_id,
                        start_timestamp=sub_in_event.timestamp,
                        end_timestamp=None,
                        quarter=sub_in_event.quarter,
                        players=list(current_lineup),
                        lineup_hash=generate_lineup_hash(current_lineup),
                        points_scored=0,
                        points_allowed=0,
                        possessions=0,
                        lineup_id=lineup.id if lineup else None,
                    )
                    db.session.add(current_segment)
                    db.session.flush()
                    segment_ids.append(current_segment.id)
                elif len(current_lineup) < 5:
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Unmatched SUB_OUT for {event.player_name} in game {game_id} at {event.timestamp}. "
                        f"Lineup size: {len(current_lineup)}"
                    )

            elif (
                event.event_type == "SUB_IN" and event.player_name not in current_lineup
            ):
                if len(current_lineup) < 5:
                    current_lineup.append(event.player_name)

        if current_segment and current_segment.end_timestamp is None:
            last_event = events[-1] if events else None
            if last_event:
                current_segment.end_timestamp = last_event.timestamp
                db.session.flush()

        db.session.commit()
        return segment_ids
    except Exception:
        db.session.rollback()
        raise


def link_events_to_segments(game_id: int) -> None:
    """
    Assign lineup_segment_id to each GameEvent based on timestamp and ID.
    O(N+M) complexity to avoid timeouts on production.
    """
    segments = (
        LineupSegment.query.filter_by(game_id=game_id)
        .order_by(LineupSegment.start_timestamp, LineupSegment.id)
        .all()
    )

    if not segments:
        return

    # Use ID as tie-breaker for deterministic ordering of simultaneous events
    events = (
        GameEvent.query.filter_by(game_id=game_id)
        .order_by(GameEvent.timestamp, GameEvent.id)
        .all()
    )

    segment_index = 0
    num_segments = len(segments)

    for event in events:
        # Move segment pointer if event is past current segment
        while segment_index < num_segments - 1:
            curr_seg = segments[segment_index]
            # If next segment starts at or before this event, and its ID is higher or timestamp is higher
            next_seg = segments[segment_index + 1]
            
            if event.timestamp > next_seg.start_timestamp:
                segment_index += 1
            elif event.timestamp == next_seg.start_timestamp:
                # If it's a substitution event at the boundary, SUB_IN usually starts the new segment
                if event.event_type == "SUB_IN":
                    segment_index += 1
                else:
                    break
            else:
                break

        segment = segments[segment_index]
        # Final check if event fits in this segment's time bounds
        is_after_start = event.timestamp >= segment.start_timestamp
        is_before_end = segment.end_timestamp is None or event.timestamp <= segment.end_timestamp
        
        if is_after_start and is_before_end:
            event.lineup_segment_id = segment.id

    db.session.commit()


def _normalize_name(value) -> str:
    return (value or "").strip().lower()


def _quarter_timeline(events: list) -> list:
    """Sorted (timestamp, quarter) pairs used to place segments on the clock."""
    return sorted(
        (e.timestamp or 0, e.quarter or 1)
        for e in events
        if e.quarter is not None
    )


def _quarter_at(timeline: list, timestamp: int, fallback: int = 1) -> int:
    """Quarter of the last timeline entry at or before `timestamp`."""
    if not timeline:
        return fallback
    chosen = timeline[0][1]
    for ts, quarter in timeline:
        if ts <= timestamp:
            chosen = quarter
        else:
            break
    return chosen or fallback


def _largest_remainder(total: int, weights: list) -> list:
    """Split `total` across `weights` by largest remainder, deterministically.

    Ties break on index so repeated runs produce identical splits.
    """
    n = len(weights)
    if n == 0 or total <= 0:
        return [0] * n
    weight_sum = sum(weights)
    if weight_sum <= 0:
        # No duration information: spread as evenly as possible.
        shares = [total // n] * n
        for i in range(total - (total // n) * n):
            shares[i] += 1
        return shares

    exact = [total * w / weight_sum for w in weights]
    shares = [int(x) for x in exact]
    remainder = total - sum(shares)
    order = sorted(range(n), key=lambda i: (-(exact[i] - shares[i]), i))
    for k in range(remainder):
        shares[order[k % n]] += 1
    return shares


def _box_score_possessions(game_id: int):
    """Authoritative box-score possessions for a game, or None when unavailable."""
    from core.models import PlayerStat
    from core.utils import calculate_possessions

    stats = PlayerStat.query.filter_by(game_id=game_id).all()
    if not stats:
        return None
    value = calculate_possessions(
        sum(s.fga or 0 for s in stats),
        sum(s.fta or 0 for s in stats),
        sum(s.oreb or 0 for s in stats),
        sum(s.tov or 0 for s in stats),
    )
    return float(value) if value and value > 0 else None


def _segment_quarters(segment, fallback_quarter: int = 1) -> set:
    """Every quarter a segment overlaps.

    LineupSegment persists both `quarter` and `end_timestamp`, so a stint that
    begins late in one quarter and ends early in the next belongs to both. A
    single-quarter lookup would strand the second quarter's shots.
    """
    start_q = segment.quarter or fallback_quarter
    if not segment.end_timestamp or not segment.start_timestamp:
        return {start_q}
    if segment.end_timestamp <= segment.start_timestamp:
        return {start_q}
    # Each quarter is roughly 12 minutes; derive the span from the clock rather
    # than assuming a fixed number of quarters per game.
    span_ms = segment.end_timestamp - segment.start_timestamp
    span_quarters = 1 + int(span_ms // (12 * 60 * 1000))
    return {start_q + offset for offset in range(max(span_quarters, 1))}


def reconcile_orphan_shot_points(
    game_id: int,
    segments: list = None,
    total_possessions: float = None,
) -> dict:
    """Credit field goals that exist only in `shot_events` to lineup segments.

    The event log is a partial mirror of the shot record: for many imports only
    a subset of shots also appear as SHOT_2PT/SHOT_3PT rows, while `shot_events`
    holds the complete record (its FGA/FGM match the box score exactly). Segments
    derived purely from GameEvent therefore undercounted scoring, which is what
    produced absurd baselines such as a 159 ORtg "team average" in a 78-point
    game.

    The reconciliation is target-based rather than shot-by-shot, so it cannot
    double count. For each (player, quarter):

    * authoritative points = made shots in `shot_events` for that player/quarter
    * already credited     = field-goal points the log's own *segment-linked*
      SHOT_* events contributed
    * shortfall            = authoritative - credited (never negative)

    Only segment-linked events count as credited: an event with no segment never
    reached a segment total, so treating it as credited would shrink the
    shortfall and reintroduce undercounting.

    ShotEvent rows carry no timestamp, so a shortfall cannot be placed on the
    clock, but it can be placed on the floor: the shooter was on court during
    their stints in that quarter. The shortfall is spread across those stints
    weighted by stint duration, so segment totals reconcile with the complete
    record while the split between a player's own stints remains a documented
    estimate.

    Possessions are reconciled on the same basis as points. Reconciling points
    while leaving possessions at their partial event-derived values would mix a
    corrected numerator with an uncorrected denominator and inflate every
    lineup rate - the same class of defect as the 200.0 ORtg this replaces. The
    possession shortfall is spread across segments weighted by their tracked
    possessions, which preserves the distribution the log provides while making
    the total authoritative.

    Deliberately untouched:

    * Free throws, which are already fully represented as FT events.
    * `reb_conceded`, which is an event-derived count with no authoritative
      counterpart.

    Args:
        game_id: Game to reconcile.
        segments: Optional pre-fetched segments.
        total_possessions: Authoritative box-score possessions. When omitted the
            possession reconciliation is skipped.

    Returns a summary dict for logging and tests.
    """
    from core.models import ShotEvent

    if segments is None:
        segments = (
            LineupSegment.query.filter_by(game_id=game_id)
            .order_by(LineupSegment.start_timestamp, LineupSegment.id)
            .all()
        )
    segments = list(segments)
    empty = {
        "points_authoritative": 0,
        "points_already_credited": 0,
        "points_added": 0,
        "points_budget": 0,
        "possessions_added": 0,
        "players_reconciled": 0,
        "unattributable_players": 0,
    }
    if not segments:
        return empty

    events = (
        GameEvent.query.filter_by(game_id=game_id)
        .order_by(GameEvent.timestamp)
        .all()
    )

    # Segment quarter span plus the stints each player occupied in it.
    quarters_by_segment = {}
    stints_by_player = {}
    for seg in segments:
        span = _segment_quarters(seg)
        quarters_by_segment[seg.id] = span
        players = seg.players or []
        if isinstance(players, str):
            try:
                import json as _json

                players = _json.loads(players)
            except Exception:
                players = []
        for player in players:
            key = _normalize_name(player)
            for quarter in span:
                stints_by_player.setdefault(key, {}).setdefault(quarter, []).append(seg)

    # Field-goal points already credited to segments by the log.
    credited = {}
    for event in events:
        if event.event_type not in ("SHOT_2PT", "SHOT_3PT"):
            continue
        if event.lineup_segment_id is None:
            continue
        if _normalize_name(event.shot_attempt) != "made":
            continue
        points = 3 if event.event_type == "SHOT_3PT" else 2
        key = (_normalize_name(event.player_name), event.quarter or 1)
        credited[key] = credited.get(key, 0) + points

    # Authoritative made-shot points per (player, quarter). `result` is checked
    # because `points` is copied verbatim from external exports and a missed
    # shot carrying a stale value must never be credited as a score.
    authoritative = {}
    shots = ShotEvent.query.filter_by(game_id=game_id).order_by(ShotEvent.id).all()
    for shot in shots:
        if _normalize_name(shot.result) != "made":
            continue
        points = shot.points or 0
        if points <= 0:
            continue
        key = (_normalize_name(shot.player_name), shot.quarter or 1)
        authoritative[key] = authoritative.get(key, 0) + points

    # Budget guard: the shortfall is measured against the field-goal points the
    # log already contributed, so running this twice would otherwise credit the
    # same gap again. Compare the complete record against the field-goal points
    # currently in the segments (total minus the free throws, which are counted
    # separately and never reconciled here).
    ft_points = 0
    for event in events:
        if event.lineup_segment_id is None:
            continue
        if event.event_type == "FT":
            ftm, _fta = parse_ft_event(event.detail, event.shot_attempt)
            ft_points += ftm
        elif event.event_type == "FT_MADE":
            ft_points += 1
    current_fg_points = sum(s.points_scored or 0 for s in segments) - ft_points
    budget = max(0, sum(authoritative.values()) - current_fg_points)

    points_added = 0
    players_reconciled = 0
    unattributable = 0
    per_stint_points = {}

    # Largest shortfalls first so a tight budget is spent where it matters most
    # rather than alphabetically.
    pending = []
    for key, target in authoritative.items():
        already = credited.get(key, 0)
        if target - already > 0:
            pending.append((key, target - already))
    pending.sort(key=lambda pair: (-pair[1], pair[0]))

    remaining_budget = budget
    for (player, quarter), shortfall in pending:
        # A nominal shortfall here does not mean points were lost: when the
        # budget is already met the points are sitting in the segments from an
        # earlier pass, they are simply no longer attributable to this player's
        # stints. Only the no-stint case below is a genuine data gap.
        if remaining_budget <= 0:
            continue

        stints = stints_by_player.get(player, {}).get(quarter)
        if not stints:
            unattributable += 1
            continue

        stints = sorted(stints, key=lambda s: (s.start_timestamp or 0, s.id))
        shortfall = min(shortfall, remaining_budget)
        durations = [max(s.duration_seconds or 0, 0) for s in stints]
        shares = _largest_remainder(shortfall, durations)
        for seg, share in zip(stints, shares):
            if share <= 0:
                continue
            seg.points_scored = (seg.points_scored or 0) + share
            per_stint_points[(seg.id, player)] = (
                per_stint_points.get((seg.id, player), 0) + share
            )
            points_added += share
        remaining_budget -= shortfall
        players_reconciled += 1

    possessions_added = 0
    if total_possessions is None:
        total_possessions = _box_score_possessions(game_id)
    if total_possessions and total_possessions > 0:
        tracked = sum(s.possessions or 0 for s in segments)
        shortfall_poss = int(round(total_possessions - tracked))
        if shortfall_poss > 0 and tracked > 0:
            ordered = sorted(
                segments, key=lambda s: (-(s.possessions or 0), s.id)
            )
            shares = _largest_remainder(
                shortfall_poss, [max(s.possessions or 0, 0) for s in ordered]
            )
            for seg, share in zip(ordered, shares):
                if share > 0:
                    seg.possessions = (seg.possessions or 0) + share
                    possessions_added += share

    if per_stint_points:
        _bump_player_lineup_points(per_stint_points)

    db.session.commit()

    return {
        "points_authoritative": sum(authoritative.values()),
        "points_already_credited": sum(credited.values()),
        "points_added": points_added,
        "points_budget": budget,
        "possessions_added": possessions_added,
        "players_reconciled": players_reconciled,
        "unattributable_players": unattributable,
    }


def _bump_player_lineup_points(per_stint_points: dict) -> None:
    """Keep per-player lineup stats consistent with reconciled segment totals.

    Sorts the affected segment ids and loads each segment's rows once instead of
    querying per (segment, player) pair.
    """
    segment_ids = sorted({segment_id for segment_id, _player in per_stint_points})
    rows_by_segment = {}
    for segment_id in segment_ids:
        rows_by_segment[segment_id] = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment_id
        ).all()

    for (segment_id, player), gained in per_stint_points.items():
        for row in rows_by_segment.get(segment_id, []):
            if _normalize_name(row.player_name) == player:
                row.points = (row.points or 0) + gained
                # Keep the shooting columns coherent with the added score.
                row.fgm = (row.fgm or 0) + gained
                row.fga = (row.fga or 0) + gained
                break

def calculate_segment_stats(segment_id: int, all_events: list = None) -> dict:
    """
    Calculate points_scored, points_allowed, possessions for a segment.

    Looks at all events during this segment and calculates aggregate stats.

    Args:
        segment_id: ID of the LineupSegment to calculate stats for
        all_events: Optional list of all GameEvent objects for duration calculation

    Returns:
        Dictionary with points_scored, points_allowed, possessions
    """
    segment = LineupSegment.query.get(segment_id)
    if not segment:
        return {"points_scored": 0, "points_allowed": 0, "possessions": 0}

    events = GameEvent.query.filter_by(lineup_segment_id=segment_id).all()

    points_scored = 0
    points_allowed = 0
    possessions = 0
    reb_conceded = 0
    possession_ending_events = set()

    for event in events:
        if event.event_type == "OPP_OREB":
            reb_conceded += 1
            
        if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
            points_scored += 2
        elif event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
            points_scored += 3
        elif event.event_type == "FT":
            ftm, _fta = parse_ft_event(event.detail, event.shot_attempt)
            points_scored += ftm
        elif event.event_type == "FT_MADE":
            points_scored += 1
        elif event.event_type == "OPP_SCORE":
            points_allowed += _parse_opp_score_points(event.detail)

        if event.event_type in [
            "SHOT_2PT",
            "SHOT_3PT",
            "TURNOVER",
            "FT",
            "FT_MADE",
            "FT_MISS",
        ]:
            if (
                event.possession_number
                and event.possession_number not in possession_ending_events
            ):
                possession_ending_events.add(event.possession_number)
                possessions += 1

    segment.points_scored = points_scored
    segment.points_allowed = points_allowed
    segment.possessions = possessions
    segment.reb_conceded = reb_conceded

    if all_events:
        segment.duration_seconds = calculate_segment_duration(events)

    db.session.commit()

    return {
        "points_scored": points_scored,
        "points_allowed": points_allowed,
        "possessions": possessions,
        "reb_conceded": reb_conceded,
    }


def populate_player_lineup_stats(segment_id: int) -> None:
    """
    Create PlayerLineupStats records for each player in the segment.

    Accumulates individual stats for each player during this segment.

    Args:
        segment_id: ID of the LineupSegment to process
    """
    segment = LineupSegment.query.get(segment_id)
    if not segment or not segment.players:
        return

    PlayerLineupStats.query.filter_by(lineup_segment_id=segment_id).delete()
    db.session.commit()

    player_stats = {}
    for player_name in segment.players:
        player_stats[player_name] = {
            "points": 0,
            "fga": 0,
            "fgm": 0,
            "tpa": 0,
            "tpm": 0,
            "fta": 0,
            "ftm": 0,
            "oreb": 0,
            "dreb": 0,
            "ast": 0,
            "stl": 0,
            "blk": 0,
            "tov": 0,
            "reb_conceded": 0,
        }

    events = GameEvent.query.filter_by(lineup_segment_id=segment_id).all()

    for event in events:
        # OPP_OREB affects ALL players on court - handle specially
        if event.event_type == "OPP_OREB":
            for p_name in player_stats:
                player_stats[p_name]["reb_conceded"] += 1
            continue

        player_name = event.player_name
        if not player_name or player_name not in player_stats:
            continue

        stats = player_stats[player_name]

        if event.event_type == "SHOT_2PT":
            stats["fga"] += 1
            if event.shot_attempt == "made":
                stats["fgm"] += 1
                stats["points"] += 2

        elif event.event_type == "SHOT_3PT":
            stats["fga"] += 1
            stats["tpa"] += 1
            if event.shot_attempt == "made":
                stats["fgm"] += 1
                stats["tpm"] += 1
                stats["points"] += 3

        elif event.event_type == "FT":
            ftm, fta = parse_ft_event(event.detail, event.shot_attempt)
            stats["points"] += ftm
            stats["ftm"] += ftm
            stats["fta"] += fta

        elif event.event_type == "FT_MADE":
            stats["fta"] += 1
            stats["ftm"] += 1
            stats["points"] += 1

        elif event.event_type == "FT_MISS":
            stats["fta"] += 1

        elif event.event_type == "TURNOVER":
            stats["tov"] += 1

        elif event.event_type == "AST":
            stats["ast"] += 1

        elif event.event_type == "STL":
            stats["stl"] += 1

        elif event.event_type == "BLK":
            stats["blk"] += 1

        elif event.event_type in ("OREB", "REBOUND_OFFENSIVE"):
            stats["oreb"] += 1

        elif event.event_type in ("DREB", "REBOUND_DEFENSIVE"):
            stats["dreb"] += 1

    for player_name, stats in player_stats.items():
        player_lineup_stat = PlayerLineupStats(
            lineup_segment_id=segment_id,
            player_name=player_name,
            points=stats["points"],
            fga=stats["fga"],
            fgm=stats["fgm"],
            tpa=stats["tpa"],
            tpm=stats["tpm"],
            fta=stats["fta"],
            ftm=stats["ftm"],
            oreb=stats["oreb"],
            dreb=stats["dreb"],
            ast=stats["ast"],
            stl=stats["stl"],
            blk=stats["blk"],
            tov=stats["tov"],
            reb_conceded=stats["reb_conceded"],
        )
        db.session.add(player_lineup_stat)

    db.session.commit()


def process_game_lineups(
    game_id: int, events: list, starting_lineup: list = None, team_id: int = None
) -> None:
    """
    Optimized entry point for lineup processing.
    Uses batch operations to avoid timeouts.
    """
    # 1. Build segments
    segment_ids = build_lineup_segments(game_id, events, starting_lineup, team_id)
    if not segment_ids:
        return

    # 2. Link events efficiently
    link_events_to_segments(game_id)

    # 3. Bulk fetch segments and events
    segments = LineupSegment.query.filter(LineupSegment.id.in_(segment_ids)).all()
    all_segment_events = GameEvent.query.filter(GameEvent.lineup_segment_id.in_(segment_ids)).all()
    
    # Group events by segment for fast access
    events_by_segment = {}
    for event in all_segment_events:
        sid = event.lineup_segment_id
        if sid not in events_by_segment:
            events_by_segment[sid] = []
        events_by_segment[sid].append(event)

    # 4. Clear existing player stats for these segments in one go
    PlayerLineupStats.query.filter(PlayerLineupStats.lineup_segment_id.in_(segment_ids)).delete(synchronize_session=False)
    db.session.commit()

    # 4b. Split-format games log no timestamped team-shot events (their FGs
    # live only in shot_events): attribute team points from score_margin
    # movement between consecutive OPP_SCORE events - the same inference the
    # report timeline uses. Net (not gross) movement is attributed, so
    # margin noise cannot inflate totals by counting only upward wiggles.
    # Live v2 games count SHOT_2PT/SHOT_3PT/FT_MADE directly.
    _direct_shot_types = {"SHOT_2PT", "SHOT_3PT", "FT_MADE"}
    use_margin_inference = not any(
        e.event_type in _direct_shot_types for e in all_segment_events
    )
    seg_inferred_points = {}
    if use_margin_inference:
        _ordered = sorted(all_segment_events, key=lambda e: e.game_seconds or 0)
        _implied_team = {}
        _opp = 0
        _team = 0
        for _e in _ordered:
            if _e.event_type != "OPP_SCORE":
                continue
            _pts = _parse_opp_score_points(_e.detail)
            _opp += _pts
            if _e.score_margin is not None:
                # Team totals never decrease: clamp logging noise so
                # segment attributions telescope exactly to the final total.
                _team = max(_team, _opp + _e.score_margin)
            _implied_team[_e.id] = _team
        _prev_team = 0
        for _seg in sorted(
            segments, key=lambda s: (s.start_timestamp or 0, s.id)
        ):
            _seg_opp = [
                e for e in events_by_segment.get(_seg.id, [])
                if e.id in _implied_team
            ]
            if not _seg_opp:
                seg_inferred_points[_seg.id] = 0
                continue
            _t_end = _implied_team[
                max(_seg_opp, key=lambda e: e.game_seconds or 0).id
            ]
            seg_inferred_points[_seg.id] = max(0, _t_end - _prev_team)
            _prev_team = _t_end

    # 5. Process each segment
    lineup_ids = set()
    new_player_stats = []

    for segment in segments:
        seg_events = events_by_segment.get(segment.id, [])
        
        # Calculate segment aggregates
        pts_scored = 0
        pts_allowed = 0
        poss = 0
        poss_ending = set()
        reb_conceded = 0
        if use_margin_inference:
            pts_scored += seg_inferred_points.get(segment.id, 0)
        
        player_map = {p: {
            "points": 0, "fga": 0, "fgm": 0, "tpa": 0, "tpm": 0, "fta": 0, "ftm": 0,
            "oreb": 0, "dreb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0, "reb_conceded": 0
        } for p in (segment.players or [])}

        for event in seg_events:
            et = event.event_type
            if et == "SHOT_2PT":
                if event.shot_attempt == "made":
                    pts_scored += 2
                    if event.player_name in player_map:
                        player_map[event.player_name]["points"] += 2
                        player_map[event.player_name]["fgm"] += 1
                if event.player_name in player_map:
                    player_map[event.player_name]["fga"] += 1
            elif et == "SHOT_3PT":
                if event.shot_attempt == "made":
                    pts_scored += 3
                    if event.player_name in player_map:
                        player_map[event.player_name]["points"] += 3
                        player_map[event.player_name]["fgm"] += 1
                        player_map[event.player_name]["tpm"] += 1
                if event.player_name in player_map:
                    player_map[event.player_name]["fga"] += 1
                    player_map[event.player_name]["tpa"] += 1
            elif et == "FT_MADE":
                pts_scored += 1
                if event.player_name in player_map:
                    player_map[event.player_name]["points"] += 1
                    player_map[event.player_name]["fta"] += 1
                    player_map[event.player_name]["ftm"] += 1
            elif et == "FT":
                # Live format stores makes in detail {"ftm": n, "fta": m}.
                # In margin-inference mode the segment total already includes
                # these points via OPP_SCORE jumps; the shooter attribution
                # below stays exact either way.
                ftm, fta = parse_ft_event(event.detail, event.shot_attempt)
                if not use_margin_inference:
                    pts_scored += ftm
                if event.player_name in player_map:
                    player_map[event.player_name]["points"] += ftm
                    player_map[event.player_name]["fta"] += fta
                    player_map[event.player_name]["ftm"] += ftm
            elif et == "OPP_SCORE":
                pts_allowed += _parse_opp_score_points(event.detail)
            elif et == "OPP_OREB":
                reb_conceded += 1
                for p in player_map: player_map[p]["reb_conceded"] += 1
            
            # Atomic stats
            if event.player_name in player_map:
                p_stats = player_map[event.player_name]
                if et == "FT_MISS": p_stats["fta"] += 1
                elif et == "TURNOVER": p_stats["tov"] += 1
                elif et == "AST": p_stats["ast"] += 1
                elif et == "STL": p_stats["stl"] += 1
                elif et == "BLK": p_stats["blk"] += 1
                elif et in ("OREB", "REBOUND_OFFENSIVE"): p_stats["oreb"] += 1
                elif et in ("DREB", "REBOUND_DEFENSIVE"): p_stats["dreb"] += 1

            # Possession tracking
            if et in ["SHOT_2PT", "SHOT_3PT", "TURNOVER", "FT", "FT_MADE", "FT_MISS"]:
                if event.possession_number and event.possession_number not in poss_ending:
                    poss_ending.add(event.possession_number)
                    poss += 1

        if use_margin_inference:
            # Team-possession endings are invisible in split-format logs
            # (missed FGs leave no trace), so count from the possession ids
            # touching the segment: each id is one total possession and the
            # team's share is half. Reconciles with the possessions formula
            # at game level (134 ids -> ~67 vs formula 69 for this game).
            _distinct = {
                e.possession_number for e in seg_events if e.possession_number
            }
            poss = max(1, round(len(_distinct) / 2)) if _distinct else poss

        # Update segment model
        segment.points_scored = pts_scored
        segment.points_allowed = pts_allowed
        segment.possessions = poss
        segment.reb_conceded = reb_conceded
        segment.duration_seconds = calculate_segment_duration(seg_events)
        if segment.lineup_id:
            lineup_ids.add(segment.lineup_id)

        # Batch preparation for player stats
        for p_name, s in player_map.items():
            new_player_stats.append(PlayerLineupStats(
                lineup_segment_id=segment.id, player_name=p_name, **s
            ))

    # 6. Bulk save everything
    db.session.bulk_save_objects(new_player_stats)
    db.session.commit()

    # 6b. Partially-logged shot events: `shot_events` is the complete record
    # while the event log mirrors only part of it, so segments built purely from
    # GameEvent undercount scoring. Credit the difference from the complete
    # record. Skipped when margin inference already telescoped team points to
    # the final score, since that path is already whole-game.
    if not use_margin_inference:
        summary = reconcile_orphan_shot_points(game_id, segments=segments)
        if summary.get("points_added") or summary.get("possessions_added"):
            try:
                from flask import current_app

                current_app.logger.info(
                    "Lineup shot reconciliation for game %s: %s authoritative pts, "
                    "%s already credited, +%s pts across %s players "
                    "(%s unattributable), +%s possessions",
                    game_id,
                    summary["points_authoritative"],
                    summary["points_already_credited"],
                    summary["points_added"],
                    summary["players_reconciled"],
                    summary["unattributable_players"],
                    summary["possessions_added"],
                )
            except Exception:
                pass

    # 7. Update affected lineups
    for lid in lineup_ids:
        update_lineup_cached_stats(lid)


# =============================================================================
# Lineup Optimizer: context-aware "best 5 for this context" ranking
# =============================================================================

#: Minimum possessions for a lineup to be considered (excludes noise).
OPTIMIZER_MIN_POSSESSIONS = 10

#: Maximum lineups returned.
OPTIMIZER_TOP_N = 5

#: Valid contexts (query param values; default "balanced").
OPTIMIZER_CONTEXTS = (
    "balanced",
    "vs_zone",
    "vs_fast",
    "protect_lead",
    "need_stops",
    "need_score",
)

#: Documented, simple per-context scoring scheme.
#:
#: Base signal is cached net_rating. Each context adds small, explainable
#: adjustments derived from already-aggregated Lineup columns:
#:
#: - balanced:      score = net
#: - vs_zone:       score = net + 0.4*(efg_pct - 50) + 0.3*ast_rate
#:                  (shooting + ball movement beats a zone)
#: - vs_fast:       score = net + 0.3*(ortg - 110) + 1.0*stocks_rate
#:                  (efficient offense + STL/BLK fuel transition)
#: - protect_lead:  score = net + 0.3*(110 - drtg) - 0.5*tov_rate
#:                  (get stops without giving it away)
#: - need_stops:    score = 0.5*net + 0.5*(110 - drtg) + 1.0*stocks_rate
#:                  (defense first: low DRtg + stocks)
#: - need_score:    score = 0.5*net + 0.5*(ortg - 110) + 0.4*(efg_pct - 50)
#:                  (offense first: high ORtg + efficient shooting)
#:
#: where efg_pct = (fgm + 0.5*tpm) / fga * 100 (0 when fga == 0),
#: tov_rate / ast_rate / stocks_rate are per-100-possession rates
#: (0 when possessions == 0). League-average anchors (50% eFG, 110 ORtg/DRtg)
#: keep adjustments on the same scale as net rating points.
OPTIMIZER_WEIGHTS_DOC = (
    "balanced=net; vs_zone=net+0.4*(efg-50)+0.3*ast_rate; "
    "vs_fast=net+0.3*(ortg-110)+stocks_rate; "
    "protect_lead=net+0.3*(110-drtg)-0.5*tov_rate; "
    "need_stops=0.5*net+0.5*(110-drtg)+stocks_rate; "
    "need_score=0.5*net+0.5*(ortg-110)+0.4*(efg-50)"
)


def _optimizer_players(lineup) -> list:
    raw = lineup.players or []
    if isinstance(raw, str):
        try:
            import json

            parsed = json.loads(raw)
            return list(parsed) if isinstance(parsed, list) else []
        except Exception:
            return []
    return list(raw)


def _optimizer_efg_pct(lineup) -> float:
    fga = lineup.fga or 0
    if not fga:
        return 0.0
    return round(((lineup.fgm or 0) + 0.5 * (lineup.tpm or 0)) / fga * 100, 1)


def _optimizer_rate(count, possessions) -> float:
    if not possessions:
        return 0.0
    return (count or 0) / possessions * 100


def _optimizer_score(lineup, context: str, efg_pct: float) -> float:
    net = lineup.net_rating or 0
    ortg = lineup.ortg or 0
    drtg = lineup.drtg or 0
    poss = lineup.total_possessions or 0
    tov_rate = _optimizer_rate(lineup.tov, poss)
    ast_rate = _optimizer_rate(lineup.ast, poss)
    stocks_rate = _optimizer_rate((lineup.stl or 0) + (lineup.blk or 0), poss)
    if context == "vs_zone":
        return net + 0.4 * (efg_pct - 50) + 0.3 * ast_rate
    if context == "vs_fast":
        return net + 0.3 * (ortg - 110) + stocks_rate
    if context == "protect_lead":
        return net + 0.3 * (110 - drtg) - 0.5 * tov_rate
    if context == "need_stops":
        return 0.5 * net + 0.5 * (110 - drtg) + stocks_rate
    if context == "need_score":
        return 0.5 * net + 0.5 * (ortg - 110) + 0.4 * (efg_pct - 50)
    return float(net)


def rank_lineups_for_context(team_id: int, context: str = "balanced") -> dict:
    """Rank candidate 5-man units for a game context.

    Args:
        team_id: Team scope (only Lineup rows for this team are considered).
        context: One of balanced, vs_zone, vs_fast, protect_lead,
            need_stops, need_score. Unknown values fall back to balanced.

    Returns:
        Dict with keys ``context``, ``lineups`` (top 5, each with
        lineup_id, players, net_rating, ortg, drtg, possessions, minutes,
        score, explanation) and ``reason`` (None on success, human-readable
        string when data is empty/insufficient). Never raises: unexpected
        errors yield ``{"lineups": [], "reason": ...}``.
    """
    from core.models import Lineup

    if context not in OPTIMIZER_CONTEXTS:
        context = "balanced"
    try:
        candidates = (
            Lineup.query.filter_by(team_id=team_id)
            .filter(Lineup.total_possessions >= OPTIMIZER_MIN_POSSESSIONS)
            .all()
        )
    except Exception as exc:  # never error on DB issues
        return {"context": context, "lineups": [], "reason": f"Unable to load lineups: {exc}"}
    if not candidates:
        return {
            "context": context,
            "lineups": [],
            "reason": (
                "Insufficient lineup data for this team "
                f"(need >= {OPTIMIZER_MIN_POSSESSIONS} possessions per unit)"
            ),
        }

    scored = []
    for lineup in candidates:
        efg = _optimizer_efg_pct(lineup)
        score = _optimizer_score(lineup, context, efg)
        scored.append((lineup, efg, score))
    # Score desc, then net desc, then possessions desc (deterministic).
    scored.sort(
        key=lambda t: (t[2], t[0].net_rating or 0, t[0].total_possessions or 0),
        reverse=True,
    )

    context_labels = {
        "balanced": "balanced",
        "vs_zone": "vs zone",
        "vs_fast": "vs fast",
        "protect_lead": "to protect a lead",
        "need_stops": "to get stops",
        "need_score": "to score",
    }
    label = context_labels.get(context, context)
    ranked = []
    for lineup, efg, score in scored[:OPTIMIZER_TOP_N]:
        net = lineup.net_rating or 0
        poss = lineup.total_possessions or 0
        minutes = round((lineup.total_seconds or 0) / 60, 1)
        ranked.append(
            {
                "lineup_id": lineup.id,
                "players": _optimizer_players(lineup),
                "net_rating": net,
                "ortg": lineup.ortg or 0,
                "drtg": lineup.drtg or 0,
                "possessions": poss,
                "minutes": minutes,
                "efg_pct": efg,
                "score": round(score, 1),
                "explanation": (
                    f"{net:+.1f} net in {poss} poss {label} "
                    f"(ORtg {lineup.ortg or 0:.1f} / DRtg {lineup.drtg or 0:.1f}, "
                    f"eFG {efg:.1f}%)"
                ),
            }
        )
    return {"context": context, "lineups": ranked, "reason": None}


def repair_shared_lineups() -> dict:
    """Split lineups shared across teams into per-team rows.

    Legacy bug: ``Lineup.lineup_hash`` was globally unique, so two teams
    with the same 5 player names shared one ``Lineup`` row and its cached
    stats mixed both teams' segments (cross-team leak). This repair:

    1. Finds every lineup whose segments span >1 team (via Game.team_id).
    2. For each foreign team, creates a per-team duplicate row with the
       same hash/players and re-links that team's segments to it.
    3. Recomputes cached stats for every touched lineup (team-pure).

    Returns ``{"split": N, "relinked": M}``. Idempotent and safe to run
    on every boot.
    """
    from core.models import Game

    split = 0
    relinked = 0
    for lineup in Lineup.query.all():
        segments = LineupSegment.query.filter_by(lineup_id=lineup.id).all()
        if not segments:
            continue
        game_ids = {s.game_id for s in segments}
        games = Game.query.filter(Game.id.in_(list(game_ids))).all()
        team_of_game = {g.id: g.team_id for g in games}
        by_team: dict[int, list] = {}
        for s in segments:
            tid = team_of_game.get(s.game_id)
            if tid is None:
                continue
            by_team.setdefault(tid, []).append(s)
        if len(by_team) <= 1:
            continue
        # Keep the original row for its own team when possible;
        # otherwise keep it for the first team with segments.
        keep_team = lineup.team_id if lineup.team_id in by_team else next(iter(by_team))
        for tid, segs in by_team.items():
            if tid == keep_team:
                continue
            dup = Lineup.query.filter_by(team_id=tid, lineup_hash=lineup.lineup_hash).first()
            if dup is None:
                dup = Lineup(
                    team_id=tid,
                    lineup_hash=lineup.lineup_hash,
                    players=list(lineup.players or []),
                    display_name=lineup.display_name,
                    is_starting=bool(lineup.is_starting),
                )
                db.session.add(dup)
                db.session.flush()
                split += 1
            for s in segs:
                s.lineup_id = dup.id
                relinked += 1
        db.session.commit()
        update_lineup_cached_stats(lineup.id)
        for tid in by_team:
            if tid == keep_team:
                continue
            dup = Lineup.query.filter_by(team_id=tid, lineup_hash=lineup.lineup_hash).first()
            if dup is not None:
                update_lineup_cached_stats(dup.id)
    # Final pass: recompute any lineup whose cached stats still mix teams
    # (covers rows whose segments were already per-team but stats stale).
    return {"split": split, "relinked": relinked}


def ensure_lineup_team_unique_index() -> bool:
    """Replace global UNIQUE(lineup_hash) with UNIQUE(team_id, lineup_hash).

    Must run BEFORE ``repair_shared_lineups``: while the legacy global
    constraint is in place, no second row can share a hash, so the repair
    cannot create the per-team duplicates it needs.

    * SQLite cannot drop a unique constraint in place, so the table is
      rebuilt using SQLite's documented 12-step procedure (create, copy,
      drop, rename) inside ONE transaction with ``foreign_keys=OFF``.
      Renaming the *old* table first would instead rewrite
      ``lineup_segments``'s foreign key to point at the dropped table,
      because ``legacy_alter_table`` is off by default.
    * Postgres drops the legacy constraint and creates the composite one.

    Returns True when the schema was changed.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateTable

    engine = db.engine
    if not inspect(engine).has_table("lineups"):
        return False
    changed = False
    if engine.dialect.name == "sqlite":
        insp = inspect(engine)
        try:
            uniques = insp.get_unique_constraints("lineups")
        except Exception:
            uniques = []
        has_composite = any(
            set(u.get("column_names") or []) == {"team_id", "lineup_hash"}
            for u in uniques
        )
        if has_composite:
            return False
        legacy_global = any(
            set(u.get("column_names") or []) == {"lineup_hash"}
            for u in uniques
        )
        if not legacy_global:
            # Older SQLite builds report unique constraints unreliably, so
            # fall back to the stored DDL.
            try:
                row = db.session.execute(
                    text(
                        "SELECT sql FROM sqlite_master "
                        "WHERE type='table' AND name='lineups'"
                    )
                ).first()
                ddl = (row[0] if row else "") or ""
            except Exception:
                ddl = ""
            compact = ddl.replace(" ", "")
            if "UNIQUE(lineup_hash)" not in compact and "UNIQUE(lineup_hash)" not in ddl:
                return False
        # Data cannot contain cross-team duplicates yet (the global
        # constraint prevented them), so a straight copy is safe.
        cols = [c.name for c in Lineup.__table__.columns]
        collist = ", ".join(f'"{c}"' for c in cols)
        ddl_new = str(CreateTable(Lineup.__table__).compile(engine)).replace(
            "CREATE TABLE lineups", "CREATE TABLE lineups_new", 1
        )
        with engine.begin() as conn:
            # Must be outside a transaction to take effect, hence
            # exec_driver_sql on a raw connection.
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.exec_driver_sql(ddl_new)
            conn.exec_driver_sql(  # noqa: S608 - column names come from the model
                f'INSERT INTO lineups_new ({collist}) SELECT {collist} FROM lineups'
            )
            conn.exec_driver_sql("DROP TABLE lineups")
            conn.exec_driver_sql("ALTER TABLE lineups_new RENAME TO lineups")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        db.session.commit()
        return True

    # Postgres / other: drop the legacy global constraint, add the composite.
    try:
        rows = db.session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'lineups'::regclass AND contype = 'u'"
            )
        ).fetchall()
    except Exception:
        return False
    names = [r[0] for r in rows]
    composite = [
        n for n in names if n == "uq_lineups_team_hash"
    ]
    legacy = [
        n for n in names
        if n != "uq_lineups_team_hash"
    ]
    for name in legacy:
        try:
            db.session.execute(
                text(f'ALTER TABLE lineups DROP CONSTRAINT "{name}"')  # noqa: S608 - name from pg_constraint
            )
            changed = True
        except Exception:
            db.session.rollback()
            return changed
    if not composite:
        try:
            db.session.execute(
                text(
                    "ALTER TABLE lineups ADD CONSTRAINT uq_lineups_team_hash "
                    "UNIQUE (team_id, lineup_hash)"
                )
            )
            changed = True
        except Exception:
            db.session.rollback()
            return changed
    if changed:
        db.session.commit()
    return changed
