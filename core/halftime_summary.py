"""Normalize the live halftime payload for the halftime PDF summary.

The payload is built in the browser and is not persisted, so this module is
the single place that decides how tracker data maps to the printable report.
It accepts both tracker generations:

* legacy live tracker (``/live-game``): ``shot_locations`` is the only shot
  source and ``game_events`` carries FT / rebound / foul rows (the legacy
  tracker never emits ``SHOT_2PT`` / ``SHOT_3PT`` rows);
* v2 / saved-game style: canonical event rows (``SHOT_2PT``, ``FT_MADE``,
  ``ASSIST``, ``REBOUND`` ...) are present and ``shot_locations`` may be
  missing.

Every value is coerced before use: a malformed payload must never take the
PDF endpoint down with a 500.
"""

import ast
import json

from core.utils import calculate_efg_percent, parse_minutes

_QUARTERS = (1, 2)

_OPPONENT_TEAM_VALUES = {"AWAY", "OPP", "OPPONENT", "THEM", "OPPONENTS"}

_QUARTER_KEYS = (
    "pts",
    "fgm",
    "fga",
    "tpm",
    "tpa",
    "ftm",
    "fta",
    "tov",
    "pf",
    "reb",
    "ast",
    "stl",
    "blk",
)

# Event aliases that represent a field-goal attempt. Canonical rows use
# SHOT_2PT / SHOT_3PT; a few import/rescue shapes carry the made/missed
# suffix instead.
_SHOT_EVENT_TYPES = {
    "SHOT_2PT": "2pt",
    "SHOT_3PT": "3pt",
    "2PT": "2pt",
    "3PT": "3pt",
    "2PT_MADE": "2pt",
    "2PT_MISS": "2pt",
    "2PT_MISSED": "2pt",
    "3PT_MADE": "3pt",
    "3PT_MISS": "3pt",
    "3PT_MISSED": "3pt",
    "TWO_PT_MADE": "2pt",
    "TWO_PT_MISS": "2pt",
    "THREE_PT_MADE": "3pt",
    "THREE_PT_MISS": "3pt",
}

_FT_EVENT_TYPES = {
    "FT",
    "FT_MADE",
    "FT_MISS",
    "FTM",
    "FREE_THROW",
    "FREE_THROWS",
    "FREE_THROW_MADE",
    "FREE_THROW_MISS",
}

_ASSIST_EVENT_TYPES = {"ASSIST", "AST"}

_REBOUND_EVENT_TYPES = {
    "REBOUND",
    "REBOUND_OFFENSIVE",
    "REBOUND_DEFENSIVE",
    "REBOUND_TEAM",
    "OREB",
    "DREB",
    "OFFENSIVE_REBOUND",
    "DEFENSIVE_REBOUND",
}

_STEAL_EVENT_TYPES = {"STEAL", "STL"}

_BLOCK_EVENT_TYPES = {"BLOCK", "BLK"}

_TURNOVER_EVENT_TYPES = {"TURNOVER", "TOV"}

_FOUL_EVENT_TYPES = {
    "FOUL",
    "FOUL_PERSONAL",
    "PERSONAL_FOUL",
    "TECH_FOUL",
    "TECHNICAL_FOUL",
    "FOUL_TECHNICAL",
    "FLAGRANT_FOUL",
    "FOUL_FLAGRANT",
}


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _is_opponent_entry(entry):
    """True only when an entry is explicitly tagged as the opponent's."""
    team = entry.get("team", entry.get("side"))
    return (
        isinstance(team, str)
        and team.strip().upper() in _OPPONENT_TEAM_VALUES
    )


def _num(value, default=0):
    """Best-effort integer coercion that never raises."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        try:
            return int(float(text))
        except (TypeError, ValueError):
            return default


def _parse_detail(detail):
    """Parse an event detail that may be a dict, JSON text or Python repr."""
    if isinstance(detail, dict):
        return detail
    if detail is None or isinstance(detail, bool):
        return {}
    if isinstance(detail, (int, float)):
        return {"points": _num(detail)}
    if not isinstance(detail, str):
        return {}

    text = detail.strip()
    if not text or len(text) > 4000:
        return {}
    if text.isdigit():
        return {"points": int(text)}

    parsed = None
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return {}

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
        return {"points": int(parsed)}
    return {}


def _quarter_number(value):
    """Return 1/2 for a quarter-like value, None otherwise."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        quarter = int(value)
    else:
        text = str(value).strip().upper()
        if text.startswith("Q"):
            text = text[1:]
        try:
            quarter = int(float(text))
        except (TypeError, ValueError):
            return None
    return quarter if quarter in _QUARTERS else None


