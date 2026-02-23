#!/usr/bin/env python3
"""
Backfill script to assign possession numbers to existing GameEvents.

This script assigns possession numbers to all GameEvents that don't have them,
then recalculates lineup segment stats.

Usage:
    flask shell
    >>> from scripts.backfill_possessions import backfill_possessions
    >>> backfill_possessions()

Or from command line:
    python scripts/backfill_possessions.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.models import db, Game, GameEvent, LineupSegment
from core.services.game_service import assign_possession_numbers
from core.services.lineup_service import (
    calculate_segment_stats,
    update_lineup_cached_stats,
)


def backfill_possessions():
    """
    Assign possession numbers to all games and recalculate lineup stats.
    """
    # Get all games
    games = Game.query.all()
    print(f"Found {len(games)} games to process")

    games_updated = 0
    segments_updated = 0

    for game in games:
        # Check if game has events without possession numbers
        events_without_possession = GameEvent.query.filter(
            GameEvent.game_id == game.id, GameEvent.possession_number == None
        ).count()

        if events_without_possession > 0:
            print(f"Assigning possessions for game {game.id} ({game.opponent})...")
            assign_possession_numbers(game.id)
            games_updated += 1

        # Recalculate lineup segment stats for this game
        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        for segment in segments:
            calculate_segment_stats(segment.id)
            segments_updated += 1

        # Update lineup cached stats
        lineup_ids = set(s.lineup_id for s in segments if s.lineup_id)
        for lineup_id in lineup_ids:
            update_lineup_cached_stats(lineup_id)

    print(f"\nBackfill complete!")
    print(f"  Games updated: {games_updated}")
    print(f"  Segments recalculated: {segments_updated}")

    return {
        "games_updated": games_updated,
        "segments_updated": segments_updated,
    }


if __name__ == "__main__":
    from run import app

    with app.app_context():
        backfill_possessions()
