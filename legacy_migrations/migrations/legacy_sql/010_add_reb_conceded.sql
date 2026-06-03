-- Add reb_conceded (offensive rebounds conceded to opponents) tracking
ALTER TABLE player_stats ADD COLUMN reb_conceded INTEGER DEFAULT 0;
ALTER TABLE player_lineup_stats ADD COLUMN reb_conceded INTEGER DEFAULT 0;

-- Index for querying players with high conceded rebounds
CREATE INDEX IF NOT EXISTS idx_player_stats_reb_conceded ON player_stats(reb_conceded);
