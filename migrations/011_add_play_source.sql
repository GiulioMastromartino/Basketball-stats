-- Migration: Add Play Source Column
-- Date: 2026-02-23
-- Description: Adds source column to plays table to track where plays came from

-- ============================================================
-- PART 1: Add source column to plays table
-- ============================================================
-- SQLite doesn't support IF NOT EXISTS for ADD COLUMN, so we handle in app code
-- This is the raw SQL that should be run:
-- ALTER TABLE plays ADD COLUMN source VARCHAR(20) DEFAULT 'imported';

-- For SQLite, run this via the application or manually:
-- Check if column exists first:
-- SELECT COUNT(*) FROM pragma_table_info('plays') WHERE name = 'source';

-- ============================================================
-- PART 2: Update existing plays to have source='imported'
-- ============================================================
-- This will be handled automatically by the DEFAULT constraint for new rows
-- For existing plays, run this after adding the column:
-- UPDATE plays SET source = 'imported' WHERE source IS NULL;

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================
-- SELECT * FROM pragma_table_info('plays') WHERE name = 'source';
-- SELECT source, COUNT(*) FROM plays GROUP BY source;
