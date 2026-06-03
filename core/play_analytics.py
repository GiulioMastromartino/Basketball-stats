import json

from sqlalchemy import case, func

from core.models import GameEvent, Play, ShotEvent, db


SHOT_TYPES = ("2pt", "3pt")
SUMMARY_EVENT_TYPES = ("SHOT_2PT", "SHOT_3PT", "TURNOVER", "FT", "FT_MADE", "FT_MISS")


def _safe_pct(numerator, denominator):
    return round((numerator / denominator) * 100, 1) if denominator and denominator > 0 else 0.0


def _parse_detail(detail):
    if detail is None:
        return {}
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        try:
            parsed = json.loads(detail)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
    return {}


def _calc_metrics(shot_attempts, made_shots, points, turnovers, three_made):
    shot_attempts = shot_attempts or 0
    made_shots = made_shots or 0
    points = points or 0
    turnovers = turnovers or 0
    three_made = three_made or 0

    possessions = shot_attempts + turnovers
    return {
        "possessions": possessions,
        "ppp": round((points / possessions), 2) if possessions > 0 else 0.0,
        "tov_pct": _safe_pct(turnovers, possessions),
        "score_pct": _safe_pct(made_shots, possessions),
        "fg_pct": _safe_pct(made_shots, shot_attempts),
        "efg_pct": (
            round(((made_shots + 0.5 * three_made) / shot_attempts) * 100, 1)
            if shot_attempts > 0
            else 0.0
        ),
    }


def _play_map(play_type):
    plays = Play.query.filter_by(play_type=play_type).all()
    return {play.id: play for play in plays}


def _legacy_shot_stats(game_id, play_ids):
    return (
        db.session.query(
            ShotEvent.play_id,
            func.count(ShotEvent.id).label("shot_attempts"),
            func.sum(case((ShotEvent.result == "made", 1), else_=0)).label("made_shots"),
            func.sum(ShotEvent.points).label("points_scored"),
            func.sum(case((ShotEvent.shot_type == "3pt", 1), else_=0)).label("three_attempts"),
            func.sum(
                case(
                    ((ShotEvent.shot_type == "3pt") & (ShotEvent.result == "made"), 1),
                    else_=0,
                )
            ).label("three_made"),
        )
        .filter(
            ShotEvent.game_id == game_id,
            ShotEvent.play_id.in_(play_ids),
            ShotEvent.shot_type.in_(SHOT_TYPES),
        )
        .group_by(ShotEvent.play_id)
        .all()
    )


def _legacy_turnover_stats(game_id, play_ids):
    return (
        db.session.query(GameEvent.play_id, func.count(GameEvent.id).label("turnovers"))
        .filter(
            GameEvent.game_id == game_id,
            GameEvent.play_id.in_(play_ids),
            GameEvent.event_type == "TURNOVER",
        )
        .group_by(GameEvent.play_id)
        .all()
    )


def _legacy_player_shot_stats(game_id, play_ids):
    return (
        db.session.query(
            ShotEvent.play_id,
            ShotEvent.player_name,
            func.count(ShotEvent.id).label("shot_attempts"),
            func.sum(case((ShotEvent.result == "made", 1), else_=0)).label("made_shots"),
            func.sum(ShotEvent.points).label("points_scored"),
            func.sum(
                case(
                    ((ShotEvent.shot_type == "3pt") & (ShotEvent.result == "made"), 1),
                    else_=0,
                )
            ).label("three_made"),
        )
        .filter(
            ShotEvent.game_id == game_id,
            ShotEvent.play_id.in_(play_ids),
            ShotEvent.shot_type.in_(SHOT_TYPES),
        )
        .group_by(ShotEvent.play_id, ShotEvent.player_name)
        .all()
    )


def _legacy_player_turnover_stats(game_id, play_ids):
    return (
        db.session.query(
            GameEvent.play_id,
            GameEvent.player_name,
            func.count(GameEvent.id).label("turnovers"),
        )
        .filter(
            GameEvent.game_id == game_id,
            GameEvent.play_id.in_(play_ids),
            GameEvent.event_type == "TURNOVER",
        )
        .group_by(GameEvent.play_id, GameEvent.player_name)
        .all()
    )


