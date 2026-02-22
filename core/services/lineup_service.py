"""
Lineup Segment Processing Service

Handles all lineup segment processing including:
- Generating lineup hashes
- Building lineup segments from game events
- Linking events to segments
- Calculating segment statistics
- Populating player lineup stats
"""

import hashlib
from typing import Optional

from core.models import (
    db,
    GameEvent,
    Lineup,
    LineupSegment,
    PlayerLineupStats,
)


def generate_lineup_hash(players: list) -> str:
    """
    Create MD5 hash of sorted player names for quick lineup lookup.

    Args:
        players: List of player names in the lineup

    Returns:
        MD5 hash string of the sorted player names
    """
    sorted_players = sorted(players)
    players_string = "|".join(sorted_players)
    return hashlib.md5(players_string.encode("utf-8")).hexdigest()


def calculate_segment_duration(segment, all_events: list) -> int:
    """
    Calculate the duration in seconds for a lineup segment based on game_seconds.

    Args:
        segment: LineupSegment object with start_timestamp and end_timestamp
        all_events: List of all GameEvent objects for the game

    Returns:
        Duration in seconds (0 if cannot be calculated)
    """
    segment_events = [
        e
        for e in all_events
        if e.timestamp >= segment.start_timestamp
        and (segment.end_timestamp is None or e.timestamp <= segment.end_timestamp)
    ]

    if not segment_events:
        return 0

    game_secs = [e.game_seconds for e in segment_events if e.game_seconds is not None]

    if len(game_secs) >= 2:
        return max(game_secs) - min(game_secs)
    elif len(game_secs) == 1:
        quarter = segment_events[0].quarter or 1
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
    """
    Recalculate and update cached stats for a lineup.

    Aggregates data from all lineup_segments for this lineup.

    Args:
        lineup_id: ID of the Lineup to update
    """
    from datetime import datetime

    lineup = Lineup.query.get(lineup_id)
    if not lineup:
        return

    segments = LineupSegment.query.filter_by(lineup_id=lineup_id).all()

    lineup.total_seconds = sum(s.duration_seconds or 0 for s in segments)
    lineup.total_possessions = sum(s.possessions or 0 for s in segments)
    lineup.points_scored = sum(s.points_scored or 0 for s in segments)
    lineup.points_allowed = sum(s.points_allowed or 0 for s in segments)
    lineup.segment_count = len(segments)
    lineup.games_played = len(set(s.game_id for s in segments))

    # Calculate ratings
    if lineup.total_possessions > 0:
        lineup.ortg = round(lineup.points_scored / lineup.total_possessions * 100, 1)
        lineup.drtg = round(lineup.points_allowed / lineup.total_possessions * 100, 1)
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

        for event in events:
            if current_segment is None:
                segment_start_timestamp = event.timestamp
                current_quarter = event.quarter
                lineup = get_or_create_lineup(
                    current_lineup, is_starting=(current_segment is None)
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

                sub_in_event = None
                remaining_events = [e for e in events if e.timestamp > event.timestamp]
                for next_event in remaining_events:
                    if (
                        next_event.event_type == "SUB_IN"
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
    Assign lineup_segment_id to each GameEvent based on timestamp.

    Uses segment's start_timestamp and end_timestamp to determine which
    segment each event belongs to.

    Args:
        game_id: ID of the game to process
    """
    segments = (
        LineupSegment.query.filter_by(game_id=game_id)
        .order_by(LineupSegment.start_timestamp)
        .all()
    )

    if not segments:
        return

    events = (
        GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.timestamp).all()
    )

    segment_index = 0

    for event in events:
        while segment_index < len(segments):
            segment = segments[segment_index]

            in_segment = event.timestamp >= segment.start_timestamp

            if segment.end_timestamp is not None:
                in_segment = in_segment and event.timestamp <= segment.end_timestamp

            if in_segment:
                event.lineup_segment_id = segment.id
                break
            elif segment.end_timestamp and event.timestamp > segment.end_timestamp:
                segment_index += 1
                if segment_index >= len(segments):
                    break
            else:
                break

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
    possession_ending_events = set()

    for event in events:
        if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
            points_scored += 2
        elif event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
            points_scored += 3
        elif event.event_type == "FT_MADE":
            points_scored += 1
        elif event.event_type == "OPP_SCORE":
            try:
                points = int(event.detail) if event.detail else 2
            except (ValueError, TypeError):
                points = 2
            points_allowed += points

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

    if all_events:
        segment.duration_seconds = calculate_segment_duration(segment, all_events)

    db.session.commit()

    return {
        "points_scored": points_scored,
        "points_allowed": points_allowed,
        "possessions": possessions,
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
    Main entry point that orchestrates all lineup processing.

    Builds segments, links events, calculates stats, and populates player stats.

    Args:
        game_id: ID of the game to process
        events: List of GameEvent objects sorted chronologically
        starting_lineup: Optional list of 5 player names as initial lineup
    """
    segment_ids = build_lineup_segments(game_id, events, starting_lineup)

    if not segment_ids:
        return

    link_events_to_segments(game_id)

    # Get unique lineup_ids that were affected
    lineup_ids = set()
    for segment_id in segment_ids:
        calculate_segment_stats(segment_id, events)
        populate_player_lineup_stats(segment_id)
        segment = LineupSegment.query.get(segment_id)
        if segment and segment.lineup_id:
            lineup_ids.add(segment.lineup_id)

    # Update cached stats for all affected lineups
    for lineup_id in lineup_ids:
        update_lineup_cached_stats(lineup_id)
