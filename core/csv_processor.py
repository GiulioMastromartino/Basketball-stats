import pandas as pd
import os, re
from config import Config

class CSVProcessor:
    @staticmethod
    def parse_filename(filename):
        match = re.match(Config.FILENAME_PATTERN, os.path.splitext(filename)[0])
        if match:
            opp, t_score, o_score, d, m, y, type_code = match.groups()
            return {
                'opponent': opp,
                'team_score': int(t_score),
                'opponent_score': int(o_score),
                'date': f"{d}/{m}",
                'sort_date': f"{y}-{m}-{d}",
                'game_type': Config.GAME_TYPE_MAP.get(type_code, 'Unknown'),
                'result': 'W' if int(t_score) > int(o_score) else 'L'
            }
        return None

    @staticmethod
    def process_game(filepath, info):
        try:
            df = pd.read_csv(filepath)
            players = []
            for _, row in df.iterrows():
                if row['Name'] == 'Total': continue
                players.append({
                    'name': row['Name'],
                    'minutes': row['MIN'],
                    'points': int(row['PTS']),
                    'fgm': int(row['FGM']), 'fga': int(row['FGA']), 'fg_percent': float(row['FG%']),
                    'tpm': int(row['3PM']), 'tpa': int(row['3PA']), 'tp_percent': float(row['3P%']),
                    'ftm': int(row['FTM']), 'fta': int(row['FTA']), 'ft_percent': float(row['FT%']),
                    'oreb': int(row['OREB']), 'dreb': int(row['DREB']), 'reb': int(row['REB']),
                    'ast': int(row['AST']), 'tov': int(row['TOV']), 'stl': int(row['STL']),
                    'blk': int(row['BLK']), 'pf': int(row['PF'])
                })
            return {**info, 'players': players}
        except Exception as e:
            print(f"Error processing CSV: {e}")
            return None
