#!/usr/bin/env python3
"""Single source of truth for championship-tracking dropdown options.

GM dashboard tracking used to be free-text (comitato, provincia, campionato,
fase, girone, stagione typed by hand) so a typo silently produced an empty
sync. Every field below is exposed as a ``<select>`` in the dashboard and
validated server-side in ``track_championship`` — free-text can never reach
the sync job.

Providers:
- ``fip_api`` — FIP backend JSON (national + regional with digital coverage).
- ``playbasket_html`` — Playbasket provincial pages (Lombardia DR4).

Conventions:
- All codes are upper-cased and stripped before validation.
- FIP gironi are letters (regional, A-Z) or numeric (national, 1-6 digits).
- Playbasket gironi are letters A-N mapped to ``lg`` ids (verified live for
  DR4 Lombardia 2025/26: A=1 … N=14).
- Season labels are always ``YYYY/YYYY``; Playbasket year = second half.
"""

from __future__ import annotations

import re

PROVIDERS = (
    ("fip_api", "FIP API — nazionale e regionali con copertura digitale"),
    ("playbasket_html", "Playbasket — provinciali Lombardia (DR4)"),
)
PROVIDER_CODES = {code for code, _ in PROVIDERS}

# ---------------------------------------------------------------------------
# FIP API options
# ---------------------------------------------------------------------------

FIP_COMITATI: tuple[tuple[str, str], ...] = (
    ("NAZ", "NAZ — Nazionale"),
    ("RLO", "RLO — Lombardia (Milano)"),
    ("PBG", "PBG — Bergamo"),
    ("PBS", "PBS — Brescia"),
    ("PVA", "PVA — Varese"),
    ("RPI", "RPI — Piemonte"),
    ("RVE", "RVE — Veneto"),
    ("RFR", "RFR — Friuli-Venezia Giulia"),
    ("REM", "REM — Emilia-Romagna"),
    ("RTO", "RTO — Toscana"),
    ("RLI", "RLI — Liguria"),
    ("RLA", "RLA — Lazio"),
    ("RMA", "RMA — Marche"),
    ("RUM", "RUM — Umbria"),
    ("RAB", "RAB — Abruzzo"),
    ("RMO", "RMO — Molise"),
    ("RCA", "RCA — Campania"),
    ("RCL", "RCL — Calabria"),
    ("RPU", "RPU — Puglia"),
    ("RBA", "RBA — Basilicata"),
    ("RSA", "RSA — Sardegna"),
    ("RSI", "RSI — Sicilia"),
    ("RVA", "RVA — Valle d'Aosta"),
    ("RTR", "RTR — Trentino-Alto Adige"),
)
FIP_COMITATI_CODES = {c for c, _ in FIP_COMITATI}

# Official backend.fip.it ``codice_campionato`` values (see the
# ``campionato`` select on fip.it/risultati — regional codes are NOT
# "DR1/DR2/DR3": Serie C=C1, DR1=D, DR2=PM, DR3=1DM).
FIP_CAMPIONATI: tuple[tuple[str, str], ...] = (
    ("A1/M", "Serie A Maschile (A1/M)"),
    ("A1/F", "Serie A Femminile (A1/F)"),
    ("A2/M", "Serie A2 Maschile (A2/M)"),
    ("A2/F", "Serie A2 Femminile (A2/F)"),
    ("B/M", "Serie B Maschile (B/M)"),
    ("B/F", "Serie B Femminile (B/F)"),
    ("B2", "Serie B Interregionale (B2)"),
    ("C1", "Serie C Maschile (C1)"),
    ("C/F", "Serie C Femminile (C/F)"),
    ("D", "Divisione Regionale 1 (D)"),
    ("PM", "Divisione Regionale 2 (PM)"),
    ("1DM", "Divisione Regionale 3 (1DM)"),
    ("U19/E", "Under 19 Eccellenza M (U19/E)"),
    ("U19G/M", "Under 19 Gold M (U19G/M)"),
    ("U17/E", "Under 17 Eccellenza M (U17/E)"),
    ("U17G/M", "Under 17 Gold M (U17G/M)"),
    ("U15/E", "Under 15 Eccellenza M (U15/E)"),
    ("U15G/M", "Under 15 Gold M (U15G/M)"),
)
FIP_CAMPIONATI_CODES = {c for c, _ in FIP_CAMPIONATI}

