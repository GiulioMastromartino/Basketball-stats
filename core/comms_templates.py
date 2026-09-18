"""Post-game comms automation (Slice N3).

WhatsApp/email templates with ``{{merge_tags}}`` for staff, parents, and
fans. Rendering is pure string substitution; unknown tags are left in
place so a typo is visible instead of silently dropped.
"""

import re

TAG_RE = re.compile(r"\{\{(\w+)\}\}")

TEMPLATES = {
    "postgame_whatsapp": (
        "\U0001F3C0 *{{team}} {{result}} {{opponent}} ({{score}})*\n"
        "{{date}}\n\n"
        "\U00002B50 Top scorer: {{top_scorer}} ({{top_points}} PTS)\n"
        "Full box score + PDF in the team hub."
    ),
    "postgame_email_subject": "[{{team}}] {{result}} vs {{opponent}} ({{score}})",
    "postgame_email_body": (
        "Hi all,\n\n"
        "Final: {{team}} {{result}} {{opponent}}, {{score}} ({{date}}).\n"
        "Top scorer: {{top_scorer}} with {{top_points}} points.\n\n"
        "The full box score and PDF report are in the team hub.\n\n"
        "— HoopsLab"
    ),
    "parent_digest": (
        "\U0001F3C0 {{team}} weekly digest\n"
        "Games: {{games_played}} ({{wins}}W-{{losses}}L) · "
        "Top scorer: {{top_scorer}} ({{top_points}} PPG)\n"
        "Next: check the team hub for PDFs and photos."
    ),
}

KNOWN_TAGS = ("team", "opponent", "score", "result", "date",
              "top_scorer", "top_points", "games_played", "wins", "losses")


def render(name: str, context: dict) -> str:
    """Render template ``name`` with ``context`` (unknown name → KeyError)."""
    template = TEMPLATES[name]  # raises KeyError for unknown templates
    context = context or {}

    def _replace(match):
        key = match.group(1)
        return str(context[key]) if key in context else match.group(0)

    return TAG_RE.sub(_replace, template)


def postgame_context(team_name: str, game, stat_rows) -> dict:
    """Build merge-tag context from a Game + its PlayerStat rows."""
    top_name, top_points = "—", 0
    for row in stat_rows or []:
        pts = int(getattr(row, "points", 0) or 0)
        if pts > top_points:
            top_name, top_points = row.player_name, pts
    return {
        "team": team_name or "Us",
        "opponent": getattr(game, "opponent", "Opponent"),
        "score": f"{game.team_score} - {game.opponent_score}",
        "result": getattr(game, "result", ""),
        "date": getattr(game, "date", ""),
        "top_scorer": top_name,
        "top_points": top_points,
    }
