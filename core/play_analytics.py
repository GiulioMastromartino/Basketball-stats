from sqlalchemy import func, case, and_
from core.models import db, Play, ShotEvent, GameEvent


def _safe_pct(n, d):
    return round((n / d) * 100, 1) if d and d > 0 else 0.0


def _calc_metrics(shot_attempts, made_shots, points, turnovers, three_made):
    shot_attempts = shot_attempts or 0
    made_shots = made_shots or 0
    points = points or 0
    turnovers = turnovers or 0
    three_made = three_made or 0

    possessions = shot_attempts + turnovers
    ppp = (points / possessions) if possessions > 0 else 0
    tov_pct = _safe_pct(turnovers, possessions)
    score_pct = _safe_pct(made_shots, possessions)
    fg_pct = _safe_pct(made_shots, shot_attempts)
    efg_pct = (
        round(((made_shots + 0.5 * three_made) / shot_attempts) * 100, 1)
        if shot_attempts > 0
        else 0.0
    )

    return {
        "possessions": possessions,
        "ppp": round(ppp, 2),
        "tov_pct": tov_pct,
        "score_pct": score_pct,
        "fg_pct": fg_pct,
        "efg_pct": efg_pct,
    }


def get_untracked_percentages(game_id: int):
    """Return untracked coverage percentages (no counts shown in UI).

    Play tagging applies primarily to 2pt/3pt shots and turnovers, so FT are excluded.
    """

    # Shots (exclude FT)
    shot_totals = (
        db.session.query(
            func.count(ShotEvent.id).label("total"),
            func.sum(case((ShotEvent.play_id.is_(None), 1), else_=0)).label("untracked"),
        )
        .filter(
            ShotEvent.game_id == game_id,
            ShotEvent.shot_type.in_(["2pt", "3pt"]),
        )
        .first()
    )

    total_shots = int(getattr(shot_totals, "total", 0) or 0)
    untracked_shots = int(getattr(shot_totals, "untracked", 0) or 0)

    # Turnovers
    tov_totals = (
        db.session.query(
            func.count(GameEvent.id).label("total"),
            func.sum(case((GameEvent.play_id.is_(None), 1), else_=0)).label("untracked"),
        )
        .filter(
            GameEvent.game_id == game_id,
            GameEvent.event_type == "TURNOVER",
        )
        .first()
    )

    total_tov = int(getattr(tov_totals, "total", 0) or 0)
    untracked_tov = int(getattr(tov_totals, "untracked", 0) or 0)

    total_poss = total_shots + total_tov
    untracked_poss = untracked_shots + untracked_tov

    return {
        "untracked_shots_pct": _safe_pct(untracked_shots, total_shots),
        "untracked_turnovers_pct": _safe_pct(untracked_tov, total_tov),
        "untracked_possessions_pct": _safe_pct(untracked_poss, total_poss),
    }


def get_play_stats(game_id, play_type="Offense"):
    """Calculate comprehensive stats for plays in a specific game.

    Includes both shot events and turnovers.
    """

    # 1. Fetch all plays of the requested type
    plays = Play.query.filter_by(play_type=play_type).all()
    play_map = {p.id: p for p in plays}

    if not plays:
        return []

    # 2. Query Shot Events (Grouped by Play)
    shot_stats = (
        db.session.query(
            ShotEvent.play_id,
            func.count(ShotEvent.id).label("shot_attempts"),
            func.sum(case((ShotEvent.result == "made", 1), else_=0)).label("made_shots"),
            func.sum(ShotEvent.points).label("points_scored"),
            func.sum(case((ShotEvent.shot_type == "3pt", 1), else_=0)).label("three_attempts"),
            func.sum(
                case(
                    (and_(ShotEvent.shot_type == "3pt", ShotEvent.result == "made"), 1),
                    else_=0,
                )
            ).label("three_made"),
        )
        .filter(
            ShotEvent.game_id == game_id,
            ShotEvent.play_id.isnot(None),
            ShotEvent.shot_type.in_(["2pt", "3pt"]),
        )
        .group_by(ShotEvent.play_id)
        .all()
    )

    # 3. Query Turnover Events (Grouped by Play)
    turnover_stats = (
        db.session.query(GameEvent.play_id, func.count(GameEvent.id).label("turnovers"))
        .filter(
            GameEvent.game_id == game_id,
            GameEvent.play_id.isnot(None),
            GameEvent.event_type == "TURNOVER",
        )
        .group_by(GameEvent.play_id)
        .all()
    )

    # 4. Merge Data
    stats_by_play = {}

    # Initialize entries for all plays that have events
    active_play_ids = set([s.play_id for s in shot_stats] + [t.play_id for t in turnover_stats])

    for play_id in active_play_ids:
        if play_id not in play_map:
            continue

        play_name = play_map[play_id].name
        stats_by_play[play_id] = {
            "id": play_id,
            "name": play_name,
            "shot_attempts": 0,
            "made_shots": 0,
            "points": 0,
            "turnovers": 0,
            "three_attempts": 0,
            "three_made": 0,
        }

    # Fill Shot Data
    for row in shot_stats:
        if row.play_id in stats_by_play:
            stats_by_play[row.play_id]["shot_attempts"] = row.shot_attempts or 0
            stats_by_play[row.play_id]["made_shots"] = row.made_shots or 0
            stats_by_play[row.play_id]["points"] = row.points_scored or 0
            stats_by_play[row.play_id]["three_attempts"] = row.three_attempts or 0
            stats_by_play[row.play_id]["three_made"] = row.three_made or 0

    # Fill Turnover Data
    for row in turnover_stats:
        if row.play_id in stats_by_play:
            stats_by_play[row.play_id]["turnovers"] = row.turnovers or 0

    # 5. Calculate Advanced Metrics
    final_stats = []

    for pid, data in stats_by_play.items():
        metrics = _calc_metrics(
            data["shot_attempts"],
            data["made_shots"],
            data["points"],
            data["turnovers"],
            data["three_made"],
        )

        if metrics["possessions"] == 0:
            continue

        final_stats.append(
            {
                "id": pid,
                "name": data["name"],
                "possessions": metrics["possessions"],
                "points": data["points"],
                "ppp": metrics["ppp"],
                "turnovers": data["turnovers"],
                "tov_pct": metrics["tov_pct"],
                "score_pct": metrics["score_pct"],
                "made_shots": data["made_shots"],
                "shot_attempts": data["shot_attempts"],
                "fg_pct": metrics["fg_pct"],
                "efg_pct": metrics["efg_pct"],
            }
        )

    # Sort by frequency (possessions) descending
    final_stats.sort(key=lambda x: x["possessions"], reverse=True)

    return final_stats


