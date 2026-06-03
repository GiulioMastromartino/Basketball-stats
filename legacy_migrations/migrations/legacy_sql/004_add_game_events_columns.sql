-- Migration: Add missing columns to game_events table
-- Run this if you get "table game_events has no column named quarter" error

-- Add quarter column
ALTER TABLE game_events ADD COLUMN quarter INTEGER;

-- Add time_remaining column
ALTER TABLE game_events ADD COLUMN time_remaining VARCHAR(10);

-- Add score_margin column
ALTER TABLE game_events ADD COLUMN score_margin INTEGER;
