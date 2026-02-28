#!/usr/bin/env python3
"""Test script for schema 3.0 JSON import support."""

import json
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from web import create_app
from core.models import db, Game, LineupSegment, GameEvent
from core.services.game_service import create_game_from_live_data


def test_import_schema_3():
    app = create_app("development")
    with app.app_context():
        # Load test payload
        payload_path = Path("test_game_payload.json")
        if not payload_path.exists():
            print("test_game_payload.json not found")
            return

        with open(payload_path, "r") as f:
            data = json.load(f)

        print(f"Importing game with schema_version: {data.get('schema_version')}")
        print(f"Features: {data.get('features')}")
        
        # Clean up existing games with same name/date to avoid duplicate errors
        existing_game = Game.query.filter_by(
            date=data.get('game', {}).get('date', data.get('date')),
            opponent=data.get('game', {}).get('opponent', data.get('opponent'))
        ).first()
        if existing_game:
            print(f"Cleaning up existing game ID: {existing_game.id}")
            # Delete related data
            GameEvent.query.filter_by(game_id=existing_game.id).delete()
            LineupSegment.query.filter_by(game_id=existing_game.id).delete()
            db.session.delete(existing_game)
            db.session.commit()
        
        try:
            game = create_game_from_live_data(data)
            print(f"Successfully created game ID: {game.id}")
            print(f"Schema version: {game.schema_version}")
            
            # Check if lineup segments were created
            segments = LineupSegment.query.filter_by(game_id=game.id).all()
            print(f"Number of lineup segments created: {len(segments)}")
            
            # Check if possession numbers were assigned
            events_with_possession = GameEvent.query.filter(
                GameEvent.game_id == game.id,
                GameEvent.possession_number.isnot(None)
            ).count()
            print(f"Number of events with possession assigned: {events_with_possession}")
            
            # Check if zone field is extracted
            events_with_zone = GameEvent.query.filter(
                GameEvent.game_id == game.id,
                GameEvent.zone.isnot(None)
            ).count()
            print(f"Number of events with zone assigned: {events_with_zone}")
            
            # Check zone values
            zones = db.session.query(GameEvent.zone).filter(
                GameEvent.game_id == game.id,
                GameEvent.zone.isnot(None)
            ).distinct().all()
            print(f"Zone values found: {[z[0] for z in zones]}")
            
            # Check if play_id is assigned
            events_with_play = GameEvent.query.filter(
                GameEvent.game_id == game.id,
                GameEvent.play_id.isnot(None)
            ).count()
            print(f"Number of events with play_id assigned: {events_with_play}")
            
            # Summary
            print("\n=== TEST RESULTS ===")
            all_passed = True
            
            if len(segments) > 0:
                print("✓ Lineup segments created")
            else:
                print("✗ FAILURE: No lineup segments created")
                all_passed = False
                
            if events_with_zone > 0:
                print(f"✓ Zone field extracted ({events_with_zone} events)")
            else:
                print("✗ FAILURE: No zones extracted")
                all_passed = False
                
            if events_with_play > 0:
                print(f"✓ Play tracking enabled ({events_with_play} events with plays)")
            else:
                print("✗ FAILURE: No play tracking")
                all_passed = False
                
            if game.schema_version == 3:
                print("✓ Schema version correctly set to 3")
            else:
                print(f"✗ FAILURE: Schema version is {game.schema_version}, expected 3")
                all_passed = False
            
            if all_passed:
                print("\n✓ ALL TESTS PASSED - Schema 3.0 import working!")
            else:
                print("\n✗ SOME TESTS FAILED")
                
            # Clean up
            # db.session.delete(game)
            # db.session.commit()
            
        except Exception as e:
            print(f"Error during import: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test_import_schema_3()
