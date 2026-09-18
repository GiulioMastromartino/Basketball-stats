"""Play effectiveness v2 (Slice N2).

PPP by play × quarter from tagged possessions and shot events, with a
cold-play flag (``PPP < 0.85`` on ``>= 10`` possessions → consider retiring).
Possessions are the primary source (they carry points + quarter + play);
untracked shot events with a play tag act as a fallback so partially-tagged
games still produce a row.
"""

from collections import defaultdict

COLD_PPP_THRESHOLD = 0.85
COLD_MIN_POSSESSIONS = 10


def _quarter_bucket(quarter) -> str:
    try:
        q = int(quarter or 0)
    except (TypeError, ValueError):
        return "unknown"
    return str(q) if 1 <= q <= 6 else "unknown"


def play_effectiveness(team_id: int, game_type: str = "ALL",
                       season_id=None) -> list:
    """Rank a team's plays by points per possession.

    Returns rows sorted by PPP desc::
        {"play_id", "name", "play_type", "possessions", "points", "ppp",
         "by_quarter": {q: {"possessions", "points", "ppp"}},
         "games_used": n, "verdict": "keep" | "watch" | "cold"}
    Plays never tagged in a possession/shot are omitted.
    """
    from core.models import Game, Play, Possession, ShotEvent

    game_query = Game.query.filter_by(team_id=team_id)
    if game_type and game_type != "ALL":
        game_query = game_query.filter(Game.game_type == game_type)
    if season_id is not None and season_id != "ALL":
        game_query = game_query.filter(Game.season_id == int(season_id))
    game_ids = [g.id for g in game_query.all()]
    if not game_ids:
        return []

    plays = {p.id: p for p in Play.query.filter_by(team_id=team_id).all()}

    points = defaultdict(int)
    possessions = defaultdict(int)
    by_quarter = defaultdict(lambda: defaultdict(lambda: {"possessions": 0,
                                                          "points": 0}))
    games_used = defaultdict(set)

    for poss in (Possession.query
                 .filter(Possession.game_id.in_(game_ids),
                         Possession.play_id.isnot(None)).all()):
        pid = poss.play_id
        possessions[pid] += 1
        points[pid] += int(poss.points or 0)
        cell = by_quarter[pid][_quarter_bucket(poss.quarter)]
        cell["possessions"] += 1
        cell["points"] += int(poss.points or 0)
        games_used[pid].add(poss.game_id)

    # Fallback: tagged shots in games with no tagged possessions for that play.
    for shot in (ShotEvent.query
                 .filter(ShotEvent.game_id.in_(game_ids),
                         ShotEvent.play_id.isnot(None)).all()):
        pid = shot.play_id
        if possessions[pid]:
            continue
        possessions[pid] += 1
        pts = int(shot.points or 0)
        points[pid] += pts
        cell = by_quarter[pid][_quarter_bucket(shot.quarter)]
        cell["possessions"] += 1
        cell["points"] += pts
        games_used[pid].add(shot.game_id)

    rows = []
    for pid, poss_count in possessions.items():
        play = plays.get(pid)
        if play is None:
            continue
        pts = points[pid]
        ppp = round(pts / poss_count, 3) if poss_count else 0.0
        quarters = {}
        for q, cell in sorted(by_quarter[pid].items()):
            n = cell["possessions"]
            quarters[q] = {
                "possessions": n,
                "points": cell["points"],
                "ppp": round(cell["points"] / n, 3) if n else 0.0,
            }
        if ppp < COLD_PPP_THRESHOLD and poss_count >= COLD_MIN_POSSESSIONS:
            verdict = "cold"
        elif ppp < 1.0 and poss_count >= COLD_MIN_POSSESSIONS:
            verdict = "watch"
        else:
            verdict = "keep"
        rows.append({
            "play_id": pid,
            "name": play.name,
            "play_type": play.play_type,
            "possessions": poss_count,
            "points": pts,
            "ppp": ppp,
            "by_quarter": quarters,
            "games_used": len(games_used[pid]),
            "verdict": verdict,
        })
    rows.sort(key=lambda r: r["ppp"], reverse=True)
    return rows
