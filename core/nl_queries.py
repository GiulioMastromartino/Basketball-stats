"""Natural-language queries (Slice N4).

Rule-based answers over the existing endpoints — no new math. Each query
returns ``{"intent", "answer", "data"}``; unknown queries fall back to a
list of supported examples. Case-insensitive, keyword-driven.
"""

import re

from core.aggregate_cache import cached_four_factors

EXAMPLES = [
    "best lineup vs zone",
    "best 5 to protect a lead",
    "who is our top scorer?",
    "how is our shooting?",
    "do we have a turnover problem?",
    "how is our rebounding?",
    "how is our recent form?",
]

_LINEUP_CONTEXTS = (
    ("zone", "vs_zone"),
    ("fast", "vs_fast"),
    ("transition", "vs_fast"),
    ("running", "vs_fast"),
    ("lead", "protect_lead"),
    ("close", "protect_lead"),
    ("clutch", "protect_lead"),
    ("stop", "need_stops"),
    ("defen", "need_stops"),
    ("score", "need_score"),
    ("bucket", "need_score"),
    ("offense", "need_score"),
)

_CONTEXT_LABELS = {
    "vs_zone": "against zone defense",
    "vs_fast": "against a fast team",
    "protect_lead": "to protect a lead",
    "need_stops": "to get stops",
    "need_score": "to score",
    "balanced": "overall",
}


def _team_games(team_id, game_type="ALL", limit=10):
    from core.models import Game

    query = Game.query.filter_by(team_id=team_id).order_by(
        Game.sort_date.desc())
    if game_type and game_type != "ALL":
        query = query.filter(Game.game_type == game_type)
    return query.limit(limit).all()


def _answer_lineup(team_id, context, game_type):
    from core.services.lineup_service import rank_lineups_for_context

    result = rank_lineups_for_context(team_id, context)
    lineups = result.get("lineups") or []
    if not lineups:
        return {
            "intent": "lineup",
            "answer": ("No lineup has enough tracked minutes yet "
                       f"{_CONTEXT_LABELS[context]}. Track a game with "
                       "substitutions first."),
            "data": {"context": context, "lineups": []},
        }
    top = lineups[0]
    names = ", ".join(top.get("players") or [])
    return {
        "intent": "lineup",
        "answer": (f"Best 5 {_CONTEXT_LABELS[context]}: {names} "
                   f"(net {top.get('net_rating'):+.1f}, "
                   f"{top.get('minutes', 0)} min)."),
        "data": {"context": context, "lineups": lineups[:3]},
    }


def _answer_top_scorer(team_id, game_type):
    from core.models import Game, PlayerStat
    from sqlalchemy import func

    query = (PlayerStat.query.join(Game, PlayerStat.game_id == Game.id)
             .filter(Game.team_id == team_id))
    if game_type and game_type != "ALL":
        query = query.filter(Game.game_type == game_type)
    rows = (query
            .with_entities(PlayerStat.player_name,
                           func.avg(PlayerStat.points),
                           func.count(PlayerStat.id))
            .group_by(PlayerStat.player_name)
            .having(func.count(PlayerStat.id) >= 1)
            .order_by(func.avg(PlayerStat.points).desc()).all())
    if not rows:
        return {"intent": "top_scorer",
                "answer": "No player stats recorded yet.",
                "data": {}}
    name, avg, games = rows[0]
    return {
        "intent": "top_scorer",
        "answer": (f"{name} leads the team at {float(avg):.1f} PPG "
                   f"over {games} games."),
        "data": {"player": name, "ppg": round(float(avg), 1),
                 "games": games},
    }


def _answer_shooting(team_id, game_type):
    games = _team_games(team_id, game_type)
    if not games:
        return {"intent": "shooting",
                "answer": "No games recorded yet.",
                "data": {}}
    factors = cached_four_factors([g.id for g in games])
    efg = factors.get("efg_pct", 0)
    verdict = "solid" if efg >= 50 else ("average" if efg >= 45 else "struggling")
    return {
        "intent": "shooting",
        "answer": (f"Shooting is {verdict}: eFG% {efg:.1f}% over the last "
                   f"{len(games)} games (target 50%+)."),
        "data": {"efg_pct": efg, "games_used": len(games)},
    }


def _answer_turnovers(team_id, game_type):
    games = _team_games(team_id, game_type)
    if not games:
        return {"intent": "turnovers",
                "answer": "No games recorded yet.",
                "data": {}}
    factors = cached_four_factors([g.id for g in games])
    tov = factors.get("tov_pct", 0)
    verdict = ("a real problem" if tov >= 16 else
               "worth watching" if tov >= 14 else "under control")
    return {
        "intent": "turnovers",
        "answer": (f"Turnovers are {verdict}: TOV% {tov:.1f}% "
                   f"(target <14%) over {len(games)} games."),
        "data": {"tov_pct": tov, "games_used": len(games)},
    }


def _answer_rebounding(team_id, game_type):
    games = _team_games(team_id, game_type)
    if not games:
        return {"intent": "rebounding",
                "answer": "No games recorded yet.",
                "data": {}}
    factors = cached_four_factors([g.id for g in games])
    orb = factors.get("orb_pct", 0)
    verdict = "dominant" if orb >= 32 else ("fine" if orb >= 28 else "leaking")
    return {
        "intent": "rebounding",
        "answer": (f"Offensive rebounding is {verdict}: OREB% {orb:.1f}% "
                   f"(target 28%+) over {len(games)} games."),
        "data": {"orb_pct": orb, "games_used": len(games)},
    }


def _answer_form(team_id, game_type):
    games = _team_games(team_id, game_type, limit=5)
    if not games:
        return {"intent": "form",
                "answer": "No games recorded yet.",
                "data": {}}
    wins = sum(1 for g in games if g.result == "W")
    diff = sum((g.team_score or 0) - (g.opponent_score or 0) for g in games)
    return {
        "intent": "form",
        "answer": (f"Last {len(games)}: {wins}W-{len(games) - wins}L, "
                   f"{diff:+d} point differential."),
        "data": {"games": len(games), "wins": wins,
                 "differential": diff},
    }


def answer_query(query: str, team_id: int, game_type: str = "ALL") -> dict:
    """Answer a natural-language coaching question for a team."""
    text = (query or "").lower()

    if "lineup" in text or "best 5" in text or "best five" in text \
            or "who should" in text or "clutch" in text:
        context = "balanced"
        for keyword, mapped in _LINEUP_CONTEXTS:
            if keyword in text:
                context = mapped
                break
        return _answer_lineup(team_id, context, game_type)
    if re.search(r"top scor|scoring leader|most points|who scores", text):
        return _answer_top_scorer(team_id, game_type)
    if re.search(r"shoot|efg|three|3pt|free throw|ft%", text):
        return _answer_shooting(team_id, game_type)
    if re.search(r"turnover|tov|sloppy|giveaway", text):
        return _answer_turnovers(team_id, game_type)
    if re.search(r"rebound|oreb|board", text):
        return _answer_rebounding(team_id, game_type)
    if re.search(r"form|trend|recent|last games|streak", text):
        return _answer_form(team_id, game_type)
    return {
        "intent": "unknown",
        "answer": ("I can answer questions like: " + "; ".join(EXAMPLES)),
        "data": {"examples": list(EXAMPLES)},
    }
