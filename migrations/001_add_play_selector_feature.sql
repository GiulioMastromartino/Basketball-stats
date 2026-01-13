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
-- PART 5: Insert sample plays for testing
-- ============================================================
INSERT OR IGNORE INTO plays (id, name, description, play_type) VALUES
(1, 'Pick & Roll (Offensive)', 'Ball handler uses screener to create space', 'Offense'),
(2, 'Isolation', 'One-on-one play setup', 'Offense'),
(3, 'Post-Up', 'Player posts up in the paint', 'Offense'),
(4, 'Fast Break', 'Quick transition offense', 'Offense'),
(5, 'Screen Away', 'Off-ball screen for shooter', 'Offense'),
(6, 'Hand-Off', 'Dribble hand-off play', 'Offense'),
(7, 'Backdoor Cut', 'Cut to basket behind defender', 'Offense'),
(8, 'Drive & Kick', 'Drive to basket and kick out to shooter', 'Offense'),
(9, 'High-Low', 'Pass from high post to low post', 'Offense'),
(10, 'Motion Offense', 'Continuous movement offense', 'Offense'),
(11, 'Zone Defense', '2-3, 3-2, or 1-3-1 zone', 'Defense'),
(12, 'Man-to-Man Defense', 'Each player guards an opponent', 'Defense'),
(13, 'Press Defense', 'Full court defensive pressure', 'Defense'),
(14, 'Trap Defense', 'Double team to force turnover', 'Defense'),
(15, 'Help Defense', 'Rotation to help teammate', 'Defense'),
(16, 'Transition Defense', 'Getting back on defense quickly', 'Defense'),
(17, 'Inbound Play', 'Set play after made basket or out of bounds', 'Special'),
(18, 'Last Shot', 'End of quarter/game situation', 'Special'),
(19, 'Out of Timeout', 'Play called after timeout', 'Special'),
(20, 'Free Play', 'Unstructured play', 'Offense');

-- ============================================================
-- VERIFICATION QUERIES (Run separately to check migration)
-- ============================================================
-- SELECT * FROM pragma_table_info('shot_events') WHERE name = 'play_id';
-- SELECT * FROM pragma_table_info('game_events') WHERE name IN ('shot_attempt', 'play_id');
-- SELECT COUNT(*) as play_count FROM plays;
-- SELECT name, play_type FROM plays ORDER BY play_type, name;