def _event_type(event):
    raw = event.get("event_type") or event.get("type") or ""
    if not isinstance(raw, str):
        return ""
    return "_".join(raw.replace("-", " ").strip().upper().split())


def _entry_quarter(entry):
    quarter = entry.get("quarter")
    if quarter is None:
        quarter = entry.get("period")
    return _quarter_number(quarter)


def _made_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"made", "make", "m", "true", "yes", "y", "1"}:
            return True
        if text in {"missed", "miss", "false", "no", "n", "0"}:
            return False
    return None


def _event_made(event, event_type):
    raw = event.get("shot_attempt")
    if raw is None:
        raw = event.get("result")
    if raw is None:
        raw = event.get("shot_result")
    made = _made_value(raw)
    if made is not None:
        return made
    if event_type.endswith("_MADE") or event_type.endswith("_MADE_"):
        return True
    if event_type.endswith("_MISS") or event_type.endswith("_MISSED"):
        return False
    detail = _parse_detail(event.get("detail", event.get("Detail")))
    return _made_value(detail.get("result")) is True


def _shot_type(shot):
    raw = shot.get("type", shot.get("shot_type", ""))
    if isinstance(raw, str):
        text = raw.strip().lower()
        if "3" in text:
            return "3pt"
        if "2" in text:
            return "2pt"
    return "3pt" if _num(shot.get("points")) == 3 else "2pt"


def _shot_made(shot):
    raw = shot.get("result")
    if raw is None:
        raw = shot.get("made")
    made = _made_value(raw)
    if made is not None:
        return made
    return _num(shot.get("points")) > 0


def _ft_counts(event_type, detail, event):
    ftm = detail.get("ftm")
    fta = detail.get("fta")

    if ftm is None and "points" in detail:
        ftm = detail.get("points")

    if ftm is None:
        made = _event_made(event, event_type)
        if event_type in {"FT_MADE", "FTM", "FREE_THROW_MADE"}:
            made = True
        elif event_type in {"FT_MISS", "FREE_THROW_MISS"}:
            made = False
        if made is not None:
            ftm = 1 if made else 0

    ftm = max(0, _num(ftm))
    if fta is None:
        # A single FT event implies one attempt; a legacy FT trip always
        # carries both ftm and fta, so only fall back for one-shot rows.
        fta = max(ftm, 1) if event_type in {
            "FT_MADE", "FTM", "FT_MISS", "FREE_THROW_MADE", "FREE_THROW_MISS"
        } else ftm
    return ftm, max(ftm, _num(fta))


def _blank_quarter():
    return {key: 0 for key in _QUARTER_KEYS}


