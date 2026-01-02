import pdfplumber
import re
from datetime import datetime

def parse_game_pdf(pdf_path):
    """
    Parses the basketball box score PDF.
    Returns a dict compatible with the app's Game model structure.
    """
    game_data = {
        "date": None,
        "opponent": "Unknown",
        "result": "W",
        "team_score": 0,
        "opponent_score": 0,
        "game_type": "Season", # Default, user might need to adjust or filename fallback
        "players": [],
        "sort_date": None
    }

    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]
        text = first_page.extract_text()
        
        # --- 1. Header Parsing ---
        # Example: "14/12 - Cesano Boscone"
        # We need to guess the year. We'll try to find a year in the text or default to current season logic.
        # For now, let's assume the current academic/sport year logic (e.g. if month > 8, year=current_year, else year=next_year)
        # But simple approach: use current year or allow override.
        
        lines = text.split('\n')
        
        # Find Date and Opponent line (usually top)
        header_regex = re.search(r"(\d{1,2}/\d{1,2})\s*-\s*(.+)", text)
        if header_regex:
            date_str = header_regex.group(1)
            opponent = header_regex.group(2).strip()
            
            # Date logic: Append current year approximation
            now = datetime.now()
            day, month = map(int, date_str.split('/'))
            
            # If month is Sept-Dec, it's late in the year. If Jan-July, it's early.
            # We'll use a simple heuristic based on current date to guess the year
            # Or just use the current year if not sure.
            # Better: Look for a year in the text.
            year_match = re.search(r"20\d{2}", text)
            if year_match:
                year = int(year_match.group(0))
            else:
                # Fallback: if today is 2026, and date is 14/12, it's likely 2025.
                # If date is 02/01, it's likely 2026.
                if month > 8: 
                    year = now.year - 1 if now.month < 8 else now.year
                else:
                    year = now.year if now.month < 8 else now.year + 1
            
            full_date_str = f"{day:02d}/{month:02d}/{year}"
            game_data["date"] = full_date_str
            game_data["sort_date"] = f"{year}-{month:02d}-{day:02d}"
            game_data["opponent"] = opponent

        # Find Score line: "win [67 - 54]" or "lose [54 - 67]"
        score_regex = re.search(r"(win|lose)\s*\[\s*(\d+)\s*-\s*(\d+)\s*\]", text, re.IGNORECASE)
        if score_regex:
            result_text = score_regex.group(1).lower()
            s1 = int(score_regex.group(2))
            s2 = int(score_regex.group(3))
            
            # "win [67 - 54]" -> Team=67, Opp=54
            # "lose [54 - 67]" -> Team=54, Opp=67 (usually score is presented Team - Opp)
            
            game_data["team_score"] = s1
            game_data["opponent_score"] = s2
            game_data["result"] = 'W' if 'win' in result_text else 'L'

        # --- 2. Player Stats Parsing ---
        # Columns (20 total): 
        # Name, MIN, PTS, FGM, FGA, FG%, 3PM, 3PA, 3P%, FTM, FTA, FT%, OREB, DREB, REB, AST, TOV, STL, BLK, PF
        
        for line in lines:
            line = line.strip()
            # Skip headers/footers
            if "Name" in line or "Total" in line:
                continue
            if not line:
                continue

            # Attempt to split from right
            # We expect 19 numerical columns.
            # Example end of line: "... 2 100% 1 3 4 6 2 2 0 2"
            # Note: "100% 1" might be stuck together if relying on simple split, but pdfplumber extract_text usually handles space well.
            # Let's try splitting by whitespace.
            
            parts = line.split()
            
            # We need at least 20 parts (Name + 19 stats). Name can be multiple parts.
            if len(parts) < 20:
                continue
                
            # Check if the last part is a number (PF)
            if not parts[-1].isdigit():
                continue

            # Map from end
            try:
                # Extract stats from the right
                pf = int(parts[-1])
                blk = int(parts[-2])
                stl = int(parts[-3])
                tov = int(parts[-4])
                ast = int(parts[-5])
                reb = int(parts[-6])
                dreb = int(parts[-7])
                oreb = int(parts[-8])
                
                # FT% (could be "100%" or "0%")
                ft_pct_str = parts[-9]
                ft_pct = float(ft_pct_str.replace('%', ''))
                
                fta = int(parts[-10])
                ftm = int(parts[-11])
                
                # 3P%
                tp_pct_str = parts[-12]
                tp_pct = float(tp_pct_str.replace('%', ''))
                
                tpa = int(parts[-13])
                tpm = int(parts[-14])
                
                # FG%
                fg_pct_str = parts[-15]
                fg_pct = float(fg_pct_str.replace('%', ''))
                
                fga = int(parts[-16])
                fgm = int(parts[-17])
                
                pts = int(parts[-18])
                minutes = parts[-19] # String "MM:SS"
                
                # Name is everything before minutes
                name_parts = parts[:-19]
                name = " ".join(name_parts)
                
                player_stat = {
                    "name": name,
                    "minutes": minutes,
                    "points": pts,
                    "fgm": fgm,
                    "fga": fga,
                    "fg_percent": fg_pct,
                    "tpm": tpm,
                    "tpa": tpa,
                    "tp_percent": tp_pct,
                    "ftm": ftm,
                    "fta": fta,
                    "ft_percent": ft_pct,
                    "oreb": oreb,
                    "dreb": dreb,
                    "reb": reb,
                    "ast": ast,
                    "tov": tov,
                    "stl": stl,
                    "blk": blk,
                    "pf": pf
                }
                game_data["players"].append(player_stat)
                
            except (ValueError, IndexError):
                # Skip lines that don't match structure (garbage text)
                continue

    return game_data