def get_play_stats(game_id, play_type="Offense"):
    play_map = _play_map(play_type)
    if not play_map:
        return []

    stats_by_play = {
        play_id: {
            "id": play_id,
            "name": play.name,
            "shot_attempts": 0,
            "made_shots": 0,
            "points": 0,
            "turnovers": 0,
            "three_made": 0,
        }
        for play_id, play in play_map.items()
    }

    for row in _legacy_shot_stats(game_id, list(play_map.keys())):
        stats_by_play[row.play_id]["shot_attempts"] = int(row.shot_attempts or 0)
        stats_by_play[row.play_id]["made_shots"] = int(row.made_shots or 0)
        stats_by_play[row.play_id]["points"] = int(row.points_scored or 0)
        stats_by_play[row.play_id]["three_made"] = int(row.three_made or 0)

    for row in _legacy_turnover_stats(game_id, list(play_map.keys())):
        stats_by_play[row.play_id]["turnovers"] = int(row.turnovers or 0)

    final_stats = []
    for play_id, payload in stats_by_play.items():
        metrics = _calc_metrics(
            payload["shot_attempts"],
            payload["made_shots"],
            payload["points"],
            payload["turnovers"],
            payload["three_made"],
        )
        if metrics["possessions"] == 0:
            continue
        final_stats.append(
            {
                "id": play_id,
                "name": payload["name"],
                "possessions": metrics["possessions"],
                "points": payload["points"],
                "ppp": metrics["ppp"],
                "turnovers": payload["turnovers"],
                "tov_pct": metrics["tov_pct"],
                "score_pct": metrics["score_pct"],
                "made_shots": payload["made_shots"],
                "shot_attempts": payload["shot_attempts"],
                "fg_pct": metrics["fg_pct"],
                "efg_pct": metrics["efg_pct"],
            }
        )

    final_stats.sort(key=lambda row: row["possessions"], reverse=True)
    return final_stats


def get_play_player_stats(game_id: int, play_type: str = "Offense"):
    play_map = _play_map(play_type)
    if not play_map:
        return []

    data = {}

    def ensure(play_id, player_name):
        if play_id not in play_map:
            return None
        if play_id not in data:
            data[play_id] = {"id": play_id, "name": play_map[play_id].name, "players": {}}
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

    for row in _legacy_player_shot_stats(game_id, list(play_map.keys())):
        entry = ensure(row.play_id, row.player_name or "Unknown")
        if not entry:
            continue
        entry["shot_attempts"] = int(row.shot_attempts or 0)
        entry["made_shots"] = int(row.made_shots or 0)
        entry["points"] = int(row.points_scored or 0)
        entry["three_made"] = int(row.three_made or 0)

    for row in _legacy_player_turnover_stats(game_id, list(play_map.keys())):
        entry = ensure(row.play_id, row.player_name or "Unknown")
        if not entry:
            continue
        entry["turnovers"] = int(row.turnovers or 0)

    plays_out = []
    for play_id, play_block in data.items():
        players_out = []
        for player_name, payload in play_block["players"].items():
            metrics = _calc_metrics(
                payload["shot_attempts"],
                payload["made_shots"],
                payload["points"],
                payload["turnovers"],
                payload["three_made"],
            )
            if metrics["possessions"] == 0:
                continue
            players_out.append(
                {
                    "player_name": player_name,
                    "possessions": metrics["possessions"],
                    "points": payload["points"],
                    "ppp": metrics["ppp"],
                    "turnovers": payload["turnovers"],
                    "tov_pct": metrics["tov_pct"],
                    "shot_attempts": payload["shot_attempts"],
                    "made_shots": payload["made_shots"],
                    "fg_pct": metrics["fg_pct"],
                    "efg_pct": metrics["efg_pct"],
                }
            )

        if players_out:
            players_out.sort(key=lambda row: row["possessions"], reverse=True)
            plays_out.append({"id": play_block["id"], "name": play_block["name"], "players": players_out})

    plays_out.sort(key=lambda row: sum(player["possessions"] for player in row["players"]), reverse=True)
    return plays_out


