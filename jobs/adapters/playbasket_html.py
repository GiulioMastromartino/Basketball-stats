#!/usr/bin/env python3
"""Adapter for Playbasket provincial pages (e.g. DR4 Milano Girone M).

Playbasket exposes no JSON API for these championships, so the calendar
tables are parsed from HTML. To fail safe against layout changes, callers
should compare :func:`page_fingerprint` across runs and alert (not parse)
when it drifts unexpectedly.
"""

import hashlib
import html as html_module
import re
import urllib.parse
import urllib.request

USER_AGENT = {"User-Agent": "BasketballStats/1.0 (+championship-tracker)"}

# Regional championships covered by Playbasket provincial pages. Lombardy
# regular-season gironi are lettered; keep in sync with
# core/championship_catalog.py PLAYBASKET_CHAMPIONSHIPS.
SUPPORTED_CHAMPIONSHIPS = {"DR1", "DR2", "DR3", "DR4"}

# Fast-path girone letter -> Playbasket lg id for Milano regular seasons
# (verified live: DR4 2025/26 A=1 … N=14, DR3 2026/27 A=1 … I=9).
# Other provinces may number differently — resolve_girone_id() checks the
# live league index first and only falls back to this map.
GIRONE_IDS = {
    "A": "1", "B": "2", "C": "3", "D": "4", "E": "5", "F": "6",
    "G": "7", "H": "8", "I": "9", "J": "10", "K": "11", "L": "12",
    "M": "13", "N": "14",
}


def league_url(region: str = "lombardia", province: str = "MI",
               championship: str = "DR4", season: str = "2026",
               mod: str = "cl", girone_id: str = "13") -> str:
    if championship not in SUPPORTED_CHAMPIONSHIPS:
        raise ValueError(
            f"Unsupported Playbasket championship {championship!r} "
            f"(supported: {sorted(SUPPORTED_CHAMPIONSHIPS)})")
    return (f"https://www.playbasket.it/{region}/league.php"
            f"?lt=2&lf=M&lr=LO&lp={province}&lc={championship}"
            f"&season={season}&mod={mod}&lg={girone_id}")


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _clean(fragment: str) -> str:
    text = html_module.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return " ".join(text.split())


def page_fingerprint(html: str) -> str:
    """Stable hash of the page's table skeleton (not its scores)."""
    skeleton = re.sub(r">[^<>]+<", "><",
                      " ".join(re.findall(r"<table.*?</table>", html,
                                          flags=re.S)))
    return hashlib.sha1(skeleton.encode("utf-8")).hexdigest()


def parse_calendar(html: str, include_scheduled: bool = False) -> list[dict]:
    """Extract games from calendar/classifica tables.

    By default only scored games are returned (historical behaviour).
    With ``include_scheduled=True`` dated rows without scores are also
    returned with ``status="scheduled"`` and empty scores, so a published
    pre-season calendar shows up instead of an empty page. Scoreless rows
    can never become losses: promotion rejects them and ``_score`` maps
    them to NULL.
    """
    games: list[dict] = []
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, flags=re.S)
    round_no = 0
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S)
        # NOTE: cells are link-wrapped (<td><a>01/10</a></td>), so unwrap
        # links before looking for the date cell.
        scored = [r for r in rows if re.search(
            r"<t[dh][^>]*>\s*\d{2}/\d{2}\s*</t[dh]>",
            re.sub(r"</?a[^>]*>", "", r))]
        if not scored:
            continue
        round_no += 1
        turno = (f"Andata {round_no}" if round_no <= 11
                 else f"Ritorno {round_no - 11}")
        for row in scored:
            cells = [ _clean(c) for c in re.findall(
                r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)]
            if len(cells) >= 6 and cells[4] and cells[5]:
                games.append({
                    "game_number": "",
                    "round": turno,
                    "date": cells[0],
                    "time": "",
                    "status": "played",
                    "home": cells[1],
                    "away": cells[2],
                    "home_score": cells[4],
                    "away_score": cells[5],
                    "venue": "",
                    "city": "",
                })
            elif (include_scheduled and len(cells) >= 3
                    and cells[1] and cells[2]):
                games.append({
                    "game_number": "",
                    "round": turno,
                    "date": cells[0],
                    "time": "",
                    "status": "scheduled",
                    "home": cells[1],
                    "away": cells[2],
                    "home_score": "",
                    "away_score": "",
                    "venue": "",
                    "city": "",
                })
    return games


