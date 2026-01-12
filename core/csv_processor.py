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
            
            # Normalize column names to handle variations of +/-
            df.columns = [c.strip() for c in df.columns]
            pm_col = None
            for col in ['+/-', 'Plus/Minus', 'PM', 'PlusMinus', 'PLUS_MINUS']:
                if col in df.columns:
                    pm_col = col
                    break
            
            players = []
            for _, row in df.iterrows():
                if row['Name'] == 'Total': continue
                
                # Safe integer conversion for +/-
                pm_val = 0
                if pm_col and pd.notna(row[pm_col]):
                    try:
                        pm_val = int(row[pm_col])
                    except:
                        pm_val = 0

                players.append({
                    'name': row['Name'],
                    'minutes': row['MIN'],
                    'points': int(row['PTS']),
                    'fgm': int(row['FGM']), 'fga': int(row['FGA']), 'fg_percent': float(row['FG%']),
                    'tpm': int(row['3PM']), 'tpa': int(row['3PA']), 'tp_percent': float(row['3P%']),
                    'ftm': int(row['FTM']), 'fta': int(row['FTA']), 'ft_percent': float(row['FT%']),
                    'oreb': int(row['OREB']), 'dreb': int(row['DREB']), 'reb': int(row['REB']),
                    'ast': int(row['AST']), 'tov': int(row['TOV']), 'stl': int(row['STL']),
                    'blk': int(row['BLK']), 'pf': int(row['PF']),
                    'plus_minus': pm_val
                })
            return {**info, 'players': players}
        except Exception as e:
            print(f"Error processing CSV: {e}")
            return None
