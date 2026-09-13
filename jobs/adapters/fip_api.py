#!/usr/bin/env python3
"""Adapter for FIP's backend JSON API (``backend.fip.it/api/v1/risultati``).

Covers national championships and regional ones with digital coverage
(Serie A/B, DR1/DR2, youth Eccellenza). Returns game dicts compatible with
``core.external_store.upsert_game``.
"""

import json
import time
import urllib.parse
import urllib.request

BASE = "https://backend.fip.it/api/v1/risultati"
USER_AGENT = {"User-Agent": "BasketballStats/1.0 (+championship-tracker)"}
MAX_GIORNATE = 30
EMPTY_LIMIT = 2


def _get(params: dict) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def fetch_games(comitato: str, campionato: str, fase: str = "1",
                girone: str = "", sesso: str = "M",
                sleep: float = 0.3) -> list[dict]:
    """Fetch all rounds (andata + ritorno) for one girone."""
    games: list[dict] = []
    first_error: Exception | None = None
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
                # Don't silently record a partial sweep as success: remember
                # the failure; the caller decides (empty result -> raise).
                if first_error is None:
                    first_error = exc
                break
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
    if not games and first_error is not None:
        raise RuntimeError(f"FIP API fetch failed: {first_error}")
    return games