def _build_quarterly_stats(game_events, shot_locations):
    """Build Q1/Q2 team totals from whichever shot source the payload has."""
    quarterly = {str(quarter): _blank_quarter() for quarter in _QUARTERS}

    events = game_events if isinstance(game_events, list) else []
    events = [
        event for event in events
        if isinstance(event, dict) and not _is_opponent_entry(event)
    ]
    shots = shot_locations if isinstance(shot_locations, list) else []
    shots = [
        shot for shot in shots
        if isinstance(shot, dict) and not _is_opponent_entry(shot)
    ]

    shot_events = []
    for event in events:
        quarter = _entry_quarter(event)
        if quarter is None:
            continue
        event_type = _event_type(event)
        shot_type = _SHOT_EVENT_TYPES.get(event_type)
        if shot_type:
            shot_events.append((quarter, event, shot_type, event_type))

    # Prefer shot events when present: the v2/saved-game payload carries the
    # complete shot log there. The legacy tracker has no SHOT_* rows at all,
    # so its shot_locations array is the only field-goal source.
    if shot_events:
        for quarter, event, shot_type, event_type in shot_events:
            bucket = quarterly[str(quarter)]
            bucket["fga"] += 1
            if shot_type == "3pt":
                bucket["tpa"] += 1
            if _event_made(event, event_type):
                bucket["fgm"] += 1
                if shot_type == "3pt":
                    bucket["tpm"] += 1
                bucket["pts"] += 3 if shot_type == "3pt" else 2
    else:
        for shot in shots:
            quarter = _entry_quarter(shot)
            if quarter is None:
                continue
            bucket = quarterly[str(quarter)]
            shot_type = _shot_type(shot)
            bucket["fga"] += 1
            if shot_type == "3pt":
                bucket["tpa"] += 1
            if _shot_made(shot):
                bucket["fgm"] += 1
                if shot_type == "3pt":
                    bucket["tpm"] += 1
                points = _num(shot.get("points"))
                bucket["pts"] += (
                    points if points > 0 else (3 if shot_type == "3pt" else 2)
                )

    # Assists live on shot_locations in the legacy payload and as dedicated
    # ASSIST rows in newer payloads. Use one source, never both.
    has_assist_events = any(
        _entry_quarter(event) is not None
        and _event_type(event) in _ASSIST_EVENT_TYPES
        for event in events
    )
    if not has_assist_events:
        for shot in shots:
            quarter = _entry_quarter(shot)
            if quarter is None or not _shot_made(shot):
                continue
            if shot.get("assister") or shot.get("assist"):
                quarterly[str(quarter)]["ast"] += 1

    for event in events:
        quarter = _entry_quarter(event)
        if quarter is None:
            continue
        event_type = _event_type(event)
        if event_type in _SHOT_EVENT_TYPES:
            continue

        detail = _parse_detail(event.get("detail", event.get("Detail")))
        bucket = quarterly[str(quarter)]

        if event_type in _FT_EVENT_TYPES:
            ftm, fta = _ft_counts(event_type, detail, event)
            bucket["ftm"] += ftm
            bucket["fta"] += fta
            bucket["pts"] += ftm
        elif event_type in _ASSIST_EVENT_TYPES:
            bucket["ast"] += 1
        elif event_type in _REBOUND_EVENT_TYPES:
            bucket["reb"] += 1
        elif event_type in _STEAL_EVENT_TYPES:
            bucket["stl"] += 1
        elif event_type in _BLOCK_EVENT_TYPES:
            bucket["blk"] += 1
        elif event_type in _TURNOVER_EVENT_TYPES:
            bucket["tov"] += 1

        # Some payloads annotate any event with the foul it caused.
        pf_increment = _num(detail.get("pf"))
        if pf_increment:
            bucket["pf"] += pf_increment
        elif event_type in _FOUL_EVENT_TYPES:
            bucket["pf"] += 1

    return quarterly


def _minutes_to_seconds(row):
    for key in ("minutes_seconds", "total_seconds", "seconds"):
        if row.get(key) is not None:
            return max(0, _num(row.get(key)))

    raw = row.get("minutes")
    if raw is None:
        raw = row.get("display_minutes")
    if raw is None or isinstance(raw, bool):
        return 0
    if isinstance(raw, (int, float)):
        return max(0, int(raw) * 60)

    text = str(raw).strip()
    if not text:
        return 0
    if ":" in text:
        return max(0, int(round(parse_minutes(text) * 60)))
    return max(0, _num(text) * 60)


def _quarter_seconds(quarter_minutes, quarter):
    for key, value in _as_dict(quarter_minutes).items():
        if _quarter_number(key) == quarter:
            if isinstance(value, str) and ":" in value:
                return max(0, int(round(parse_minutes(value) * 60)))
            return max(0, _num(value))
    return 0


