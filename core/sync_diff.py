"""Deeper sync diffs (P2 remainder).

Standings/game change diffs ("score corrected 78→80"), roster
cross-checks, internal-vs-external score checks, and per-championship
sync-health snapshots for the sidecar. All pure functions except
``sync_health_snapshot``, which reads the SQLite sidecar read-only and
never raises.
"""

from datetime import datetime, timedelta

STALE_AFTER_HOURS = 26


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def diff_standings(old_rows: list, new_rows: list) -> dict:
    """Diff two standings snapshots (dicts with team/position/points/...)."""
    old_by_team = {_norm(r.get("team")): r for r in old_rows or []}
    new_by_team = {_norm(r.get("team")): r for r in new_rows or []}
    added = [new_by_team[k] for k in new_by_team if k not in old_by_team]
    removed = [old_by_team[k] for k in old_by_team if k not in new_by_team]
    moved, score_changes = [], []
    for key in old_by_team:
        if key not in new_by_team:
            continue
        old, new = old_by_team[key], new_by_team[key]
        try:
            delta = int(old.get("position", old.get("pos", 0)) or 0) - int(
                new.get("position", new.get("pos", 0)) or 0)
        except (TypeError, ValueError):
            delta = 0
        if delta:
            moved.append({"team": new.get("team") or old.get("team"),
                          "old_pos": old.get("position", old.get("pos")),
                          "new_pos": new.get("position", new.get("pos")),
                          "delta": delta})
        for field in ("points", "pts", "won", "lost", "scored", "conceded",
                      "w", "l", "pf", "ps", "g"):
            if field in old and field in new and old[field] != new[field]:
                score_changes.append({"team": new.get("team") or old.get("team"),
                                      "field": field,
                                      "old": old[field], "new": new[field]})
    moved.sort(key=lambda m: m["delta"], reverse=True)
    return {"added": added, "removed": removed, "moved": moved,
            "score_changes": score_changes}


def _game_key(game: dict) -> str:
    date = game.get("game_date") or game.get("data") or game.get("date") or ""
    home = _norm(game.get("home") or game.get("casa") or "")
    away = _norm(game.get("away") or game.get("ospite") or "")
    return f"{date}|{home}|{away}"


def _score(game: dict):
    home = game.get("home_score", game.get("pc"))
    away = game.get("away_score", game.get("po"))
    try:
        home = int(home) if home not in (None, "", "-") else None
    except (TypeError, ValueError):
        home = None
    try:
        away = int(away) if away not in (None, "", "-") else None
    except (TypeError, ValueError):
        away = None
    return home, away


def diff_games(old_games: list, new_games: list) -> dict:
    """Surface score corrections between two external game snapshots."""
    old_by_key = {_game_key(g): g for g in old_games or []}
    corrections, added = [], []
    for game in new_games or []:
        key = _game_key(game)
        previous = old_by_key.get(key)
        if previous is None:
            added.append(game)
            continue
        old_home, old_away = _score(previous)
        new_home, new_away = _score(game)
        if (old_home, old_away) != (new_home, new_away) and \
                None not in (old_home, old_away, new_home, new_away):
            corrections.append({
                "game": key,
                "old": f"{old_home}-{old_away}",
                "new": f"{new_home}-{new_away}",
            })
    return {"corrections": corrections, "added": added,
            "count": len(corrections)}


def roster_cross_check(roster_names: list, stat_names: list) -> dict:
    """Cross-check the team roster vs names in box scores.

    ``stat_only`` names (box score but no roster row) are the usual
    fallout of legacy CSV imports; ``without_stats`` flags roster rows
    that never played (or name mismatches worth merging).
    """
    roster = {_norm(n): n for n in roster_names or [] if (n or "").strip()}
    stats = {_norm(n): n for n in stat_names or [] if (n or "").strip()}
    return {
        "matched": sorted(roster[k] for k in roster if k in stats),
        "stat_only": sorted(stats[k] for k in stats if k not in roster),
        "without_stats": sorted(roster[k] for k in roster if k not in stats),
    }