def get_player_play_stats(game_id: int, play_type: str = "Offense"):
    by_play = get_play_player_stats(game_id, play_type=play_type)
    player_map = {}

    for play in by_play:
        for player in play["players"]:
            player_row = player_map.setdefault(player["player_name"], {"player_name": player["player_name"], "plays": []})
            player_row["plays"].append(
                {
                    "id": play["id"],
                    "name": play["name"],
                    "possessions": player["possessions"],
                    "points": player["points"],
                    "ppp": player["ppp"],
                    "turnovers": player["turnovers"],
                    "tov_pct": player["tov_pct"],
                    "fg_pct": player["fg_pct"],
                    "efg_pct": player["efg_pct"],
                }
            )

    result = list(player_map.values())
    for player in result:
        player["plays"].sort(key=lambda row: row["possessions"], reverse=True)
    result.sort(key=lambda row: sum(play["possessions"] for play in row["plays"]), reverse=True)
    return result


def _summary_bucket():
    return {
        "possessions": set(),
        "score_possessions": set(),
        "points": 0,
        "turnovers": 0,
        "shot_attempts": 0,
        "made_shots": 0,
        "three_made": 0,
        "estimated_possessions": False,
    }


def _summary_finalize(name, payload, estimated=False, entity_id=None):
    possessions = len(payload["possessions"])
    if possessions == 0:
        return None

    row = {
        "name": name,
        "possessions": possessions,
        "points": payload["points"],
        "ppp": round((payload["points"] / possessions), 2),
        "turnovers": payload["turnovers"],
        "tov_pct": _safe_pct(payload["turnovers"], possessions),
        "score_pct": _safe_pct(len(payload["score_possessions"]), possessions),
        "made_shots": payload["made_shots"],
        "shot_attempts": payload["shot_attempts"],
        "fg_pct": _safe_pct(payload["made_shots"], payload["shot_attempts"]),
        "efg_pct": (
            round(((payload["made_shots"] + 0.5 * payload["three_made"]) / payload["shot_attempts"]) * 100, 1)
            if payload["shot_attempts"] > 0
            else 0.0
        ),
        "estimated_possessions": estimated or payload["estimated_possessions"],
    }
    if entity_id is not None:
        row["id"] = entity_id
    return row


def _consume_matching_shot(remaining_shots, event):
    player_name = event.player_name or ""
    expected_type = "3pt" if event.event_type == "SHOT_3PT" else "2pt"
    expected_result = event.shot_attempt if event.shot_attempt in ("made", "missed") else None

    exact = [
        shot
        for shot in remaining_shots
        if shot.play_id == event.play_id
        and (shot.player_name or "") == player_name
        and shot.quarter == event.quarter
        and shot.shot_type == expected_type
        and (expected_result is None or shot.result == expected_result)
    ]
    if exact:
        chosen = exact[0]
        remaining_shots.remove(chosen)
        return chosen

    broad = [
        shot
        for shot in remaining_shots
        if shot.play_id == event.play_id
        and (shot.player_name or "") == player_name
        and shot.quarter == event.quarter
        and shot.shot_type == expected_type
    ]
    if expected_result is None and broad:
        chosen = broad[0]
        remaining_shots.remove(chosen)
        return chosen
    return None


def _summary_ft_has_outcome(event):
    if event.event_type == "FT_MADE":
        return True
    if event.event_type == "FT_MISS":
        return True
    if event.event_type == "FT":
        detail = _parse_detail(event.detail)
        return int(detail.get("fta", 0) or 0) > 0 or int(detail.get("ftm", 0) or 0) > 0
    return False


def _summary_ft_points(event):
    if event.event_type == "FT_MADE":
        return 1
    if event.event_type == "FT":
        detail = _parse_detail(event.detail)
        return int(detail.get("ftm", 0) or 0)
    return 0