def _build_player_stats(player_stats_raw):
    stats = []
    for player_name, player_row in _as_dict(player_stats_raw).items():
        row = _as_dict(player_row)

        fgm = _num(row.get("fgm"))
        fga = _num(row.get("fga"))
        tpm = _num(row.get("tpm"))
        tpa = _num(row.get("tpa"))
        ftm = _num(row.get("ftm"))
        fta = _num(row.get("fta"))
        oreb = _num(row.get("oreb"))
        dreb = _num(row.get("dreb"))
        ast = _num(row.get("ast"))
        stl = _num(row.get("stl"))
        blk = _num(row.get("blk"))
        tov = _num(row.get("tov"))
        pf = _num(row.get("pf"))
        plus_minus = _num(row.get("plus_minus"))

        points = row.get("points")
        if points in (None, ""):
            points = (max(0, fgm - tpm) * 2) + (tpm * 3) + ftm
        points = _num(points)

        reb_raw = row.get("reb")
        reb = oreb + dreb if reb_raw in (None, "") else _num(reb_raw)

        two_pt_made = max(0, fgm - tpm)
        two_pt_att = max(0, fga - tpa)

        stats.append(
            {
                "player_name": str(player_name),
                "minutes": _format_seconds(_minutes_to_seconds(row)),
                "q1_minutes": _format_seconds(
                    _quarter_seconds(row.get("quarter_minutes"), 1)
                ),
                "q2_minutes": _format_seconds(
                    _quarter_seconds(row.get("quarter_minutes"), 2)
                ),
                "points": points,
                "reb": reb,
                "oreb": oreb,
                "dreb": dreb,
                "ast": ast,
                "stl": stl,
                "blk": blk,
                "tov": tov,
                "pf": pf,
                "fgm": fgm,
                "fga": fga,
                "fg_percent": (fgm / fga * 100) if fga > 0 else 0,
                "tpm": tpm,
                "tpa": tpa,
                "tp_percent": (tpm / tpa * 100) if tpa > 0 else 0,
                "ftm": ftm,
                "fta": fta,
                "ft_percent": (ftm / fta * 100) if fta > 0 else 0,
                "two_pt_made": two_pt_made,
                "two_pt_att": two_pt_att,
                "two_pt_pct": (
                    two_pt_made / two_pt_att * 100 if two_pt_att > 0 else 0
                ),
                "efg_pct": calculate_efg_percent(fgm, tpm, fga),
                "plus_minus": plus_minus,
                "eff": (
                    points
                    + reb
                    + ast
                    + stl
                    + blk
                    - ((fga - fgm) + (fta - ftm) + tov)
                ),
            }
        )

    stats.sort(key=lambda row: (-row["points"], row["player_name"].lower()))
    return stats


def _format_seconds(total_seconds):
    total_seconds = max(0, _num(total_seconds))
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _build_team_aggregates(stats):
    total_fgm = sum(row["fgm"] for row in stats)
    total_fga = sum(row["fga"] for row in stats)
    total_tpm = sum(row["tpm"] for row in stats)
    total_tpa = sum(row["tpa"] for row in stats)
    total_ftm = sum(row["ftm"] for row in stats)
    total_fta = sum(row["fta"] for row in stats)
    total_two_pt_made = sum(row["two_pt_made"] for row in stats)
    total_two_pt_att = sum(row["two_pt_att"] for row in stats)

    return {
        "fg_pct": (total_fgm / total_fga * 100) if total_fga > 0 else 0,
        "tp_pct": (total_tpm / total_tpa * 100) if total_tpa > 0 else 0,
        "ft_pct": (total_ftm / total_fta * 100) if total_fta > 0 else 0,
        "two_pt_pct": (
            total_two_pt_made / total_two_pt_att * 100
            if total_two_pt_att > 0
            else 0
        ),
    }


def _build_top_performers(stats):
    if not stats:
        return {}
    return {
        "points": max(stats, key=lambda row: row["points"]),
        "efficiency": max(stats, key=lambda row: row["eff"]),
        "rebounds": max(stats, key=lambda row: row["reb"]),
    }


def build_halftime_summary(data):
    """Return the template context for the halftime PDF summary."""
    data = _as_dict(data)
    stats = _build_player_stats(data.get("player_stats"))

    return {
        "stats": stats,
        "top_performers": _build_top_performers(stats),
        "team_aggregates": _build_team_aggregates(stats),
        "quarterly_stats": _build_quarterly_stats(
            data.get("game_events"), data.get("shot_locations")
        ),
        "team_score": _num(data.get("team_score")),
        "opp_score": _num(data.get("opp_score")),
    }
