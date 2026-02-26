-- Advanced Analytics Migration
-- Creates tables for lineup tracking, possessions, shot zones, and player lineup stats

-- Lineup Segments: Track which 5 players are on the floor at every moment
CREATE TABLE IF NOT EXISTS lineup_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    start_timestamp BIGINT NOT NULL,
    end_timestamp BIGINT,
    quarter INTEGER,
    players JSON NOT NULL,
    lineup_hash VARCHAR(64) NOT NULL,
    points_scored INTEGER DEFAULT 0,
    points_allowed INTEGER DEFAULT 0,
    possessions INTEGER DEFAULT 0,
    FOREIGN KEY (game_id) REFERENCES games(id)
);

CREATE INDEX IF NOT EXISTS idx_lineup_segments_game_id ON lineup_segments(game_id);
CREATE INDEX IF NOT EXISTS idx_lineup_segments_hash ON lineup_segments(lineup_hash);

-- Possessions: Track distinct possessions for pace-adjusted stats
CREATE TABLE IF NOT EXISTS possessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    start_event_id INTEGER NOT NULL,
    end_event_id INTEGER,
    team_possession BOOLEAN DEFAULT 1,
    quarter INTEGER,
    points INTEGER DEFAULT 0,
    play_id INTEGER,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (start_event_id) REFERENCES game_events(id),
    FOREIGN KEY (end_event_id) REFERENCES game_events(id),
    FOREIGN KEY (play_id) REFERENCES plays(id)
);

CREATE INDEX IF NOT EXISTS idx_possessions_game_id ON possessions(game_id);
CREATE INDEX IF NOT EXISTS idx_possessions_play_id ON possessions(play_id);

-- Shot Zones: Expected point values for different court zones
CREATE TABLE IF NOT EXISTS shot_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_name VARCHAR(50) UNIQUE NOT NULL,
    zone_type VARCHAR(20) NOT NULL,
    expected_value FLOAT NOT NULL,
    description VARCHAR(255),
    x_min FLOAT,
    x_max FLOAT,
    y_min FLOAT,
    y_max FLOAT
);

-- Player Lineup Stats: Aggregated stats for a player during a lineup segment
CREATE TABLE IF NOT EXISTS player_lineup_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lineup_segment_id INTEGER NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    points INTEGER DEFAULT 0,
    fga INTEGER DEFAULT 0,
    fgm INTEGER DEFAULT 0,
    tpa INTEGER DEFAULT 0,
    tpm INTEGER DEFAULT 0,
    fta INTEGER DEFAULT 0,
    ftm INTEGER DEFAULT 0,
    oreb INTEGER DEFAULT 0,
    dreb INTEGER DEFAULT 0,
    ast INTEGER DEFAULT 0,
    stl INTEGER DEFAULT 0,
    blk INTEGER DEFAULT 0,
    tov INTEGER DEFAULT 0,
    FOREIGN KEY (lineup_segment_id) REFERENCES lineup_segments(id)
);

CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_segment ON player_lineup_stats(lineup_segment_id);
CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_player ON player_lineup_stats(player_name);

-- Add new columns to game_events table
ALTER TABLE game_events ADD COLUMN quarter INTEGER;
ALTER TABLE game_events ADD COLUMN time_remaining VARCHAR(10);
ALTER TABLE game_events ADD COLUMN score_margin INTEGER;

-- Insert default shot zone values
INSERT OR IGNORE INTO shot_zones (zone_name, zone_type, expected_value, description, x_min, x_max, y_min, y_max) VALUES
    ('Rim', 'Paint', 1.20, 'Layups and dunks at the basket', 210, 290, 0, 100),
    ('Paint', 'Paint', 0.85, 'Shots in the paint (non-rim)', 150, 350, 0, 150),
    ('Midrange', 'Midrange', 0.75, 'Mid-range jumpers', 0, 500, 100, 350),
    ('Corner_3', 'Corner_3', 1.10, 'Corner 3-pointers', 0, 500, 0, 100),
    ('Above_Break_3', 'Above_Break_3', 1.05, 'Above-the-break 3-pointers', 0, 500, 300, 470),
    ('FT', 'FT', 0.75, 'Free throws', NULL, NULL, NULL, NULL);
