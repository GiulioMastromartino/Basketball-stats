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
from core.models import db, GameEvent, Lineup, LineupSegment, PlayerLineupStats

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


def get_or_create_lineup(players: list, is_starting: bool = False):
    """
    Get existing lineup or create new one.

    Args:
        players: List of 5 player names
        is_starting: Whether this is a starting lineup

    Returns:
        Lineup object (existing or newly created)
    """
    if len(players) != 5:
        return None

    lineup_hash = generate_lineup_hash(players)
    lineup = Lineup.query.filter_by(lineup_hash=lineup_hash).first()

    if not lineup:
        lineup = Lineup(
            lineup_hash=lineup_hash, players=sorted(players), is_starting=is_starting
        )
        db.session.add(lineup)
        db.session.flush()

    return lineup


def update_lineup_cached_stats(lineup_id: int):
    """Update cached stats for a lineup by aggregating all segments."""
    from datetime import datetime

    lineup = Lineup.query.get(lineup_id)
    if not lineup:
        return

    segments = LineupSegment.query.filter_by(lineup_id=lineup_id).all()

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


def build_lineup_segments(
    game_id: int, events: list, starting_lineup: list = None
) -> list:
    """
    Process events chronologically to create LineupSegment records.

    Args:
        game_id: ID of the game being processed
        events: List of GameEvent objects sorted chronologically by timestamp
        starting_lineup: Optional list of 5 player names as initial lineup.
                        If None, extracts from first 5 SUB_IN events in Q1.

    Returns:
        List of created segment IDs
    """
    LineupSegment.query.filter_by(game_id=game_id).delete()
    db.session.flush()

    if not events:
        db.session.commit()
        return []

    try:
        current_lineup = []

        if starting_lineup:
            current_lineup = list(starting_lineup)
        else:
            first_sub_in_timestamp = None
            for event in events:
                if event.event_type == "SUB_IN":
                    first_sub_in_timestamp = event.timestamp
                    break

            players_before_sub = []
            for event in events:
                if first_sub_in_timestamp and event.timestamp >= first_sub_in_timestamp:
                    break

                if event.player_name and event.event_type not in ("SUB_IN", "SUB_OUT"):
                    if event.player_name not in players_before_sub:
                        players_before_sub.append(event.player_name)
                        if len(players_before_sub) == 5:
                            break

            current_lineup = players_before_sub

        if len(current_lineup) < 5:
            db.session.commit()
            return []

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
                    current_lineup, is_starting=True
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

                    lineup = get_or_create_lineup(current_lineup)

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
        elif event.event_type == "FT_MADE":
            points_scored += 1
        elif event.event_type == "OPP_SCORE":
            pts = 2
            if event.detail:
                try:
                    if isinstance(event.detail, str) and (event.detail.startswith('{') or event.detail.startswith('[')):
                        import json
                        detail_data = json.loads(event.detail)
                        if isinstance(detail_data, dict):
                            pts = int(detail_data.get('points', 2))
                        else:
                            pts = int(event.detail)
                    else:
                        pts = int(event.detail)
                except (ValueError, TypeError, json.JSONDecodeError):
                    pts = 2
            points_allowed += pts

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
        elif event.event_type == "OPP_OREB" or event.event_type == "OPP_SCORE":
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
        segment.duration_seconds = calculate_segment_duration(segment, all_events)

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
            stats["fta"] += 1

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
    game_id: int, events: list, starting_lineup: list = None
) -> None:
    """
    Optimized entry point for lineup processing.
    Uses batch operations to avoid timeouts.
    """
    # 1. Build segments
    segment_ids = build_lineup_segments(game_id, events, starting_lineup)
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
            elif et == "OPP_SCORE":
                pts = 2
                if event.detail:
                    try:
                        if isinstance(event.detail, str) and (event.detail.startswith('{') or event.detail.startswith('[')):
                            import json
                            detail_data = json.loads(event.detail)
                            if isinstance(detail_data, dict):
                                pts = int(detail_data.get('points', 2))
                            else:
                                pts = int(event.detail)
                        else:
                            pts = int(event.detail)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pts = 2
                pts_allowed += pts
            elif et == "OPP_OREB":
                reb_conceded += 1
                for p in player_map: player_map[p]["reb_conceded"] += 1
            
            # Atomic stats
            if event.player_name in player_map:
                p_stats = player_map[event.player_name]
                if et == "FT": p_stats["fta"] += 1
                elif et == "FT_MISS": p_stats["fta"] += 1
                elif et == "TURNOVER": p_stats["tov"] += 1
                elif et == "AST": p_stats["ast"] += 1
                elif et == "STL": p_stats["stl"] += 1
                elif et == "BLK": p_stats["blk"] += 1
                elif et in ("OREB", "REBOUND_OFFENSIVE"): p_stats["oreb"] += 1
                elif et in ("DREB", "REBOUND_DEFENSIVE"): p_stats["dreb"] += 1

            # Possession tracking
            if et in ["SHOT_2PT", "SHOT_3PT", "TURNOVER", "FT", "FT_MADE", "FT_MISS", "OPP_OREB", "OPP_SCORE"]:
                if event.possession_number and event.possession_number not in poss_ending:
                    poss_ending.add(event.possession_number)
                    poss += 1

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

    # 7. Update affected lineups
    for lid in lineup_ids:
        update_lineup_cached_stats(lid)