def parse_standings(html: str) -> list[dict]:
    """Extract the overall standings table (first table with P.ti header)."""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, flags=re.S)
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S)
        if not rows:
            continue
        header = [_clean(c) for c in re.findall(
            r"<t[dh][^>]*>(.*?)</t[dh]>", rows[0], flags=re.S)]
        if "P.ti" not in header or "Squadra" not in header:
            continue
        standings = []
        for row in rows[1:]:
            cells = [_clean(c) for c in re.findall(
                r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.S)]
            if len(cells) < 8 or not cells[1]:
                continue
            try:
                standings.append({
                    "pos": int(cells[0]), "team": cells[1],
                    "pts": int(cells[2]), "g": int(cells[4]),
                    "w": int(cells[5]), "l": int(cells[6]),
                    "pf": int(cells[9]), "ps": int(cells[10]),
                })
            except (ValueError, IndexError):
                continue
        if standings:
            return standings
    return []


def league_title(html: str) -> str:
    """Page title (e.g. 'Calendario Girone A | Est | …'). Empty when unknown."""
    match = re.search(r"<title>(.*?)</title>", html or "", flags=re.S)
    return _clean(match.group(1)) if match else ""


def resolve_girone_id(province: str = "MI", championship: str = "DR4",
                      season: str = "2026", girone: str = "M") -> str:
    """Map a girone letter to its Playbasket ``lg`` id for an exact league.

    Parses the league index (same region/province/championship/season) and
    picks the link whose text is exactly ``Girone <letter>``. Falls back to
    the static :data:`GIRONE_IDS` map (Milano regular seasons). Raises
    ``ValueError`` when the girone does not exist for that league — e.g.
    "M" for DR3 Milano, whose gironi are A–I.
    """
    letter = (girone or "").strip().upper()
    if not letter:
        raise ValueError("Empty Playbasket girone")
    if letter.isdigit():
        return letter
    if championship not in SUPPORTED_CHAMPIONSHIPS:
        raise ValueError(
            f"Unsupported Playbasket championship {championship!r} "
            f"(supported: {sorted(SUPPORTED_CHAMPIONSHIPS)})")
    try:
        index_html = _fetch(league_url("lombardia", province, championship,
                                       season, "gr",
                                       GIRONE_IDS.get(letter, "1")))
    except Exception:
        index_html = ""
    if index_html:
        links = [(href, _clean(text)) for href, text in re.findall(
            r'<a[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>',
            index_html, flags=re.S)]
        # Exact "Girone X" first, then "Girone X | Zone…" variants —
        # link texts carry geographic suffixes in some seasons.
        for exact in (True, False):
            for href, text in links:
                if exact:
                    if text != f"Girone {letter}":
                        continue
                elif not text.startswith(f"Girone {letter} |"):
                    continue
                query = urllib.parse.urlparse(html_module.unescape(href))
                params = urllib.parse.parse_qs(query.query)
                if ((params.get("lc", [""])[0].upper()
                        != championship.upper())
                        or (params.get("lp", [""])[0].upper()
                            != province.upper())
                        or (params.get("season", [""])[0] != season)):
                    continue
                lg = (params.get("lg", [""])[0] or "").strip()
                if lg.isdigit():
                    return lg
        # Index reachable but no such girone for this exact league —
        # never fall back to another league's numbering.
        raise ValueError(
            f"Girone {letter!r} does not exist for Playbasket "
            f"{championship} {province} season {season}.")
    static = GIRONE_IDS.get(letter)
    if static is not None:
        return static
    raise ValueError(
        f"Unmapped Playbasket girone {girone!r} for {championship} "
        f"{province} season {season} "
        f"(mapped: {sorted(GIRONE_IDS)})")


def fetch_championship(region: str = "lombardia", province: str = "MI",
                       championship: str = "DR4", season: str = "2026",
                       girone: str = "M", mod: str = "cl"
                       ) -> tuple[list[dict], list[dict], str]:
    """Fetch (games, standings, fingerprint) for a Playbasket girone.

    Scheduled (scoreless) fixtures are included so a published pre-season
    calendar is visible before the first results come in.
    """
    girone_id = resolve_girone_id(province, championship, season, girone)
    html = _fetch(league_url(region, province, championship, season, mod,
                             girone_id))
    games = parse_calendar(html, include_scheduled=True)
    standings_html = html if mod == "st" else _fetch(
        league_url(region, province, championship, season, "st",
                   girone_id))
    return games, parse_standings(standings_html), page_fingerprint(html)