def _summary_fallback(game_id, play_map):
    play_rows = {}
    player_rows = {}

    shot_rows = (
        ShotEvent.query.filter(
            ShotEvent.game_id == game_id,
            ShotEvent.play_id.in_(list(play_map.keys())),
            ShotEvent.shot_type.in_(SHOT_TYPES),
        )
        .order_by(ShotEvent.id.asc())
        .all()
    )
    event_rows = (
        GameEvent.query.filter(
            GameEvent.game_id == game_id,
            GameEvent.play_id.in_(list(play_map.keys())),
            GameEvent.event_type.in_(("TURNOVER", "FT", "FT_MADE", "FT_MISS")),
        )
        .order_by(GameEvent.timestamp.asc(), GameEvent.id.asc())
        .all()
    )

    for shot in shot_rows:
        play_bucket = play_rows.setdefault(shot.play_id, _summary_bucket())
        player_bucket = player_rows.setdefault((shot.play_id, shot.player_name or "Unknown"), _summary_bucket())
        for bucket in (play_bucket, player_bucket):
            bucket["estimated_possessions"] = True
            bucket["possessions"].add(("shot", shot.id))
            bucket["shot_attempts"] += 1
            if shot.result == "made":
                bucket["made_shots"] += 1
                bucket["points"] += int(shot.points or 0)
                bucket["score_possessions"].add(("shot", shot.id))
                if shot.shot_type == "3pt":
                    bucket["three_made"] += 1

    for event in event_rows:
        if event.event_type.startswith("FT") and not _summary_ft_has_outcome(event):
            continue
        play_bucket = play_rows.setdefault(event.play_id, _summary_bucket())
        player_bucket = player_rows.setdefault((event.play_id, event.player_name or "Unknown"), _summary_bucket())
        identity = ("event", event.id)
        points = _summary_ft_points(event)
        for bucket in (play_bucket, player_bucket):
            bucket["estimated_possessions"] = True
            bucket["possessions"].add(identity)
            if event.event_type == "TURNOVER":
                bucket["turnovers"] += 1
            else:
                bucket["points"] += points
                if points > 0:
                    bucket["score_possessions"].add(identity)

    return play_rows, player_rows


def _collect_summary_play_analysis(game_id, play_type="Offense"):
    play_map = _play_map(play_type)
    if not play_map:
        return {"plays": [], "play_players": [], "player_plays": [], "estimated_possessions": False}

    play_ids = list(play_map.keys())
    relevant_events = (
        GameEvent.query.filter(
            GameEvent.game_id == game_id,
            GameEvent.play_id.in_(play_ids),
            GameEvent.event_type.in_(SUMMARY_EVENT_TYPES),
        )
        .order_by(GameEvent.possession_number.asc(), GameEvent.timestamp.asc(), GameEvent.id.asc())
        .all()
    )
    use_possession_mode = bool(relevant_events) and all(
        event.possession_number is not None for event in relevant_events
    )

    play_rows = {}
    player_rows = {}

    if use_possession_mode:
        remaining_shots = (
            ShotEvent.query.filter(
                ShotEvent.game_id == game_id,
                ShotEvent.play_id.in_(play_ids),
                ShotEvent.shot_type.in_(SHOT_TYPES),
            )
            .order_by(ShotEvent.id.asc())
            .all()
        )

        for event in relevant_events:
            possession_number = event.possession_number
            player_name = event.player_name or "Unknown"
            play_bucket = play_rows.setdefault(event.play_id, _summary_bucket())
            player_bucket = player_rows.setdefault((event.play_id, player_name), _summary_bucket())

            if event.event_type in ("SHOT_2PT", "SHOT_3PT"):
                matched_shot = _consume_matching_shot(remaining_shots, event)
                if not matched_shot:
                    continue
                for bucket in (play_bucket, player_bucket):
                    bucket["possessions"].add(possession_number)
                    bucket["shot_attempts"] += 1
                    if matched_shot.result == "made":
                        bucket["made_shots"] += 1
                        bucket["points"] += int(matched_shot.points or 0)
                        bucket["score_possessions"].add(possession_number)
                        if matched_shot.shot_type == "3pt":
                            bucket["three_made"] += 1
            elif event.event_type == "TURNOVER":
                for bucket in (play_bucket, player_bucket):
                    bucket["possessions"].add(possession_number)
                    bucket["turnovers"] += 1
            elif _summary_ft_has_outcome(event):
                points = _summary_ft_points(event)
                for bucket in (play_bucket, player_bucket):
                    bucket["possessions"].add(possession_number)
                    bucket["points"] += points
                    if points > 0:
                        bucket["score_possessions"].add(possession_number)
    else:
        play_rows, player_rows = _summary_fallback(game_id, play_map)

    plays = []
    for play_id, payload in play_rows.items():
        row = _summary_finalize(
            play_map[play_id].name,
            payload,
            estimated=not use_possession_mode,
            entity_id=play_id,
        )
        if row:
            plays.append(row)
    plays.sort(key=lambda row: row["possessions"], reverse=True)

    play_players = []
    for play_id, play in play_map.items():
        players = []
        for (player_play_id, player_name), payload in player_rows.items():
            if player_play_id != play_id:
                continue
            row = _summary_finalize(player_name, payload, estimated=not use_possession_mode)
            if row:
                row["player_name"] = row.pop("name")
                players.append(row)
        if players:
            players.sort(key=lambda row: row["possessions"], reverse=True)
            play_players.append(
                {
                    "id": play_id,
                    "name": play.name,
                    "players": players,
                    "estimated_possessions": not use_possession_mode,
                }
            )
    play_players.sort(key=lambda row: sum(player["possessions"] for player in row["players"]), reverse=True)

    player_map = {}
    for play in play_players:
        for player in play["players"]:
            player_row = player_map.setdefault(player["player_name"], {"player_name": player["player_name"], "plays": []})
            player_row["plays"].append(
                {
                    "id": play["id"],
                    "name": play["name"],
                    "possessions": player["possessions"],
                    "points": player["points"],
                    "ppp": player["ppp"],
                    "turnovers": player["turnovers"],
                    "tov_pct": player["tov_pct"],
                    "fg_pct": player["fg_pct"],
                    "efg_pct": player["efg_pct"],
                    "score_pct": player["score_pct"],
                    "shot_attempts": player["shot_attempts"],
                    "made_shots": player["made_shots"],
                    "estimated_possessions": player["estimated_possessions"],
                }
            )

    player_plays = list(player_map.values())
    for player in player_plays:
        player["plays"].sort(key=lambda row: row["possessions"], reverse=True)
    player_plays.sort(key=lambda row: sum(play["possessions"] for play in row["plays"]), reverse=True)

    return {
        "plays": plays,
        "play_players": play_players,
        "player_plays": player_plays,
        "estimated_possessions": not use_possession_mode,
    }


