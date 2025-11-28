class AdvancedAnalytics:
    @staticmethod
    def calculate_ts_percent(points, fga, fta):
        """True Shooting Percentage"""
        if fga == 0 and fta == 0: return 0.0
        return round(points / (2 * (fga + 0.44 * fta)) * 100, 1)

    @staticmethod
    def calculate_efg_percent(fgm, tpm, fga):
        """Effective Field Goal Percentage"""
        if fga == 0: return 0.0
        return round((fgm + 0.5 * tpm) / fga * 100, 1)

    @staticmethod
    def calculate_game_score(p):
        """Hollinger Game Score"""
        return round(p['points'] + 0.4 * p['fgm'] - 0.7 * p['fga'] - 0.4*(p['fta'] - p['ftm']) + 0.7 * p['oreb'] + 0.3 * p['dreb'] + p['stl'] + 0.7 * p['ast'] + 0.7 * p['blk'] - 0.4 * p['pf'] - p['tov'], 1)

    @staticmethod
    def enrich_player_stats(df):
        """Add advanced metrics to player DataFrame"""
        if df.empty: return df
        
        df['ts_percent'] = df.apply(lambda x: AdvancedAnalytics.calculate_ts_percent(x['points'], x['fga'], x['fta']), axis=1)
        df['efg_percent'] = df.apply(lambda x: AdvancedAnalytics.calculate_efg_percent(x['fgm'], x['tpm'], x['fga']), axis=1)
        # Game Score requires dictionary access
        df['game_score'] = df.apply(lambda x: AdvancedAnalytics.calculate_game_score(x), axis=1)
        
        return df
