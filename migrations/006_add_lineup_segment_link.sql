-- Migration: Add lineup_segment_id to game_events table
-- Links game events to lineup segments for tracking which lineup was on court

-- Add lineup_segment_id column (references lineup_segments.id)
ALTER TABLE game_events ADD COLUMN lineup_segment_id INTEGER REFERENCES lineup_segments(id);
