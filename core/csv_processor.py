import pandas as pd
import os, re
from config import Config

class CSVProcessor:
    # Column name mappings for legacy format compatibility
    COLUMN_MAPPINGS = {
        # Player name variations
        'player': 'Name',
        'player_name': 'Name',
        'players': 'Name',
        
        # Minutes variations
        'min': 'MIN',
        'minutes': 'MIN',
        'mp': 'MIN',
        
        # Points variations
        'pts': 'PTS',
        'points': 'PTS',
        'pt': 'PTS',
        
        # Field goal variations
        'fgm': 'FGM',
        'fg': 'FGM',
        'fga': 'FGA',
        'fg%': 'FG%',
        'fg_pct': 'FG%',
        'fg_percent': 'FG%',
        
        # Three point variations
        '3pm': '3PM',
        '3p': '3PM',
        '3pa': '3PA',
        '3p%': '3P%',
        '3p_pct': '3P%',
        '3p_percent': '3P%',
        'tpm': '3PM',
        'tpa': '3PA',
        'tp%': '3P%',
        
        # Free throw variations
        'ftm': 'FTM',
        'ft': 'FTM',
        'fta': 'FTA',
        'ft%': 'FT%',
        'ft_pct': 'FT%',
        'ft_percent': 'FT%',
        
        # Rebound variations
        'oreb': 'OREB',
        'orb': 'OREB',
        'dreb': 'DREB',
        'drb': 'DREB',
        'reb': 'REB',
        'trb': 'REB',
        'total_reb': 'REB',
        'reb_conceded': 'REB_CONCEDED',
        'rebounds_conceded': 'REB_CONCEDED',
        'opp_oreb': 'REB_CONCEDED',
        'opponent_oreb': 'REB_CONCEDED',
        
        # Assist variations
        'ast': 'AST',
        'assists': 'AST',
        
        # Turnover variations
        'tov': 'TOV',
        'to': 'TOV',
        'turnovers': 'TOV',
        
        # Steal variations
        'stl': 'STL',
        'steals': 'STL',
        'st': 'STL',
        
        # Block variations
        'blk': 'BLK',
        'blocks': 'BLK',
        'bk': 'BLK',
        
        # Personal foul variations
        'pf': 'PF',
        'fouls': 'PF',
        'personal_fouls': 'PF',
        
        # Plus/minus variations
        '+/-': 'PlusMinus',
        'plus/minus': 'PlusMinus',
        'pm': 'PlusMinus',
        'plusminus': 'PlusMinus',
        'plus_minus': 'PlusMinus',
    }
    
    # Alternative filename patterns for legacy formats
    LEGACY_FILENAME_PATTERNS = [
        # Standard format: Opponent_TeamScore-OppScore_DD-MM-YYYY_Type
        r'^([^_]+)_(\d+)-(\d+)_(\d{2})-(\d{2})-(\d{4})_([FSP])$',
        # Alternative format: Opponent_TeamScore-OppScore_YYYY-MM-DD_Type
        r'^([^_]+)_(\d+)-(\d+)_(\d{4})-(\d{2})-(\d{2})_([FSP])$',
        # Legacy format: DD-MM-YYYY_Opponent_TeamScore-OppScore
        r'^(\d{2})-(\d{2})-(\d{4})_([^_]+)_(\d+)-(\d+)$',
        # Simple format: Opponent_DD-MM-YYYY
        r'^([^_]+)_(\d{2})-(\d{2})-(\d{4})$',
        # Format with score in parentheses: Opponent_(TeamScore-OppScore)_DD-MM-YYYY
        r'^([^(]+)\((\d+)-(\d+)\)_(\d{2})-(\d{2})-(\d{4})$',
    ]

    @staticmethod
    def parse_filename(filename):
        # Try standard pattern first
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
        
        # Try legacy patterns
        base_name = os.path.splitext(filename)[0]
        
        # Pattern: Opponent_TeamScore-OppScore_YYYY-MM-DD_Type (ISO date format)
        pattern = r'^([^_]+)_(\d+)-(\d+)_(\d{4})-(\d{2})-(\d{2})_([FSP])$'
        match = re.match(pattern, base_name)
        if match:
            opp, t_score, o_score, y, m, d, type_code = match.groups()
            return {
                'opponent': opp,
                'team_score': int(t_score),
                'opponent_score': int(o_score),
                'date': f"{d}/{m}",
                'sort_date': f"{y}-{m}-{d}",
                'game_type': Config.GAME_TYPE_MAP.get(type_code, 'Unknown'),
                'result': 'W' if int(t_score) > int(o_score) else 'L'
            }
        
        # Pattern: DD-MM-YYYY_Opponent_TeamScore-OppScore
        pattern = r'^(\d{2})-(\d{2})-(\d{4})_([^_]+)_(\d+)-(\d+)$'
        match = re.match(pattern, base_name)
        if match:
            d, m, y, opp, t_score, o_score = match.groups()
            return {
                'opponent': opp,
                'team_score': int(t_score),
                'opponent_score': int(o_score),
                'date': f"{d}/{m}",
                'sort_date': f"{y}-{m}-{d}",
                'game_type': 'Season',  # Default
                'result': 'W' if int(t_score) > int(o_score) else 'L'
            }
        
        # Pattern: Opponent_(TeamScore-OppScore)_DD-MM-YYYY
        pattern = r'^([^(]+)\((\d+)-(\d+)\)_(\d{2})-(\d{2})-(\d{4})$'
        match = re.match(pattern, base_name)
        if match:
            opp, t_score, o_score, d, m, y = match.groups()
            return {
                'opponent': opp.strip(),
                'team_score': int(t_score),
                'opponent_score': int(o_score),
                'date': f"{d}/{m}",
                'sort_date': f"{y}-{m}-{d}",
                'game_type': 'Season',  # Default
                'result': 'W' if int(t_score) > int(o_score) else 'L'
            }
        
        # Pattern: Opponent_DD-MM-YYYY (no score in filename)
        pattern = r'^([^_]+)_(\d{2})-(\d{2})-(\d{4})$'
        match = re.match(pattern, base_name)
        if match:
            opp, d, m, y = match.groups()
            return {
                'opponent': opp,
                'team_score': 0,  # Will need to be calculated from player stats
                'opponent_score': 0,  # Will need to be provided separately
                'date': f"{d}/{m}",
                'sort_date': f"{y}-{m}-{d}",
                'game_type': 'Season',
                'result': 'W'  # Default, should be overridden
            }
        
        return None

    @staticmethod
    def normalize_columns(df):
        """Normalize column names to standard format."""
        # Strip whitespace from column names
        df.columns = [c.strip() for c in df.columns]
        
        # Create a mapping for current columns
        new_columns = {}
        for col in df.columns:
            col_lower = col.lower().replace(' ', '_').replace('-', '_')
            # Check direct mapping
            if col in CSVProcessor.COLUMN_MAPPINGS:
                new_columns[col] = CSVProcessor.COLUMN_MAPPINGS[col]
            # Check lowercase mapping
            elif col_lower in CSVProcessor.COLUMN_MAPPINGS:
                new_columns[col] = CSVProcessor.COLUMN_MAPPINGS[col_lower]
            # Check if column is already in standard format
            elif col in ['Name', 'MIN', 'PTS', 'FGM', 'FGA', 'FG%', '3PM', '3PA', '3P%', 
                        'FTM', 'FTA', 'FT%', 'OREB', 'DREB', 'REB', 'AST', 'TOV', 'STL', 'BLK', 'PF', 'REB_CONCEDED']:
                continue  # Already standard
            else:
                # Keep original if no mapping found
                continue
        
        # Rename columns
        if new_columns:
            df = df.rename(columns=new_columns)
        
        return df

    @staticmethod
    def process_game(filepath, info):
        try:
            df = pd.read_csv(filepath)
            
            # Normalize column names for legacy format compatibility
            df = CSVProcessor.normalize_columns(df)
            
            # Handle PlusMinus column separately (it has multiple possible names)
            pm_col = None
            for col in ['PlusMinus', '+/-', 'Plus/Minus', 'PM', 'PLUS_MINUS']:
                if col in df.columns:
                    pm_col = col
                    break
            
            players = []
            for _, row in df.iterrows():
                # Skip total row
                name_val = row.get('Name', row.get('name', row.get('Player', '')))
                if pd.isna(name_val) or str(name_val).lower() == 'total':
                    continue
                
                # Safe integer conversion for +/-
                pm_val = 0
                if pm_col and pd.notna(row.get(pm_col)):
                    try:
                        pm_val = int(row[pm_col])
                    except:
                        pm_val = 0

                # Helper function to safely get numeric value
                def safe_int(row, key, default=0):
                    val = row.get(key, default)
                    if pd.isna(val):
                        return default
                    try:
                        return int(val)
                    except:
                        return default
                
                def safe_float(row, key, default=0.0):
                    val = row.get(key, default)
                    if pd.isna(val):
                        return default
                    try:
                        return float(val)
                    except:
                        return default

                players.append({
                    'name': name_val,
                    'minutes': row.get('MIN', row.get('minutes', '0')),
                    'points': safe_int(row, 'PTS'),
                    'fgm': safe_int(row, 'FGM'), 
                    'fga': safe_int(row, 'FGA'), 
                    'fg_percent': safe_float(row, 'FG%'),
                    'tpm': safe_int(row, '3PM'), 
                    'tpa': safe_int(row, '3PA'), 
                    'tp_percent': safe_float(row, '3P%'),
                    'ftm': safe_int(row, 'FTM'), 
                    'fta': safe_int(row, 'FTA'), 
                    'ft_percent': safe_float(row, 'FT%'),
                    'oreb': safe_int(row, 'OREB'), 
                    'dreb': safe_int(row, 'DREB'), 
                    'reb': safe_int(row, 'REB'),
                    'ast': safe_int(row, 'AST'), 
                    'tov': safe_int(row, 'TOV'), 
                    'stl': safe_int(row, 'STL'),
                    'blk': safe_int(row, 'BLK'), 
                    'pf': safe_int(row, 'PF'),
                    'plus_minus': pm_val,
                    'reb_conceded': safe_int(row, 'REB_CONCEDED'),
                })
            return {**info, 'players': players}
        except Exception as e:
            print(f"Error processing CSV: {e}")
            return None
