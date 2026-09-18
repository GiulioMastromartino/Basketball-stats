"""Halftime one-tap share (Slice N1).

Builds the staff WhatsApp text for a halftime update from the same live
payload the v2 console already sends to ``POST /reports/live/halftime-pdf``
(opponent, date, team_score, opp_score, player_stats). Sending itself goes
through ``core.services.whatsapp_service``; this module stays side-effect
free so it is trivially unit-testable.
"""


def validate_halftime_payload(data) -> list:
    """Return a list of human-readable problems (empty == valid)."""
    errors = []
    if not isinstance(data, dict):
        return ["payload must be a JSON object"]
    if not (data.get("opponent") or "").strip():
        errors.append("opponent is required")
    if not (data.get("date") or "").strip():
        errors.append("date is required")
    stats = data.get("player_stats")
    if not isinstance(stats, dict) or not stats:
        errors.append("player_stats must be a non-empty object")
    for key in ("team_score", "opp_score"):
        try:
            value = int(data.get(key, 0))
        except (TypeError, ValueError):
            errors.append(f"{key} must be an integer")
            continue
        if value < 0 or value > 300:
            errors.append(f"{key} looks out of range")
    return errors


def _num(value, default=0):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def build_halftime_text(data) -> str:
    """Render the staff WhatsApp halftime message (<= ~600 chars)."""
    opponent = (data.get("opponent") or "Unknown").strip()
    date = (data.get("date") or "").strip()
    team_score = _num(data.get("team_score"))
    opp_score = _num(data.get("opp_score"))
    stats = data.get("player_stats") or {}

    leaders = sorted(
        stats.items(), key=lambda kv: _num((kv[1] or {}).get("points")), reverse=True
    )[:3]
    lines = [
        f"\u23f8\ufe0f *HALFTIME* {opponent} ({date})",
        f"Score: *{team_score} - {opp_score}*",
    ]
    if leaders:
        lines.append("")
        lines.append("*Top scorers*")
        for name, row in leaders:
            row = row or {}
            lines.append(
                f"- {name}: {_num(row.get('points'))} PTS, "
                f"{_num(row.get('reb', _num(row.get('oreb')) + _num(row.get('dreb'))))} REB, "
                f"{_num(row.get('ast'))} AST"
            )

    fgm = sum(_num((r or {}).get("fgm")) for r in stats.values())
    fga = sum(_num((r or {}).get("fga")) for r in stats.values())
    tov = sum(_num((r or {}).get("tov")) for r in stats.values())
    if fga:
        lines.append("")
        lines.append(f"Team FG {fgm}/{fga} ({fgm / fga * 100:.0f}%) \u00b7 TOV {tov}")
    lines.append("")
    lines.append("Full box in the halftime PDF.")
    return "\n".join(lines)