def cross_check_game_scores(team_name: str, internal_games: list,
                            external_games: list) -> list:
    """Compare internal results vs the external feed for the same fixtures.

    Matches conservatively: same date (DD/MM/YYYY or YYYY-MM-DD tolerant)
    with our team on one side and the same opponent on the other.
    Returns mismatches like "score corrected 78→80".
    """
    ours = _norm(team_name)
    mismatches = []
    for internal in internal_games or []:
        opp = _norm(internal.get("opponent"))
        date = _norm(internal.get("date"))
        for external in external_games or []:
            if _norm_date(external.get("game_date") or external.get("data")) != \
                    _norm_date(date):
                continue
            home = _norm(external.get("home") or external.get("casa"))
            away = _norm(external.get("away") or external.get("ospite"))
            if ours in home or home in ours:
                us_ext, them_ext, we_are_home = (
                    external.get("home_score", external.get("pc")),
                    external.get("away_score", external.get("po")), True)
                them_name = away
            elif ours in away or away in ours:
                us_ext, them_ext, we_are_home = (
                    external.get("away_score", external.get("po")),
                    external.get("home_score", external.get("pc")), False)
                them_name = home
            else:
                continue
            if opp not in them_name and them_name not in opp:
                continue
            try:
                us_ext = int(us_ext) if us_ext not in (None, "", "-") else None
                them_ext = int(them_ext) if them_ext not in (
                    None, "", "-") else None
            except (TypeError, ValueError):
                continue
            if us_ext is None or them_ext is None:
                continue
            us_int = internal.get("team_score")
            them_int = internal.get("opponent_score")
            if (us_int, them_int) != (us_ext, them_ext):
                mismatches.append({
                    "date": internal.get("date"),
                    "opponent": internal.get("opponent"),
                    "internal": f"{us_int}-{them_int}",
                    "external": f"{us_ext}-{them_ext}",
                    "we_are_home": we_are_home,
                })
    return mismatches


def _norm_date(value) -> str:
    """Normalize DD/MM/YYYY or YYYY-MM-DD to YYYY-MM-DD ("" if unknown)."""
    text = (value or "").strip()
    if not text or text == "-":
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def sync_health_snapshot(championship_id: int = None) -> dict:
    """Per-championship sync health from the sidecar (read-only)."""
    from core import external_store as store

    try:
        conn = store.connect()
    except Exception as exc:
        return {"error": f"sidecar unavailable: {exc}", "championships": []}
    try:
        champs = store.list_championships(conn)
        if championship_id is not None:
            champs = [c for c in champs if c["id"] == championship_id]
        now = datetime.utcnow()
        result = []
        for champ in champs:
            games = store.list_games(conn, champ["id"])
            standings = store.get_standings(conn, champ["id"])
            log_rows = [dict(r) for r in conn.execute(
                """SELECT * FROM ext_sync_log
                   WHERE championship_id=? OR championship_id IS NULL
                   ORDER BY id DESC LIMIT 5""",
                (champ["id"],)).fetchall()]
            last_errors = [r["error"] for r in log_rows if r.get("error")]
            try:
                checked = datetime.strptime(
                    (champ.get("last_checked") or "")[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                try:
                    checked = datetime.strptime(
                        (champ.get("last_checked") or "")[:19],
                        "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    checked = None
            stale = (checked is None or
                     now - checked > timedelta(hours=STALE_AFTER_HOURS))
            result.append({
                "id": champ["id"],
                "display_name": champ.get("display_name"),
                "provider": champ.get("provider"),
                "active": bool(champ.get("active")),
                "last_checked": champ.get("last_checked"),
                "stale": stale,
                "games": len(games),
                "standings_teams": len(standings),
                "recent_errors": last_errors[:3],
                "last_runs": [
                    {"fetched": r.get("fetched"), "added": r.get("added"),
                     "updated": r.get("updated"), "error": r.get("error"),
                     "at": r.get("started_at")} for r in log_rows
                ],
            })
        return {"championships": result, "count": len(result)}
    except Exception as exc:
        return {"error": f"health check failed: {exc}", "championships": []}
    finally:
        try:
            conn.close()
        except Exception:
            pass
