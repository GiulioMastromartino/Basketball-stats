#!/usr/bin/env python3
"""
Backfill script to populate duration_seconds for existing LineupSegment records.

This script recalculates duration for all segments that have duration_seconds = 0 or NULL.
Run this after applying the migration to add the duration_seconds column.

Usage:
    flask shell
    >>> from scripts.backfill_durations import backfill_segment_durations
    >>> backfill_segment_durations()

Or from command line:
    python scripts/backfill_durations.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.models import db, GameEvent, LineupSegment


def calculate_duration(segment, all_events: list) -> int:
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


def backfill_segment_durations(batch_size: int = 100) -> dict:
    """
    Backfill duration_seconds for all LineupSegment records with NULL or 0 values.

    Args:
        batch_size: Number of segments to process before committing

    Returns:
        Dictionary with stats about the backfill operation
    """
    segments = LineupSegment.query.filter(
        (LineupSegment.duration_seconds == None) | (LineupSegment.duration_seconds == 0)
    ).all()

    total_segments = len(segments)
    updated_count = 0
    skipped_count = 0
    error_count = 0

    print(f"Found {total_segments} segments to process")

    game_events_cache = {}

    for i, segment in enumerate(segments, 1):
        try:
            if segment.game_id not in game_events_cache:
                game_events_cache[segment.game_id] = (
                    GameEvent.query.filter_by(game_id=segment.game_id)
                    .order_by(GameEvent.timestamp)
                    .all()
                )

            all_events = game_events_cache[segment.game_id]
            duration = calculate_duration(segment, all_events)

            if duration > 0:
                segment.duration_seconds = duration
                updated_count += 1
            else:
                skipped_count += 1

            if i % batch_size == 0:
                db.session.commit()
                print(f"Processed {i}/{total_segments} segments...")

        except Exception as e:
            error_count += 1
            print(f"Error processing segment {segment.id}: {e}")
            db.session.rollback()

    db.session.commit()

    stats = {
        "total_segments": total_segments,
        "updated": updated_count,
        "skipped": skipped_count,
        "errors": error_count,
    }

    print(f"\nBackfill complete!")
    print(f"  Total segments: {total_segments}")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped (no duration): {skipped_count}")
    print(f"  Errors: {error_count}")

    return stats


if __name__ == "__main__":
    from run import app

    with app.app_context():
        backfill_segment_durations()