def get_play_player_stats(game_id: int, play_type: str = "Offense"):
    """Play -> Players breakdown for a single game (tracked plays only)."""

    plays = Play.query.filter_by(play_type=play_type).all()
    play_map = {p.id: p for p in plays}
    if not plays:
        return []

    shot_rows = (
        db.session.query(
            ShotEvent.play_id,
            ShotEvent.player_name,
            func.count(ShotEvent.id).label("shot_attempts"),
            func.sum(case((ShotEvent.result == "made", 1), else_=0)).label("made_shots"),
            func.sum(ShotEvent.points).label("points_scored"),
            func.sum(
                case(
                    (and_(ShotEvent.shot_type == "3pt", ShotEvent.result == "made"), 1),
                    else_=0,
                )
            ).label("three_made"),
        )
        .filter(
            ShotEvent.game_id == game_id,
            ShotEvent.play_id.isnot(None),
            ShotEvent.shot_type.in_(["2pt", "3pt"]),
        )
        .group_by(ShotEvent.play_id, ShotEvent.player_name)
        .all()
    )

    tov_rows = (
        db.session.query(
            GameEvent.play_id,
            GameEvent.player_name,
            func.count(GameEvent.id).label("turnovers"),
        )
        .filter(
            GameEvent.game_id == game_id,
            GameEvent.play_id.isnot(None),
            GameEvent.event_type == "TURNOVER",
        )
        .group_by(GameEvent.play_id, GameEvent.player_name)
        .all()
    )

    # build: play_id -> player -> stats
    data = {}

    def ensure(play_id, player_name):
        if play_id not in play_map:
            return None
        if play_id not in data:
            data[play_id] = {
                "id": play_id,
                "name": play_map[play_id].name,
                "players": {},
            }
        if player_name not in data[play_id]["players"]:
            data[play_id]["players"][player_name] = {
                "player_name": player_name,
                "shot_attempts": 0,
                "made_shots": 0,
                "points": 0,
                "turnovers": 0,
                "three_made": 0,
            }
        return data[play_id]["players"][player_name]

    for r in shot_rows:
        entry = ensure(r.play_id, r.player_name)
        if not entry:
            continue
        entry["shot_attempts"] = int(r.shot_attempts or 0)
        entry["made_shots"] = int(r.made_shots or 0)
        entry["points"] = int(r.points_scored or 0)
        entry["three_made"] = int(r.three_made or 0)

    for r in tov_rows:
        entry = ensure(r.play_id, r.player_name)
        if not entry:
            continue
        entry["turnovers"] = int(r.turnovers or 0)

    # finalize
    plays_out = []
    for play_id, play_block in data.items():
        players_out = []
        for player_name, s in play_block["players"].items():
            metrics = _calc_metrics(
                s["shot_attempts"],
                s["made_shots"],
                s["points"],
                s["turnovers"],
                s["three_made"],
            )
            if metrics["possessions"] == 0:
                continue
            players_out.append(
                {
                    "player_name": player_name,
                    "possessions": metrics["possessions"],
                    "points": s["points"],
                    "ppp": metrics["ppp"],
                    "turnovers": s["turnovers"],
                    "tov_pct": metrics["tov_pct"],
                    "shot_attempts": s["shot_attempts"],
                    "made_shots": s["made_shots"],
                    "fg_pct": metrics["fg_pct"],
                    "efg_pct": metrics["efg_pct"],
                }
            )

        if not players_out:
            continue

        players_out.sort(key=lambda x: x["possessions"], reverse=True)
        plays_out.append({"id": play_block["id"], "name": play_block["name"], "players": players_out})

    plays_out.sort(key=lambda x: sum(p["possessions"] for p in x["players"]), reverse=True)
    return plays_out


def get_player_play_stats(game_id: int, play_type: str = "Offense"):
    """Player -> Plays breakdown for a single game (tracked plays only)."""

    by_play = get_play_player_stats(game_id, play_type=play_type)
    player_map = {}

    for play in by_play:
        for p in play.get("players", []):
            name = p["player_name"]
            if name not in player_map:
                player_map[name] = {"player_name": name, "plays": []}
            player_map[name]["plays"].append(
                {
                    "id": play["id"],
                    "name": play["name"],
                    "possessions": p["possessions"],
                    "points": p["points"],
                    "ppp": p["ppp"],
                    "turnovers": p["turnovers"],
                    "tov_pct": p["tov_pct"],
                    "fg_pct": p["fg_pct"],
                    "efg_pct": p["efg_pct"],
                }
            )

    out = list(player_map.values())
    for row in out:
        row["plays"].sort(key=lambda x: x["possessions"], reverse=True)

    out.sort(key=lambda r: sum(p["possessions"] for p in r["plays"]), reverse=True)
    return out
