"""Play suggester (Slice N4).

Ranks playbook plays by historical PPP in the current context
(score/time/lineup situation + quarter). Context matching is deliberately
light: plays whose type/tags mention the situation get a boost, then PPP
decides. Untried plays trail with a "no data" reason instead of vanishing.
"""

from core.play_effectiveness import play_effectiveness

_CONTEXT_HINTS = (
    ("zone", ("zone",)),
    ("fast", ("transition", "fast", "early")),
    ("transition", ("transition", "fast", "early")),
    ("lead", ("clock", "stall", "protect", "half-court", "halfcourt")),
    ("protect", ("clock", "stall", "protect", "half-court", "halfcourt")),
    ("clutch", ("clutch", "late", "horns", "lob", "iso")),
    ("press", ("press", "break")),
    ("lob", ("lob",)),
    ("iso", ("iso",)),
)

_DEFAULT_LIMIT = 5


def _context_boost(play_type: str, tags: str, situation: str) -> float:
    if not situation:
        return 0.0
    text = f"{play_type or ''} {tags or ''}".lower()
    for keyword, hints in _CONTEXT_HINTS:
        if keyword in situation and any(h in text for h in hints):
            return 0.15
    return 0.0


def suggest_plays(team_id: int, situation: str = "", quarter=None,
                  limit: int = _DEFAULT_LIMIT,
                  game_type: str = "ALL") -> dict:
    """Rank plays for ``situation`` (free text) + optional quarter.

    Returns ``{"situation", "plays": [...], "note"}``; each play carries
    ``score`` (PPP + context boost), PPP, possessions, verdict, and reason.
    """
    from core.models import Play

    situation = (situation or "").lower().strip()
    rows = {r["play_id"]: r for r in
            play_effectiveness(team_id, game_type=game_type)}
    plays = Play.query.filter_by(team_id=team_id, is_active=True).all()

    ranked = []
    for play in plays:
        row = rows.get(play.id)
        ppp = row["ppp"] if row else 0.0
        poss = row["possessions"] if row else 0
        boost = _context_boost(play.play_type, play.tags, situation)
        if quarter is not None and row:
            try:
                qcell = row["by_quarter"].get(str(int(quarter)))
            except (TypeError, ValueError):
                qcell = None
            if qcell and qcell["possessions"] >= 3:
                ppp = qcell["ppp"]
        if row:
            reason = (f"{poss} possessions at {row['ppp']:.2f} PPP"
                      + (" (quarter split)" if quarter else ""))
        else:
            reason = "No tracked possessions yet — try it to collect data"
        ranked.append({
            "play_id": play.id,
            "name": play.name,
            "play_type": play.play_type,
            "ppp": ppp,
            "possessions": poss,
            "verdict": row["verdict"] if row else "untried",
            "score": round(ppp + boost, 3),
            "reason": reason,
        })
    ranked.sort(key=lambda r: (r["score"], r["possessions"]), reverse=True)
    return {
        "situation": situation,
        "quarter": quarter,
        "plays": ranked[:max(1, limit)],
        "note": ("Ranked by historical PPP"
                 + (" with a context boost" if situation else "")
                 + "."),
    }
