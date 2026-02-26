-- Database Performance Indexes
-- Run this to optimize query performance

CREATE INDEX IF NOT EXISTS idx_playerstats_player_name ON player_stats(player_name);
CREATE INDEX IF NOT EXISTS idx_playerstats_game_id ON player_stats(game_id);
CREATE INDEX IF NOT EXISTS idx_playerstats_minutes ON player_stats(minutes);

CREATE INDEX IF NOT EXISTS idx_games_sort_date ON games(sort_date);
CREATE INDEX IF NOT EXISTS idx_games_game_type ON games(game_type);
CREATE INDEX IF NOT EXISTS idx_games_opponent ON games(opponent);
CREATE INDEX IF NOT EXISTS idx_games_result ON games(result);

CREATE INDEX IF NOT EXISTS idx_playerstats_game_player ON player_stats(game_id, player_name);
CREATE INDEX IF NOT EXISTS idx_games_type_date ON games(game_type, sort_date);
