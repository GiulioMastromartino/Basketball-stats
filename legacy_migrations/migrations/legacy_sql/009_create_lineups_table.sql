-- Create lineups table for multi-game tracking
CREATE TABLE IF NOT EXISTS lineups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lineup_hash VARCHAR(64) UNIQUE NOT NULL,
    players JSON NOT NULL,
    display_name VARCHAR(100),
    is_starting BOOLEAN DEFAULT 0,
    
    total_seconds INTEGER DEFAULT 0,
    total_possessions INTEGER DEFAULT 0,
    points_scored INTEGER DEFAULT 0,
    points_allowed INTEGER DEFAULT 0,
    games_played INTEGER DEFAULT 0,
    segment_count INTEGER DEFAULT 0,
    
    ortg FLOAT DEFAULT 0,
    drtg FLOAT DEFAULT 0,
    net_rating FLOAT DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add lineup_id foreign key to lineup_segments
ALTER TABLE lineup_segments ADD COLUMN lineup_id INTEGER REFERENCES lineups(id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_lineups_hash ON lineups(lineup_hash);
CREATE INDEX IF NOT EXISTS idx_lineups_net_rating ON lineups(net_rating);
CREATE INDEX IF NOT EXISTS idx_lineup_segments_lineup_id ON lineup_segments(lineup_id);
