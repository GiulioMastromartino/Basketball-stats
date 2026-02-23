-- Migration: Add timeline fields to game_events table
-- Adds possession_number and game_seconds for improved timeline tracking

-- Add possession_number column (sequence number for each possession)
ALTER TABLE game_events ADD COLUMN possession_number INTEGER;

-- Add game_seconds column (absolute game time in seconds)
ALTER TABLE game_events ADD COLUMN game_seconds INTEGER;
