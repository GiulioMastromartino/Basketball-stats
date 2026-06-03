import pdfplumber
import re
from datetime import datetime


def _safe_int(val, default=0):
    try:
        return int(val)
    except Exception:
        return default


def _safe_float_pct(val, default=0.0):
    try:
        return float(str(val).replace("%", ""))
    except Exception:
        return default


def parse_game_pdf(pdf_path):
    """Parse a basketball box-score PDF into the internal game_data format."""

    game_data = {
        "date": "",
        "opponent": "Unknown",
        "result": "W",
        "team_score": 0,
        "opponent_score": 0,
        "game_type": "Season",
        "players": [],
        "sort_date": "",
    }

    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]

        # --- Header parsing (best effort) ---
        text = first_page.extract_text() or ""

        header_regex = re.search(r"(\d{1,2}/\d{1,2})\s*-\s*(.+)", text)
        if header_regex:
            date_str = header_regex.group(1)
            opponent = header_regex.group(2).strip()

            # Attempt to guess year if not present
            now = datetime.now()
            day, month = map(int, date_str.split("/"))
            year_match = re.search(r"20\d{2}", text)
            if year_match:
                year = int(year_match.group(0))
            else:
                # Simple heuristic: if the PDF month is in the future relative to now, assume previous year
                year = now.year
                if month > now.month + 1:
                    year = now.year - 1

            game_data["date"] = f"{day:02d}/{month:02d}/{year:04d}"
            game_data["sort_date"] = f"{year:04d}-{month:02d}-{day:02d}"
            game_data["opponent"] = opponent

        score_regex = re.search(
            r"(win|lose)\s*\[\s*(\d+)\s*-\s*(\d+)\s*\]", text, re.IGNORECASE
        )
        if score_regex:
            result_text = score_regex.group(1).lower()
            s1 = _safe_int(score_regex.group(2), 0)
            s2 = _safe_int(score_regex.group(3), 0)
            game_data["team_score"] = s1
            game_data["opponent_score"] = s2
            game_data["result"] = "W" if "win" in result_text else "L"

        # --- Player stats parsing ---
        # Prefer table extraction (more robust than text lines)
        try:
            table = first_page.extract_table()
        except Exception:
            table = None

        def parse_row_cells(row):
            # Expected columns:
            # Name, MIN, PTS, FGM, FGA, FG%, 3PM, 3PA, 3P%, FTM, FTA, FT%, OREB, DREB, REB, AST, TOV, STL, BLK, PF
            # Optional 21st column: +/-
            if not row:
                return None

            # remove None and trim
            row = [c.strip() if isinstance(c, str) else c for c in row]
            row = [c for c in row if c not in (None, "")]
            if not row:
                return None

            if str(row[0]).strip().lower() in {"name", "total"}:
                return None

            if len(row) < 20:
                return None

            try:
                p_data = {
                    "name": str(row[0]).strip(),
                    "minutes": str(row[1]).strip(),
                    "points": _safe_int(row[2]),
                    "fgm": _safe_int(row[3]),
                    "fga": _safe_int(row[4]),
                    "fg_percent": _safe_float_pct(row[5]),
                    "tpm": _safe_int(row[6]),
                    "tpa": _safe_int(row[7]),
                    "tp_percent": _safe_float_pct(row[8]),
                    "ftm": _safe_int(row[9]),
                    "fta": _safe_int(row[10]),
                    "ft_percent": _safe_float_pct(row[11]),
                    "oreb": _safe_int(row[12]),
                    "dreb": _safe_int(row[13]),
                    "reb": _safe_int(row[14]),
                    "ast": _safe_int(row[15]),
                    "tov": _safe_int(row[16]),
                    "stl": _safe_int(row[17]),
                    "blk": _safe_int(row[18]),
                    "pf": _safe_int(row[19]),
                    "plus_minus": 0
                }
                
                # Check for +/- column (index 20)
                if len(row) > 20:
                    p_data["plus_minus"] = _safe_int(row[20])
                    
                return p_data
            except Exception:
                return None

        players = []
        if table:
            for row in table:
                parsed = parse_row_cells(row)
                if parsed:
                    players.append(parsed)

        # Fallback: line parsing (best effort)
        # NOTE: Fallback assumes standard 20 columns. Does not support +/- to avoid breaking legacy files.
        if not players:
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            for line in lines:
                if "Name" in line or line.startswith("Total"):
                    continue

                parts = line.split()
                if len(parts) < 20:
                    continue
                if not parts[-1].isdigit():
                    continue

                try:
                    pf = int(parts[-1])
                    blk = int(parts[-2])
                    stl = int(parts[-3])
                    tov = int(parts[-4])
                    ast = int(parts[-5])
                    reb = int(parts[-6])
                    dreb = int(parts[-7])
                    oreb = int(parts[-8])

                    ft_pct = _safe_float_pct(parts[-9])
                    fta = _safe_int(parts[-10])
                    ftm = _safe_int(parts[-11])

                    tp_pct = _safe_float_pct(parts[-12])
                    tpa = _safe_int(parts[-13])
                    tpm = _safe_int(parts[-14])

                    fg_pct = _safe_float_pct(parts[-15])
                    fga = _safe_int(parts[-16])
                    fgm = _safe_int(parts[-17])

                    pts = _safe_int(parts[-18])
                    minutes = parts[-19]
                    name = " ".join(parts[:-19]).strip()
                    if not name:
                        continue

                    players.append(
                        {
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
                            "pf": pf,
                            "plus_minus": 0 # Default for fallback text parsing
                        }
                    )
                except Exception:
                    continue

        game_data["players"] = players

    return game_data
