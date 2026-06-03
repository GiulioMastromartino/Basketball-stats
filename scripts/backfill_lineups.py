#!/usr/bin/env python3
"""
Backfill script to populate lineups table and link existing lineup_segments.

This script:
1. Creates Lineup records from unique lineup_hashes in lineup_segments
2. Links each LineupSegment to its corresponding Lineup
3. Updates cached stats for each Lineup

Usage:
    flask shell
    >>> from scripts.backfill_lineups import backfill_lineups
    >>> backfill_lineups()

Or from command line:
    python scripts/backfill_lineups.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from datetime import datetime
from core.models import db, Game, Lineup, LineupSegment
from core.services.lineup_service import (
    generate_lineup_hash,
    update_lineup_cached_stats,
)


def backfill_lineups():
    """
    Populate lineups table from existing lineup_segments.

    Creates Lineup records for each unique lineup_hash and links segments.
    """
    segments = LineupSegment.query.filter((LineupSegment.lineup_id == None)).all()

    total_segments = len(segments)
    print(f"Found {total_segments} segments to process")

    lineup_cache = {}

    existing_lineups = Lineup.query.all()
    for lineup in existing_lineups:
        lineup_cache[lineup.lineup_hash] = lineup.id
    print(f"Found {len(existing_lineups)} existing lineups")

    created_count = 0
    linked_count = 0
    updated_count = 0

    for i, segment in enumerate(segments, 1):
        try:
            lineup_hash = segment.lineup_hash

            players = segment.players
            if isinstance(players, str):
                import json

                try:
                    players = json.loads(players)
                except:
                    players = []

            if lineup_hash not in lineup_cache:
                is_starting = i == 1

                lineup = Lineup(
                    lineup_hash=lineup_hash,
                    players=sorted(players) if players else [],
                    is_starting=is_starting,
                )
                db.session.add(lineup)
                db.session.flush()
                lineup_cache[lineup_hash] = lineup.id
                created_count += 1

            segment.lineup_id = lineup_cache[lineup_hash]
            linked_count += 1

            if i % 100 == 0:
                db.session.commit()
                print(f"Processed {i}/{total_segments} segments...")

        except Exception as e:
            print(f"Error processing segment {segment.id}: {e}")
            db.session.rollback()

    db.session.commit()

    print("Updating cached stats for all lineups...")
    all_lineup_ids = list(set(lineup_cache.values()))
    for lineup_id in all_lineup_ids:
        try:
            update_lineup_cached_stats(lineup_id)
            updated_count += 1
        except Exception as e:
            print(f"Error updating lineup {lineup_id}: {e}")

    stats = {
        "total_segments": total_segments,
        "lineups_created": created_count,
        "segments_linked": linked_count,
        "lineups_updated": updated_count,
    }

    print(f"\nBackfill complete!")
    print(f"  Total segments processed: {total_segments}")
    print(f"  Lineups created: {created_count}")
    print(f"  Segments linked: {linked_count}")
    print(f"  Lineups stats updated: {updated_count}")

    return stats


if __name__ == "__main__":
    from run import app

    with app.app_context():
        backfill_lineups()