def get_summary_play_stats(game_id, play_type="Offense"):
    return _collect_summary_play_analysis(game_id, play_type=play_type)["plays"]


def get_summary_play_player_stats(game_id: int, play_type: str = "Offense"):
    return _collect_summary_play_analysis(game_id, play_type=play_type)["play_players"]


def get_summary_player_play_stats(game_id: int, play_type: str = "Offense"):
    return _collect_summary_play_analysis(game_id, play_type=play_type)["player_plays"]


def get_player_top_plays_by_points(game_id: int, limit: int = 3, play_type: str = "Offense"):
    player_plays = get_player_play_stats(game_id, play_type=play_type)
    result = {}
    for entry in player_plays:
        plays = sorted(entry["plays"], key=lambda play: (play["points"], play["possessions"]), reverse=True)
        result[entry["player_name"]] = plays[:limit]
    return result


def get_summary_player_top_plays_by_points(game_id: int, limit: int = 3, play_type: str = "Offense"):
    player_plays = get_summary_player_play_stats(game_id, play_type=play_type)
    result = {}
    for entry in player_plays:
        plays = sorted(entry["plays"], key=lambda play: (play["points"], play["possessions"]), reverse=True)
        result[entry["player_name"]] = plays[:limit]
    return result


def get_untracked_percentages(game_id: int):
    shot_events = (
        db.session.query(
            func.count(GameEvent.id).label("total"),
            func.sum(case((GameEvent.play_id.is_(None), 1), else_=0)).label("untracked"),
        )
        .filter(
            GameEvent.game_id == game_id,
            GameEvent.event_type.in_(("SHOT_2PT", "SHOT_3PT")),
        )
        .first()
    )

    total_shots = int(getattr(shot_events, "total", 0) or 0)
    untracked_shots = int(getattr(shot_events, "untracked", 0) or 0)

    turnover_events = (
        db.session.query(
            func.count(GameEvent.id).label("total"),
            func.sum(case((GameEvent.play_id.is_(None), 1), else_=0)).label("untracked"),
        )
        .filter(GameEvent.game_id == game_id, GameEvent.event_type == "TURNOVER")
        .first()
    )

    total_tov = int(getattr(turnover_events, "total", 0) or 0)
    untracked_tov = int(getattr(turnover_events, "untracked", 0) or 0)
    total_poss = total_shots + total_tov
    untracked_poss = untracked_shots + untracked_tov

    return {
        "untracked_shots_pct": _safe_pct(untracked_shots, total_shots),
        "untracked_turnovers_pct": _safe_pct(untracked_tov, total_tov),
        "untracked_possessions_pct": _safe_pct(untracked_poss, total_poss),
    }