FIP_FASI: tuple[tuple[str, str], ...] = (
    ("1", "Fase 1 — qualificazione / regular season"),
    ("2", "Fase 2 — seconda fase"),
    ("3", "Fase 3 — playoff / orologio"),
    ("4", "Fase 4 — playout / finali"),
)
FIP_FASI_CODES = {c for c, _ in FIP_FASI}

FIP_SESSO: tuple[tuple[str, str], ...] = (
    ("M", "Maschile (M)"),
    ("F", "Femminile (F)"),
)
FIP_SESSO_CODES = {c for c, _ in FIP_SESSO}

# Regional gironi are numeric backend ids (e.g. 85405 = DR3/1DM Milano
# Girone H — offered via the dashboard's live girone lookup, never as
# free text); national gironi are numeric too (e.g. 85160 for Serie A).
# Single letters (A-Z) stay valid for back-compat.
FIP_GIRONI_LETTERS: tuple[str, ...] = tuple(
    chr(c) for c in range(ord("A"), ord("Z") + 1)
)
FIP_GIRONI_KNOWN_NUMERIC: tuple[str, ...] = ("85160", "85404", "85405",
                                             "85406")
_FIP_GIRONE_RE = re.compile(r"^(?:[A-Z]|[0-9]{1,6})$")

# ---------------------------------------------------------------------------
# Playbasket options (provincial pages, currently Lombardia DR4)
# ---------------------------------------------------------------------------

PLAYBASKET_REGIONS: tuple[tuple[str, str], ...] = (
    ("lombardia", "Lombardia"),
)
PLAYBASKET_REGION_CODES = {c for c, _ in PLAYBASKET_REGIONS}

PLAYBASKET_PROVINCES: tuple[tuple[str, str], ...] = (
    ("MI", "MI — Milano"),
    ("MB", "MB — Monza e Brianza"),
    ("BG", "BG — Bergamo"),
    ("BS", "BS — Brescia"),
    ("CO", "CO — Como"),
    ("CR", "CR — Cremona"),
    ("LC", "LC — Lecco"),
    ("LO", "LO — Lodi"),
    ("MN", "MN — Mantova"),
    ("PV", "PV — Pavia"),
    ("SO", "SO — Sondrio"),
    ("VA", "VA — Varese"),
)
PLAYBASKET_PROVINCE_CODES = {c for c, _ in PLAYBASKET_PROVINCES}

PLAYBASKET_CHAMPIONSHIPS: tuple[tuple[str, str], ...] = (
    ("DR1", "Divisione Regionale 1 (DR1)"),
    ("DR2", "Divisione Regionale 2 (DR2)"),
    ("DR3", "Divisione Regionale 3 (DR3)"),
    ("DR4", "Divisione Regionale 4 (DR4)"),
)
PLAYBASKET_CHAMPIONSHIP_CODES = {c for c, _ in PLAYBASKET_CHAMPIONSHIPS}

# Girone letters offered in the dropdown. The Playbasket ``lg`` id is
# resolved live per (province, championship, season) by
# jobs.adapters.playbasket_html.resolve_girone_id — letters that do not
# exist for the chosen league (e.g. "M" for DR3 Milano, whose gironi are
# A–I) are rejected by Verifica, never silently mapped elsewhere.
# Static lg numbers below are the known Milano regular-season mapping.
_PLAYBASKET_STATIC_LG = {
    "A": "1", "B": "2", "C": "3", "D": "4", "E": "5", "F": "6",
    "G": "7", "H": "8", "I": "9", "J": "10", "K": "11", "L": "12",
    "M": "13", "N": "14",
}
PLAYBASKET_GIRONI: tuple[tuple[str, str, str], ...] = tuple(
    (letter, _PLAYBASKET_STATIC_LG.get(letter, ""), f"Girone {letter}")
    for letter in (chr(c) for c in range(ord("A"), ord("Z") + 1))
)
PLAYBASKET_GIRONE_CODES = {g for g, _, _ in PLAYBASKET_GIRONI}
PLAYBASKET_GIRONE_IDS = dict(_PLAYBASKET_STATIC_LG)

