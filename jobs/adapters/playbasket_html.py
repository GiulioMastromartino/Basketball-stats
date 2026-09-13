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
import urllib.request

USER_AGENT = {"User-Agent": "BasketballStats/1.0 (+championship-tracker)"}

# Currently only DR4 is mapped; anything else is rejected before saving.
SUPPORTED_CHAMPIONSHIPS = {"DR4"}

# Girone letter -> Playbasket lg id (extend as new gironi are mapped).
GIRONE_IDS = {"M": "13"}


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


def parse_calendar(html: str) -> list[dict]:
    """Extract scored games from calendar/classifica tables."""
    games: list[dict] = []
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, flags=re.S)
    round_no = 0
    for table in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, flags=re.S)
        scored = [r for r in rows if re.search(
            r"<t[dh][^>]*>\s*\d{2}/\d{2}\s*</t[dh]>", r)]
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


def fetch_championship(region: str = "lombardia", province: str = "MI",
                       championship: str = "DR4", season: str = "2026",
                       girone: str = "M", mod: str = "cl"
                       ) -> tuple[list[dict], list[dict], str]:
    """Fetch (games, standings, fingerprint) for a Playbasket girone."""
    girone_id = GIRONE_IDS.get((girone or "").strip().upper(),
                               (girone or "").strip())
    if not girone_id.isdigit():
        raise ValueError(
            f"Unmapped Playbasket girone {girone!r} "
            f"(mapped: {sorted(GIRONE_IDS)})")
    html = _fetch(league_url(region, province, championship, season, mod,
                             girone_id))
    games = parse_calendar(html)
    standings_html = html if mod == "st" else _fetch(
        league_url(region, province, championship, season, "st",
                   girone_id))
    return games, parse_standings(standings_html), page_fingerprint(html)
