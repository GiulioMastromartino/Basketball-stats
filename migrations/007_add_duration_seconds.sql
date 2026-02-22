-- Add duration_seconds column to lineup_segments table
-- This tracks the actual playing time in seconds for each lineup segment

ALTER TABLE lineup_segments ADD COLUMN duration_seconds INTEGER DEFAULT 0;

-- Create index for faster queries on duration
CREATE INDEX IF NOT EXISTS idx_lineup_segments_duration ON lineup_segments(duration_seconds);