PLAYBASKET_FASI: tuple[tuple[str, str], ...] = (
    ("1", "Fase 1 — regular season"),
)
PLAYBASKET_FASI_CODES = {c for c, _ in PLAYBASKET_FASI}

# Comitato shown for Playbasket rows (region committee); fixed to Lombardia.
PLAYBASKET_COMITATI: tuple[tuple[str, str], ...] = (
    ("RLO", "RLO — Lombardia"),
)
PLAYBASKET_COMITATI_CODES = {c for c, _ in PLAYBASKET_COMITATI}

SEASONS: tuple[tuple[str, str], ...] = (
    ("2023/2024", "2023/2024"),
    ("2024/2025", "2024/2025"),
    ("2025/2026", "2025/2026"),
    ("2026/2027", "2026/2027"),
)
SEASON_CODES = {c for c, _ in SEASONS}
_SEASON_RE = re.compile(r"^20\d{2}/20\d{2}$")


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def season_year(season_label: str) -> str:
    """Second-half year used by Playbasket URLs (``2025/2026`` -> ``2026``)."""
    label = (season_label or "").strip()
    if "/" in label:
        return label.split("/")[-1].strip()
    return label


def catalog() -> dict:
    """Full dropdown catalog for the GM dashboard + JSON endpoint."""
    return {
        "providers": [{"code": c, "label": l} for c, l in PROVIDERS],
        "fip": {
            "comitati": [{"code": c, "label": l} for c, l in FIP_COMITATI],
            "campionati": [{"code": c, "label": l} for c, l in FIP_CAMPIONATI],
            "fasi": [{"code": c, "label": l} for c, l in FIP_FASI],
            "sesso": [{"code": c, "label": l} for c, l in FIP_SESSO],
            "gironi_letters": list(FIP_GIRONI_LETTERS),
            "gironi_numeric": list(FIP_GIRONI_KNOWN_NUMERIC),
            "seasons": [c for c, _ in SEASONS],
            "defaults": {
                "comitato": "RLO", "campionato": "1DM",
                "fase": "1", "sesso": "M", "girone": "85405",
                "season": "2026/2027",
            },
        },
        "playbasket": {
            "regions": [{"code": c, "label": l}
                        for c, l in PLAYBASKET_REGIONS],
            "provinces": [{"code": c, "label": l}
                           for c, l in PLAYBASKET_PROVINCES],
            "championships": [{"code": c, "label": l}
                              for c, l in PLAYBASKET_CHAMPIONSHIPS],
            "gironi": [{"code": g, "lg": lg, "label": l}
                        for g, lg, l in PLAYBASKET_GIRONI],
            "fasi": [{"code": c, "label": l} for c, l in PLAYBASKET_FASI],
            "comitati": [{"code": c, "label": l}
                         for c, l in PLAYBASKET_COMITATI],
            "seasons": [c for c, _ in SEASONS],
            "defaults": {
                "region": "lombardia", "comitato": "RLO",
                "province": "MI", "campionato": "DR4",
                "fase": "1", "girone": "M",
                "season": "2025/2026",
            },
        },
        "seasons": [{"code": c, "label": l} for c, l in SEASONS],
    }


