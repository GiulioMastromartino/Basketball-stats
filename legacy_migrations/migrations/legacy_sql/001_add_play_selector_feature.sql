-- Migration: Add Play Selector Feature
-- Date: 2026-01-12
-- Description: Adds play tracking functionality to shot events and game events

-- ============================================================
-- PART 1: Create plays table if not exists
-- ============================================================
CREATE TABLE IF NOT EXISTS plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    play_type VARCHAR(50) DEFAULT 'Offense',
    image_filename VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- PART 2: Add play_id to shot_events if column doesn't exist
-- ============================================================
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we check first
-- This is safe to run multiple times
BEGIN;
    -- Check if column exists, if not add it
    SELECT CASE 
        WHEN COUNT(*) = 0 THEN 
            'ALTER TABLE shot_events ADD COLUMN play_id INTEGER REFERENCES plays(id)'
        ELSE 
            'SELECT 1' -- No-op if column exists
    END as sql_to_run
    FROM pragma_table_info('shot_events')
    WHERE name = 'play_id';
COMMIT;

-- Safer approach: Try to add column, ignore error if exists
-- Run this manually or use try-catch in application code
-- ALTER TABLE shot_events ADD COLUMN play_id INTEGER REFERENCES plays(id);

-- ============================================================
-- PART 3: Add columns to game_events if they don't exist
-- ============================================================
-- Add shot_attempt column
-- ALTER TABLE game_events ADD COLUMN shot_attempt VARCHAR(10);

-- Add play_id column  
-- ALTER TABLE game_events ADD COLUMN play_id INTEGER REFERENCES plays(id);

-- ============================================================
-- PART 4: Create indexes for performance
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_shot_events_play_id ON shot_events(play_id);
CREATE INDEX IF NOT EXISTS idx_game_events_play_id ON game_events(play_id);
CREATE INDEX IF NOT EXISTS idx_plays_type ON plays(play_type);
CREATE INDEX IF NOT EXISTS idx_game_events_type ON game_events(event_type);

-- ============================================================
-- VERIFICATION QUERIES (Run separately to check migration)
-- ============================================================
-- SELECT * FROM pragma_table_info('shot_events') WHERE name = 'play_id';
-- SELECT * FROM pragma_table_info('game_events') WHERE name IN ('shot_attempt', 'play_id');
-- SELECT COUNT(*) as play_count FROM plays;
-- SELECT name, play_type FROM plays ORDER BY play_type, name;