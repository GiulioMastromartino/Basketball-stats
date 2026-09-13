"""Opponent scout auto-report builder (one-page PDF context).

Reads internal game history vs a single opponent and summarizes:
- record over the last N meetings (W-L plus per-game scores),
- team per-game averages vs that opponent (PTS, FG%/3P%/FT%, REB, AST, TOV),
- top-3 opponent-beaters ranked by average Hollinger Game Score,
- zone tendency summary when shot-tracking rows exist (skipped otherwise),
- latest external sidecar score vs that opponent (read-only, best effort).

Never invents data: every section degrades to an "insufficient data" state
when its source rows are missing, and the external lookup never raises.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func

from core.models import Game, PlayerStat, ShotEvent
from core.utils import calculate_game_score, safe_percentage

DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def _clamp_limit(limit_n_games):
    try:
        limit = int(limit_n_games)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _latest_external_vs(opponent):
    """Best-effort read-only lookup of the latest sidecar score vs opponent.

    Returns a dict with home/away/scores/date/status, or None when the
    sidecar cache is absent, empty, or has no scored game vs the opponent.
    Never raises and never creates state when the cache file is missing.
    """
    try:
        import os
        from pathlib import Path

        from core import external_store

        override = os.getenv("EXT_CACHE_PATH")
        if override:
            cache_path = Path(override)
        else:
            cache_path = (
                Path(external_store.__file__).resolve().parents[1]
                / "data"
                / "external_cache.db"
            )
        if not cache_path.exists():
            return None

        needle = (opponent or "").strip().lower()
        if not needle:
            return None

        conn = external_store.connect(str(cache_path))
        try:
            latest = None
            for champ in external_store.list_championships(conn):
                for game in external_store.list_games(
                    conn, champ["id"], team_filter=opponent.strip()
                ):
                    if game.get("home_score") is None or game.get(
                        "away_score"
                    ) is None:
                        continue
                    haystack = (
                        f"{game.get('home', '')} {game.get('away', '')}".lower()
                    )
                    if needle not in haystack:
                        continue
                    if latest is None or str(game.get("game_date", "")) >= str(
                        latest.get("game_date", "")
                    ):
                        latest = game
            if not latest:
                return None
            return {
                "home": latest.get("home", ""),
                "away": latest.get("away", ""),
                "home_score": latest.get("home_score"),
                "away_score": latest.get("away_score"),
                "date": latest.get("game_date", ""),
                "status": latest.get("status", ""),
            }
        finally:
            conn.close()
    except Exception:
        return None


def _classify_zone(x_loc, y_loc, shot_type):
    try:
        from core.advanced_analytics import classify_shot_zone

        return classify_shot_zone(x_loc, y_loc, shot_type or "")
    except Exception:
        return "Midrange"


def build_scout(opponent, team_id, limit_n_games=DEFAULT_LIMIT):
    """Build the template context for the opponent scout one-pager.

    Args:
        opponent: Opponent name (matched case-insensitively, exact).
        team_id: Owning team id; all queries are scoped to it.
        limit_n_games: How many recent meetings to include (1..20).

    Returns:
        Dict ready to unpack into ``game_scout_pdf.html``.
    """
    limit = _clamp_limit(limit_n_games)
    name = (opponent or "").strip()

    games = []
    if name and team_id is not None:
        games = (
            Game.query.filter(
                Game.team_id == team_id,
                func.lower(Game.opponent) == name.lower(),
            )
            .order_by(Game.sort_date.desc())
            .limit(limit)
            .all()
        )

    display_name = games[0].opponent if games else name
    game_ids = [g.id for g in games]
    has_data = bool(games)

    record_games = [
        {
            "date": g.date,
            "team_score": g.team_score,
            "opponent_score": g.opponent_score,
            "result": g.result,
        }
        for g in games
    ]
    record = {
        "wins": sum(1 for g in games if g.result == "W"),
        "losses": sum(1 for g in games if g.result != "W"),
        "games": record_games,
    }

    averages = None
    if game_ids:
        stats = PlayerStat.query.filter(PlayerStat.game_id.in_(game_ids)).all()
        totals = {
            "points": sum(s.points or 0 for s in stats),
            "fgm": sum(s.fgm or 0 for s in stats),
            "fga": sum(s.fga or 0 for s in stats),
            "tpm": sum(s.tpm or 0 for s in stats),
            "tpa": sum(s.tpa or 0 for s in stats),
            "ftm": sum(s.ftm or 0 for s in stats),
            "fta": sum(s.fta or 0 for s in stats),
            "reb": sum((s.reb or 0) for s in stats),
            "ast": sum(s.ast or 0 for s in stats),
            "tov": sum(s.tov or 0 for s in stats),
        }
        n = len(games)
        if stats and n:
            averages = {
                "pts": round(totals["points"] / n, 1),
                "fg_pct": round(safe_percentage(totals["fgm"], totals["fga"]), 1),
                "tp_pct": round(safe_percentage(totals["tpm"], totals["tpa"]), 1),
                "ft_pct": round(safe_percentage(totals["ftm"], totals["fta"]), 1),
                "reb": round(totals["reb"] / n, 1),
                "ast": round(totals["ast"] / n, 1),
                "tov": round(totals["tov"] / n, 1),
            }

    top_beaters = []
    if game_ids:
        rows = PlayerStat.query.filter(
            PlayerStat.game_id.in_(game_ids)
        ).all()
        by_player = defaultdict(list)
        for s in rows:
            minutes = (s.minutes or "").strip()
            if minutes in ("", "00:00", "0"):
                continue
            gmsc = calculate_game_score(
                s.points or 0,
                s.fgm or 0,
                s.fga or 0,
                s.ftm or 0,
                s.fta or 0,
                s.oreb or 0,
                s.dreb or 0,
                s.stl or 0,
                s.ast or 0,
                s.blk or 0,
                s.pf or 0,
                s.tov or 0,
            )
            by_player[s.player_name].append(
                {"gmsc": gmsc, "points": s.points or 0}
            )
        ranked = []
        for player_name, entries in by_player.items():
            avg_gmsc = sum(e["gmsc"] for e in entries) / len(entries)
            avg_pts = sum(e["points"] for e in entries) / len(entries)
            ranked.append(
                {
                    "player_name": player_name,
                    "games": len(entries),
                    "avg_gmsc": round(avg_gmsc, 1),
                    "avg_pts": round(avg_pts, 1),
                }
            )
        ranked.sort(key=lambda r: r["avg_gmsc"], reverse=True)
        top_beaters = ranked[:3]

    zones = {"has_shot_data": False, "rows": []}
    if game_ids:
        shots = (
            ShotEvent.query.filter(
                ShotEvent.game_id.in_(game_ids),
                ShotEvent.x_loc.isnot(None),
                ShotEvent.y_loc.isnot(None),
            )
            .all()
        )
        if shots:
            buckets = defaultdict(lambda: {"makes": 0, "attempts": 0})
            for shot in shots:
                zone = shot.zone or _classify_zone(
                    shot.x_loc, shot.y_loc, shot.shot_type
                )
                buckets[zone]["attempts"] += 1
                if (shot.result or "").lower() == "made":
                    buckets[zone]["makes"] += 1
            rows = [
                {
                    "zone": zone,
                    "attempts": data["attempts"],
                    "makes": data["makes"],
                    "pct": round(
                        safe_percentage(data["makes"], data["attempts"]), 1
                    ),
                }
                for zone, data in buckets.items()
            ]
            rows.sort(key=lambda r: r["attempts"], reverse=True)
            zones = {"has_shot_data": True, "rows": rows}

    return {
        "opponent": display_name,
        "team_id": team_id,
        "limit": limit,
        "has_data": has_data,
        "record": record,
        "averages": averages,
        "top_beaters": top_beaters,
        "zones": zones,
        "external": _latest_external_vs(name) if name else None,
        "generated_at": datetime.now().strftime("%B %d, %Y"),
    }
