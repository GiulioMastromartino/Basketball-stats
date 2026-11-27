#!/usr/bin/env python3
"""Adapter for FIP's backend JSON API (``backend.fip.it/api/v1/risultati``).

Covers national championships and regional ones with digital coverage.
Backend codes are the official FIP ones (see the ``campionato`` select on
``fip.it/risultati``): Serie C is ``C1``, DR1 is ``D``, DR2 is ``PM``,
DR3 is ``1DM`` — *not* ``DR1/DR2/DR3``. Regional gironi are numeric ids
(e.g. ``85405`` = DR3 Milano Girone H); :func:`discover_gironi` scrapes
the id→label mapping from the public risultati page so dropdowns never
rely on guessed codes. Returns game dicts compatible with
``core.external_store.upsert_game``.
"""

import html as html_module
import json
import re
import time
import urllib.parse
import urllib.request

BASE = "https://backend.fip.it/api/v1/risultati"
RISULTATI_PAGE = "https://fip.it/risultati/"
USER_AGENT = {"User-Agent": "BasketballStats/1.0 (+championship-tracker)"}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
MAX_GIORNATE = 30
EMPTY_LIMIT = 2


def _get(params: dict) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def discover_gironi(comitato: str, campionato: str, fase: str = "1",
                     sesso: str = "M", regione: str = "LO") -> list[dict]:
    """Scrape the official id→label girone mapping from fip.it/risultati.

    The risultati page is server-rendered: requesting it with
    comitato/campionato pre-selected embeds the exact ``gironi`` select
    for that league (e.g. DR3/1DM Milano → G=85404, H=85405, I=85406).
    ``regione`` selects the regional group; the dashboard only calls this
    for Lombardy committees (``RLO/PBG/PBS/PVA``), whose region code is
    ``LO``.
    Returns ``[{"code": "85405", "label": "Girone H"}]`` (empty when the
    league has no gironi select). Raises ``RuntimeError`` on fetch failure.
    """
    params = {
        "group": "campionati-regionali",
        "regione_codice": regione,
        "comitato_codice": comitato,
        "sesso": sesso,
        "codice_campionato": campionato,
        "codice_fase": fase,
    }
    url = RISULTATI_PAGE + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=BROWSER_UA)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
    except Exception as exc:
        raise RuntimeError(f"FIP gironi page fetch failed: {exc}") from exc
    match = re.search(
        r'<select[^>]*name=["\']gironi["\'][^>]*>(.*?)</select>',
        html, flags=re.S)
    if not match:
        return []
    options = []
    for value, label in re.findall(
            r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>',
            match.group(1), flags=re.S):
        code = (value or "").strip()
        text = " ".join(html_module.unescape(
            re.sub(r"<[^>]+>", " ", label)).split())
        if code and code.isdigit():
            options.append({"code": code, "label": text or f"Girone {code}"})
    return options


def fetch_games(comitato: str, campionato: str, fase: str = "1",
                girone: str = "", sesso: str = "M",
                sleep: float = 0.3) -> list[dict]:
    """Fetch all rounds (andata + ritorno) for one girone."""
    games: list[dict] = []
    for code_ar, turno in (("1", "Andata"), ("0", "Ritorno")):
        giornata = 1
        empty_streak = 0
        while giornata <= MAX_GIORNATE and empty_streak < EMPTY_LIMIT:
            try:
                payload = _get({
                    "comitato_codice": comitato,
                    "sesso": sesso,
                    "codice_campionato": campionato,
                    "codice_fase": fase,
                    "codice_girone": girone,
                    "codice_ar": code_ar,
                    "giornata": giornata,
                })
            except Exception as exc:
                raise RuntimeError(
                    f"FIP API fetch failed at {turno} {giornata}: {exc}"
                ) from exc
            partite = payload.get("partite", []) if payload else []
            if not partite:
                empty_streak += 1
                giornata += 1
                continue
            empty_streak = 0
            for match in partite:
                games.append({
                    "game_number": match.get("numero_gara", ""),
                    "round": f"{turno} {giornata}",
                    "date": match.get("data_partita", ""),
                    "time": match.get("ora_partita", ""),
                    "status": match.get("stato_gara", ""),
                    "home": match.get("casa", ""),
                    "away": match.get("ospite", ""),
                    "home_score": match.get("punti_casa_uff", -1),
                    "away_score": match.get("punti_ospite_uff", -1),
                    "venue": match.get("campo_gioco", ""),
                    "city": match.get("citta_campo_gioco", ""),
                })
            giornata += 1
            if sleep:
                time.sleep(sleep)
    return games
