#!/usr/bin/env python3
"""
Data Integrity Migration Script
Ensures all legacy shot events have appropriate play_id values (or NULL).

This script:
1. Analyzes existing shot_events for play_id consistency
2. Attempts to match shots to plays based on play tags/descriptions
3. Sets NULL for unmatched shots (explicitly no play association)
4. Validates data integrity after migration
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.models import db, ShotEvent, Play, GameEvent
from sqlalchemy import text


def create_app():
    """Create Flask app for database context."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///basketball_stats.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def analyze_current_state():
    """Analyze current state of shot_events play_id values."""
    print("\n=== Analyzing Current State ===")
    
    # Total shots
    total_shots = ShotEvent.query.count()
    print(f"Total shot events: {total_shots}")
    
    # Shots with play_id
    shots_with_play = ShotEvent.query.filter(ShotEvent.play_id.isnot(None)).count()
    print(f"Shots with play_id: {shots_with_play}")
    
    # Shots without play_id
    shots_without_play = ShotEvent.query.filter(ShotEvent.play_id.is_(None)).count()
    print(f"Shots without play_id (NULL): {shots_without_play}")
    
    # Available plays
    total_plays = Play.query.count()
    print(f"Total plays available: {total_plays}")
    
    return {
        'total_shots': total_shots,
        'shots_with_play': shots_with_play,
        'shots_without_play': shots_without_play,
        'total_plays': total_plays
    }


def migrate_shot_play_ids():
    """
    Migrate shot events to ensure proper play_id values.
    
    Strategy:
    1. For shots with valid play_id - verify the play exists
    2. For shots with invalid play_id - set to NULL
    3. For shots without play_id - keep as NULL (explicit no association)
    """
    print("\n=== Migrating Shot Play IDs ===")
    
    # Get all valid play IDs
    valid_play_ids = set(p.id for p in Play.query.all())
    print(f"Valid play IDs: {valid_play_ids}")
    
    # Find shots with invalid play_id references
    invalid_shots = ShotEvent.query.filter(
        ShotEvent.play_id.isnot(None),
        ~ShotEvent.play_id.in_(valid_play_ids)
    ).all()
    
    if invalid_shots:
        print(f"Found {len(invalid_shots)} shots with invalid play_id references")
        for shot in invalid_shots:
            print(f"  Shot {shot.id}: play_id={shot.play_id} (invalid)")
            shot.play_id = None
        
        db.session.commit()
        print("Set invalid play_id references to NULL")
    else:
        print("No invalid play_id references found")
    
    # Verify foreign key integrity
    print("\nVerifying foreign key integrity...")
    result = db.session.execute(text("""
        SELECT COUNT(*) FROM shot_events se
        LEFT JOIN plays p ON se.play_id = p.id
        WHERE se.play_id IS NOT NULL AND p.id IS NULL
    """)).scalar()
    
    if result == 0:
        print("✓ All play_id references are valid")
    else:
        print(f"✗ Found {result} orphaned play_id references")
    
    return len(invalid_shots)


def infer_play_from_game_events():
    """
    Attempt to infer play associations from game_events.
    
    If a shot event corresponds to a game_event that has a play_id,
    we can infer the association.
    """
    print("\n=== Inferring Play Associations from Game Events ===")
    
    # Find game events with play_id that correspond to shots
    game_events_with_plays = GameEvent.query.filter(
        GameEvent.play_id.isnot(None),
        GameEvent.event_type.in_(['SHOT_2PT', 'SHOT_3PT'])
    ).all()
    
    inferred_count = 0
    
    for event in game_events_with_plays:
        # Try to find corresponding shot event
        shot = ShotEvent.query.filter(
            ShotEvent.game_id == event.game_id,
            ShotEvent.player_name == event.player_name,
            ShotEvent.play_id.is_(None)  # Only update shots without play_id
        ).first()
        
        if shot:
            shot.play_id = event.play_id
            inferred_count += 1
            print(f"  Inferred: Shot {shot.id} -> Play {event.play_id}")
    
    if inferred_count > 0:
        db.session.commit()
        print(f"Inferred {inferred_count} play associations")
    else:
        print("No play associations could be inferred")
    
    return inferred_count


def validate_migration():
    """Validate the migration completed successfully."""
    print("\n=== Validating Migration ===")
    
    # Check for NULL play_id (should be valid)
    null_count = ShotEvent.query.filter(ShotEvent.play_id.is_(None)).count()
    print(f"Shots with NULL play_id: {null_count} (valid)")
    
    # Check for valid play_id references
    valid_count = db.session.execute(text("""
        SELECT COUNT(*) FROM shot_events se
        JOIN plays p ON se.play_id = p.id
    """)).scalar()
    print(f"Shots with valid play_id: {valid_count}")
    
    # Check for orphaned references (should be 0)
    orphaned = db.session.execute(text("""
        SELECT COUNT(*) FROM shot_events se
        LEFT JOIN plays p ON se.play_id = p.id
        WHERE se.play_id IS NOT NULL AND p.id IS NULL
    """)).scalar()
    
    if orphaned == 0:
        print("✓ No orphaned play_id references")
        return True
    else:
        print(f"✗ Found {orphaned} orphaned play_id references")
        return False


def run_migration():
    """Run the complete migration process."""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("SHOT EVENT PLAY_ID MIGRATION")
        print("=" * 60)
        
        # Step 1: Analyze current state
        state = analyze_current_state()
        
        # Step 2: Migrate invalid play_id references
        invalid_fixed = migrate_shot_play_ids()
        
        # Step 3: Infer play associations from game events
        inferred = infer_play_from_game_events()
        
        # Step 4: Validate migration
        success = validate_migration()
        
        # Final summary
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Total shots processed: {state['total_shots']}")
        print(f"Invalid play_id fixed: {invalid_fixed}")
        print(f"Play associations inferred: {inferred}")
        print(f"Migration successful: {'YES' if success else 'NO'}")
        print("=" * 60)
        
        return success


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