def validate(provider: str, data: dict) -> tuple[bool, str | None, dict]:
    """Validate dropdown selections; returns (ok, error, normalized).

    ``data`` keys: comitato_codice, province_codice, codice_campionato,
    codice_fase, codice_girone, season_label, sesso (+ region for
    Playbasket, currently fixed to Lombardy).
    """
    provider = (provider or "").strip()
    if provider not in PROVIDER_CODES:
        return False, f"Provider sconosciuto: {provider!r}.", {}

    season = (data.get("season_label") or "").strip()
    if season not in SEASON_CODES or not _SEASON_RE.match(season):
        return False, (
            f"Stagione non valida: {season!r}. "
            f"Scegli dal menu: {', '.join(s for s, _ in SEASONS)}."
        ), {}

    if provider == "fip_api":
        comitato = _norm(data.get("comitato_codice"))
        campionato = _norm(data.get("codice_campionato"))
        fase = (data.get("codice_fase") or "").strip()
        sesso = _norm(data.get("sesso")) or "M"
        girone = _norm(data.get("codice_girone"))
        if comitato not in FIP_COMITATI_CODES:
            return False, f"Comitato FIP non valido: {comitato!r}.", {}
        if campionato not in FIP_CAMPIONATI_CODES:
            return False, (
                f"Campionato FIP non valido: {campionato!r}."
            ), {}
        if fase not in FIP_FASI_CODES:
            return False, f"Fase FIP non valida: {fase!r}.", {}
        if sesso not in FIP_SESSO_CODES:
            return False, f"Sesso non valido: {sesso!r}.", {}
        if not girone or not _FIP_GIRONE_RE.match(girone):
            return False, (
                f"Girone FIP non valido: {girone!r}. "
                "Usa una lettera A-Z (regionali) o un id numerico "
                "(nazionali, es. 85160)."
            ), {}
        normalized = {
            "provider": provider,
            "comitato_codice": comitato,
            "province_codice": "MI",
            "codice_campionato": campionato,
            "codice_fase": fase,
            "codice_girone": girone,
            "season_label": season,
            "sesso": sesso,
        }
        return True, None, normalized

    # playbasket_html
    region = (data.get("region") or "lombardia").strip().lower()
    comitato = _norm(data.get("comitato_codice")) or "RLO"
    province = _norm(data.get("province_codice")) or "MI"
    campionato = _norm(data.get("codice_campionato"))
    fase = (data.get("codice_fase") or "").strip() or "1"
    girone = _norm(data.get("codice_girone"))
    if region not in PLAYBASKET_REGION_CODES:
        return False, f"Regione non valida: {region!r}.", {}
    if comitato not in PLAYBASKET_COMITATI_CODES:
        return False, f"Comitato non valido: {comitato!r}.", {}
    if province not in PLAYBASKET_PROVINCE_CODES:
        return False, f"Provincia non valida: {province!r}.", {}
    if campionato not in PLAYBASKET_CHAMPIONSHIP_CODES:
        return False, (
            f"Campionato Playbasket non valido: {campionato!r}. "
            f"Supportati: {sorted(PLAYBASKET_CHAMPIONSHIP_CODES)}."
        ), {}
    if fase not in PLAYBASKET_FASI_CODES:
        return False, f"Fase non valida: {fase!r}.", {}
    if girone not in PLAYBASKET_GIRONE_CODES:
        return False, (
            f"Girone Playbasket non valido: {girone!r}. "
            f"Gironi mappati: {sorted(PLAYBASKET_GIRONE_CODES)}."
        ), {}
    normalized = {
        "provider": provider,
        "comitato_codice": comitato,
        "province_codice": province,
        "codice_campionato": campionato,
        "codice_fase": fase,
        "codice_girone": girone,
        "season_label": season,
        "sesso": "M",
        "region": region,
    }
    return True, None, normalized


def default_display_name(provider: str, norm: dict) -> str:
    if provider == "fip_api":
        return (f"FIP {norm['codice_campionato']} "
                f"{norm['comitato_codice']} Gir. {norm['codice_girone']} "
                f"{norm['season_label']}").strip()
    return (f"Playbasket {norm['codice_campionato']} "
            f"Gir. {norm['codice_girone']} {norm['season_label']}").strip()
