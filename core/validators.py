from datetime import datetime


class DataValidator:
    @staticmethod
    def validate_player_stats(stats):
        required = ['name', 'points', 'minutes']
        for field in required:
            if field not in stats:
                raise ValueError(f"Missing field: {field}")
        return stats


# --- Import-wizard helpers (CSV preview / inline fix) -----------------------
REQUIRED_CSV_COLUMNS = [
    "Name", "MIN", "PTS", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%",
    "FTM", "FTA", "FT%", "OREB", "DREB", "REB", "AST", "TOV", "STL",
    "BLK", "PF",
]

OPTIONAL_CSV_COLUMNS = {"PlusMinus", "REB_CONCEDED"}

INT_CSV_COLUMNS = {
    "PTS", "FGM", "FGA", "3PM", "3PA", "FTM", "FTA", "OREB", "DREB",
    "REB", "AST", "TOV", "STL", "BLK", "PF", "PlusMinus", "REB_CONCEDED",
}

FLOAT_CSV_COLUMNS = {"FG%", "3P%", "FT%"}

# Accepted date inputs for the wizard date-override fix. The legacy
# filename convention is DD-MM-YYYY; users commonly paste DD/MM/YYYY or
# ISO YYYY-MM-DD, so accept all three (plus 2-digit years).
DATE_INPUT_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d")


def parse_import_date(raw):
    """Parse a user-supplied date override.

    Returns (date_display, sort_date) with display as DD/MM/YYYY and sort
    as YYYY-MM-DD, or (None, None) when unparseable. Never raises.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    # Normalize separators then try known formats.
    for fmt in DATE_INPUT_FORMATS:
        try:
            dt = datetime.strptime(text, fmt)
            if dt.year < 100:
                dt = dt.replace(year=2000 + dt.year)
            return dt.strftime("%d/%m/%Y"), dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: zero-padded single-digit day/month like 5/3/2025.
    try:
        parts = text.replace("-", "/").split("/")
        if len(parts) == 3:
            if len(parts[0]) == 4:  # YYYY/M/D
                y, m, d = (int(p) for p in parts)
            else:  # D/M/YYYY
                d, m, y = (int(p) for p in parts)
            if y < 100:
                y += 2000
            dt = datetime(y, m, d)
            return dt.strftime("%d/%m/%Y"), dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        pass
    return None, None


def is_valid_minutes(value):
    """Loose check: MM:SS, M:SS, or plain decimal minutes."""
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    if ":" in text:
        parts = text.split(":")
        if len(parts) != 2:
            return False
        try:
            minutes = int(parts[0])
            seconds = int(parts[1])
        except ValueError:
            return False
        return minutes >= 0 and 0 <= seconds < 60
    try:
        return float(text) >= 0
    except ValueError:
        return False
