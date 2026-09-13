import pandas as pd
import os, re
from io import StringIO
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
    def _normalize_opponent(name):
        """Normalize opponent name: strip, collapse internal whitespace, remove non-printable chars."""
        if not name:
            return "Unknown"
        name = name.strip()
        name = re.sub(r'\s+', ' ', name)
        name = ''.join(c for c in name if c.isprintable())
        return name

    @staticmethod
    def parse_filename(filename):
        # Try standard pattern first
        match = re.match(Config.FILENAME_PATTERN, os.path.splitext(filename)[0])
        if match:
            opp, t_score, o_score, d, m, y, type_code = match.groups()
            return {
                'opponent': CSVProcessor._normalize_opponent(opp),
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
                'opponent': CSVProcessor._normalize_opponent(opp),
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
                'opponent': CSVProcessor._normalize_opponent(opp),
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
                'opponent': CSVProcessor._normalize_opponent(opp),
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
                'opponent': CSVProcessor._normalize_opponent(opp),
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
    def frame_to_players(df):
        """Convert a normalized DataFrame to the legacy player-dict list.

        Shared by process_game() and the import-wizard commit path so both
        produce identical PlayerStat payloads. Skips the 'Total' row.
        """
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
        return players

    @staticmethod
    def mapped_frame(content_text, column_mapping=None):
        """Read CSV text into a normalized DataFrame.

        Applies the user's column mapping then legacy aliases. Raises
        ValueError on empty/unparseable content so callers can return 400.
        """
        from core.validators import OPTIONAL_CSV_COLUMNS, REQUIRED_CSV_COLUMNS

        text = content_text if isinstance(content_text, str) else ""
        if not text.strip():
            raise ValueError("Empty file: no CSV content found.")
        try:
            df = pd.read_csv(StringIO(text))
        except Exception as e:
            raise ValueError(f"Could not parse CSV: {e}")
        try:
            df = df.dropna(how='all')
        except Exception:
            pass
        df.columns = [str(c).strip() for c in df.columns]
        if len(df.columns) == 0:
            raise ValueError("Could not parse CSV: no columns detected.")
        allowed_targets = set(REQUIRED_CSV_COLUMNS) | set(OPTIONAL_CSV_COLUMNS)
        rename = {}
        for src, dst in (column_mapping or {}).items():
            if src not in df.columns or dst not in allowed_targets:
                continue
            if dst != src and (dst in df.columns or dst in rename.values()):
                raise ValueError(
                    f"Cannot map '{src}' to '{dst}': "
                    "target column already present."
                )
            rename[src] = dst
        if rename:
            df = df.rename(columns=rename)
        return CSVProcessor.normalize_columns(df)

    @staticmethod
    def build_preview(content_text, filename, column_mapping=None,
                      date_override=None, max_rows=50):
        """Preview-first validation for the import wizard (CSV).

        Never raises: malformed input yields {"valid": False, ...} with a
        ``fatal`` message so routes can return 400 instead of 500.
        ``column_mapping`` maps an uploaded header -> canonical header
        (e.g. {"Punti": "PTS"}); ``date_override`` is a free-form date
        string fixed up in-UI without re-uploading.
        """
        from core.validators import (
            FLOAT_CSV_COLUMNS, INT_CSV_COLUMNS, OPTIONAL_CSV_COLUMNS,
            REQUIRED_CSV_COLUMNS, is_valid_minutes, parse_import_date,
        )

        result = {
            'filename': filename,
            'game_info': None,
            'filename_error': None,
            'columns_found': [],
            'columns_missing': [],
            'row_errors': [],
            'rows': [],
            'total_rows': 0,
            'valid': False,
        }

        text = content_text if isinstance(content_text, str) else ""
        if not text.strip():
            result['fatal'] = "Empty file: no CSV content found."
            return result

        try:
            df = CSVProcessor.mapped_frame(text, column_mapping)
        except ValueError as e:
            result['fatal'] = str(e)
            return result

        if df.empty and len(df.columns) == 0:
            result['fatal'] = "Could not parse CSV: no columns detected."
            return result

        result['columns_found'] = list(df.columns)
        missing = [c for c in REQUIRED_CSV_COLUMNS if c not in df.columns]
        result['columns_missing'] = missing

        # Game info from the legacy filename convention; date override wins.
        info = CSVProcessor.parse_filename(filename or "")
        if info is None:
            result['filename_error'] = (
                "Filename does not match "
                "Opponent_TeamScore-OppScore_DD-MM-YYYY_[F/S/P].csv"
            )
        if date_override:
            display, sort_date = parse_import_date(date_override)
            if display is None:
                result['row_errors'].append({
                    'row': None, 'column': 'date_override',
                    'message': (
                        "Unrecognized date. Use DD-MM-YYYY, DD/MM/YYYY "
                        "or YYYY-MM-DD."
                    ),
                    'value': date_override,
                })
            elif info is not None:
                info = {**info, 'date': display, 'sort_date': sort_date}
            else:
                # Date fixed but filename still unusable: keep the error.
                pass
        result['game_info'] = info

        # Per-row validation (skip the legacy 'Total' row, report the rest).
        rows_out = []
        data_rows = 0
        for idx, (_, row) in enumerate(df.iterrows()):
            raw = {c: (None if pd.isna(v) else v) for c, v in row.items()}
            # JSON-safe primitives.
            clean = {}
            for c, v in raw.items():
                if v is None:
                    clean[c] = None
                elif isinstance(v, (int, float, str, bool)):
                    clean[c] = v
                else:
                    clean[c] = str(v)
            rows_out.append(clean)

            name_val = row.get('Name', row.get('name', row.get('Player', '')))
            name_text = '' if pd.isna(name_val) else str(name_val).strip()
            if name_text.lower() == 'total':
                continue
            data_rows += 1
            if not name_text:
                result['row_errors'].append({
                    'row': idx, 'column': 'Name',
                    'message': 'Missing player name.', 'value': clean.get('Name'),
                })

            for col in INT_CSV_COLUMNS:
                if col not in df.columns:
                    continue
                val = row.get(col)
                if pd.isna(val) or (isinstance(val, str) and not val.strip()):
                    continue  # blanks default to 0 at import, like legacy
                try:
                    if isinstance(val, float) and not float(val).is_integer():
                        raise ValueError
                    int(val)
                except (ValueError, TypeError):
                    result['row_errors'].append({
                        'row': idx, 'column': col,
                        'message': f"Not a whole number: {val!r}.",
                        'value': clean.get(col),
                    })
            for col in FLOAT_CSV_COLUMNS:
                if col not in df.columns:
                    continue
                val = row.get(col)
                if pd.isna(val) or (isinstance(val, str) and not val.strip()):
                    continue
                try:
                    float(val)
                except (ValueError, TypeError):
                    result['row_errors'].append({
                        'row': idx, 'column': col,
                        'message': f"Not a number: {val!r}.",
                        'value': clean.get(col),
                    })
            min_val = row.get('MIN') if 'MIN' in df.columns else None
            min_blank = (min_val is None or pd.isna(min_val)
                         or (isinstance(min_val, str) and not min_val.strip()))
            if 'MIN' in df.columns and not min_blank \
                    and not is_valid_minutes(min_val):
                result['row_errors'].append({
                    'row': idx, 'column': 'MIN',
                    'message': 'Bad minutes format. Use MM:SS or minutes.',
                    'value': clean.get('MIN'),
                })

        result['rows'] = rows_out[:max_rows]
        result['total_rows'] = len(rows_out)
        result['player_rows'] = data_rows
        if data_rows == 0:
            result['row_errors'].append({
                'row': None, 'column': None,
                'message': 'No player rows found (only a Total row or empty).',
                'value': None,
            })

        result['valid'] = (
            info is not None
            and not missing
            and not result['row_errors']
            and data_rows > 0
        )
        return result

    @staticmethod
    def process_game(filepath, info):
        # Legacy direct-import path (filename convention). Unchanged behavior:
        # lenient coercion, Total row skipped, None on unreadable file.
        try:
            df = pd.read_csv(filepath)

            # Normalize column names for legacy format compatibility
            df = CSVProcessor.normalize_columns(df)

            players = CSVProcessor.frame_to_players(df)
            return {**info, 'players': players}
        except Exception as e:
            print(f"Error processing CSV: {e}")
            return None
