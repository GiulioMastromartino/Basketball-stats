"""
Comprehensive test game generator for basketball stats.

Generates a complete, realistic game payload with:
- 10 players (5 starters, 5 bench)
- Chronologically ordered events across 4 quarters
- Shot locations, lineup tracking, timeline fields
- Final score around 85-78
"""

import json
import hashlib
import random
from datetime import datetime


def generate_test_game_payload():
    """Generate a comprehensive test game payload."""

    players = [
        {"name": "Smith", "is_starter": True, "minutes": 28},
        {"name": "Johnson", "is_starter": True, "minutes": 25},
        {"name": "Williams", "is_starter": True, "minutes": 24},
        {"name": "Brown", "is_starter": True, "minutes": 22},
        {"name": "Davis", "is_starter": True, "minutes": 20},
        {"name": "Miller", "is_starter": False, "minutes": 15},
        {"name": "Wilson", "is_starter": False, "minutes": 14},
        {"name": "Moore", "is_starter": False, "minutes": 12},
        {"name": "Taylor", "is_starter": False, "minutes": 10},
        {"name": "Anderson", "is_starter": False, "minutes": 8},
    ]

    starter_names = [p["name"] for p in players if p["is_starter"]]
    bench_names = [p["name"] for p in players if not p["is_starter"]]

    current_lineup = starter_names.copy()

    events = []
    shot_events = []
    player_stats = {p["name"]: _create_empty_stats(p["name"]) for p in players}

    team_score = 0
    opp_score = 0
    timestamp = 1700000000000
    event_id = 1
    shot_id = 1

    quarter_minutes = {1: 10, 2: 10, 3: 10, 4: 10}

    sub_schedule = [
        (1, 480, [("Davis", "Miller")]),
        (1, 300, [("Brown", "Wilson")]),
        (2, 540, [("Williams", "Moore"), ("Smith", "Taylor")]),
        (2, 300, [("Miller", "Davis"), ("Wilson", "Brown")]),
        (3, 480, [("Moore", "Williams"), ("Taylor", "Smith")]),
        (3, 240, [("Davis", "Anderson"), ("Brown", "Wilson")]),
        (4, 480, [("Anderson", "Davis"), ("Wilson", "Brown"), ("Moore", "Williams")]),
        (4, 180, [("Miller", "Taylor")]),
    ]

    quarter_scoring = {
        1: {"team": 20, "opp": 18},
        2: {"team": 22, "opp": 20},
        3: {"team": 23, "opp": 22},
        4: {"team": 20, "opp": 18},
    }

    for quarter in range(1, 5):
        quarter_events = []
        quarter_start_seconds = (quarter - 1) * 600

        q_team_score = quarter_scoring[quarter]["team"]
        q_opp_score = quarter_scoring[quarter]["opp"]

        shots_2pt = int(q_team_score * 0.55) // 2
        shots_3pt = int(q_team_score * 0.35) // 3
        fts = q_team_score - (shots_2pt * 2) - (shots_3pt * 3)

        made_2pt = shots_2pt
        made_3pt = shots_3pt

        for minute in range(10, 0, -1):
            second_in_minute = random.randint(0, 59)
            game_seconds = quarter_start_seconds + (
                600 - minute * 60 - second_in_minute
            )
            time_remaining = f"{minute:02d}:{(60 - second_in_minute) % 60:02d}"
            ts = (
                timestamp
                + (quarter_start_seconds + (600 - minute * 60 - second_in_minute))
                * 1000
            )

            for q, q_time, subs in sub_schedule:
                if q == quarter and q_time // 60 == minute:
                    for out_player, in_player in subs:
                        if out_player in current_lineup:
                            quarter_events.append(
                                {
                                    "id": event_id,
                                    "event_type": "SUB_OUT",
                                    "player_name": out_player,
                                    "detail": None,
                                    "timestamp": ts,
                                    "shot_attempt": None,
                                    "quarter": quarter,
                                    "time_remaining": time_remaining,
                                    "score_margin": team_score - opp_score,
                                    "game_seconds": game_seconds,
                                }
                            )
                            event_id += 1
                            ts += 100

                            quarter_events.append(
                                {
                                    "id": event_id,
                                    "event_type": "SUB_IN",
                                    "player_name": in_player,
                                    "detail": None,
                                    "timestamp": ts,
                                    "shot_attempt": None,
                                    "quarter": quarter,
                                    "time_remaining": time_remaining,
                                    "score_margin": team_score - opp_score,
                                    "game_seconds": game_seconds,
                                }
                            )
                            event_id += 1

                            idx = current_lineup.index(out_player)
                            current_lineup[idx] = in_player

            if minute in [9, 7, 5, 3, 1] and made_2pt > 0:
                shooter = random.choice(current_lineup)
                is_made = random.random() > 0.4
                x, y = _get_shot_location("2pt")

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "SHOT_2PT",
                        "player_name": shooter,
                        "detail": None,
                        "timestamp": ts,
                        "shot_attempt": "made" if is_made else "missed",
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                        "x_loc": x,
                        "y_loc": y,
                    }
                )
                event_id += 1

                shot_events.append(
                    {
                        "id": shot_id,
                        "player_name": shooter,
                        "shot_type": "2pt",
                        "result": "made" if is_made else "missed",
                        "points": 2 if is_made else 0,
                        "x_loc": x,
                        "y_loc": y,
                        "quarter": quarter,
                    }
                )
                shot_id += 1

                player_stats[shooter]["fga"] += 1
                if is_made:
                    player_stats[shooter]["fgm"] += 1
                    player_stats[shooter]["points"] += 2
                    team_score += 2
                    made_2pt -= 1

            if minute in [8, 4] and made_3pt > 0:
                shooter = random.choice(current_lineup)
                is_made = random.random() > 0.6
                x, y = _get_shot_location("3pt")

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "SHOT_3PT",
                        "player_name": shooter,
                        "detail": None,
                        "timestamp": ts,
                        "shot_attempt": "made" if is_made else "missed",
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                        "x_loc": x,
                        "y_loc": y,
                    }
                )
                event_id += 1

                shot_events.append(
                    {
                        "id": shot_id,
                        "player_name": shooter,
                        "shot_type": "3pt",
                        "result": "made" if is_made else "missed",
                        "points": 3 if is_made else 0,
                        "x_loc": x,
                        "y_loc": y,
                        "quarter": quarter,
                    }
                )
                shot_id += 1

                player_stats[shooter]["tpa"] += 1
                player_stats[shooter]["fga"] += 1
                if is_made:
                    player_stats[shooter]["tpm"] += 1
                    player_stats[shooter]["fgm"] += 1
                    player_stats[shooter]["points"] += 3
                    team_score += 3
                    made_3pt -= 1

            if minute in [6, 2] and fts > 0:
                shooter = random.choice(current_lineup)
                ftm = min(fts, random.randint(1, 2))
                fta = ftm + random.randint(0, 1)

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "FT",
                        "player_name": shooter,
                        "detail": json.dumps({"ftm": ftm, "fta": fta}),
                        "timestamp": ts,
                        "shot_attempt": None,
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                    }
                )
                event_id += 1

                for i in range(fta):
                    is_made = i < ftm
                    quarter_events.append(
                        {
                            "id": event_id,
                            "event_type": "FT_MADE" if is_made else "FT_MISS",
                            "player_name": shooter,
                            "detail": None,
                            "timestamp": ts + (i + 1) * 50,
                            "shot_attempt": None,
                            "quarter": quarter,
                            "time_remaining": time_remaining,
                            "score_margin": team_score - opp_score,
                            "game_seconds": game_seconds,
                        }
                    )
                    event_id += 1

                player_stats[shooter]["fta"] += fta
                player_stats[shooter]["ftm"] += ftm
                player_stats[shooter]["points"] += ftm
                team_score += ftm
                fts -= ftm

            if minute in [9, 6, 3]:
                reb_type = random.choice(["OREB", "DREB"])
                rebounder = random.choice(current_lineup)

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": reb_type,
                        "player_name": rebounder,
                        "detail": None,
                        "timestamp": ts + 200,
                        "shot_attempt": None,
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                    }
                )
                event_id += 1

                if reb_type == "OREB":
                    player_stats[rebounder]["oreb"] += 1
                else:
                    player_stats[rebounder]["dreb"] += 1
                player_stats[rebounder]["reb"] += 1

            if minute in [8, 5, 2]:
                turnover_player = random.choice(current_lineup)

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "TURNOVER",
                        "player_name": turnover_player,
                        "detail": None,
                        "timestamp": ts + 300,
                        "shot_attempt": None,
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                    }
                )
                event_id += 1
                player_stats[turnover_player]["tov"] += 1

            if minute in [9, 7, 5, 3, 1]:
                opp_points = random.choice([0, 2, 2, 2, 3])
                if opp_points > 0 and opp_score < quarter_scoring[quarter]["opp"] + 5:
                    opp_score += opp_points
                    x, y = _get_shot_location("opp")

                    quarter_events.append(
                        {
                            "id": event_id,
                            "event_type": "OPP_SCORE",
                            "player_name": None,
                            "detail": json.dumps(
                                {"points": opp_points, "result": "made"}
                            ),
                            "timestamp": ts + 400,
                            "shot_attempt": None,
                            "quarter": quarter,
                            "time_remaining": time_remaining,
                            "score_margin": team_score - opp_score,
                            "game_seconds": game_seconds,
                            "x_loc": x,
                            "y_loc": y,
                        }
                    )
                    event_id += 1

            if minute in [4, 1]:
                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "OPP_OREB",
                        "player_name": None,
                        "detail": None,
                        "timestamp": ts + 500,
                        "shot_attempt": None,
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                    }
                )
                event_id += 1

                for p in current_lineup:
                    player_stats[p]["reb_conceded"] += 1

        events.extend(
            sorted(quarter_events, key=lambda x: x["game_seconds"], reverse=True)
        )

    team_score = 85
    opp_score = 78

    lineup_segments = _generate_lineup_segments(events, starter_names, bench_names)

    final_player_stats = _finalize_player_stats(player_stats, players)

    # Convert shot_events to shot_locations format for create_game_from_live_data
    shot_locations = []
    for s in shot_events:
        shot_locations.append({
            "shooter": s["player_name"],
            "type": s["shot_type"],
            "result": s["result"],
            "points": s["points"],
            "x": s.get("x_loc", 250),
            "y": s.get("y_loc", 150),
            "quarter": s["quarter"],
            "play_id": None,
        })

    # Keep player_stats as list for nested import format
    # (create_game_from_live_data expects list when "game" key is present)

    game_data = {
        "game": {
            "id": 1,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "opponent": "Test Opponents",
            "team_score": team_score,
            "opponent_score": opp_score,
            "result": "W",
            "game_type": "Season",
            "sort_date": datetime.now().strftime("%Y-%m-%d"),
            "source": "TEST_GENERATOR",
        },
        "players": players,
        "starting_lineup": starter_names,
        "game_events": events,
        "shot_events": shot_events,
        "shot_locations": shot_locations,
        "player_stats": final_player_stats,
        "lineup_segments": lineup_segments,
        "metadata": {
            "total_events": len(events),
            "total_shots": len(shot_events),
            "total_lineup_combinations": len(
                set(seg["lineup_hash"] for seg in lineup_segments)
            ),
            "generated_at": datetime.now().isoformat(),
            "schema_version": 2,
        },
        "features": {
            "LINEUP_TRACKING": True,
        },
        # Top-level fields for create_game_from_live_data (flat format)
        "date": datetime.now().strftime("%Y-%m-%d"),
        "opponent": "Test Opponents",
        "team_score": team_score,
        "opponent_score": opp_score,
        "game_type": "Season",
        "schema_version": 2,
    }

    return game_data


def _create_empty_stats(name):
    return {
        "player_name": name,
        "points": 0,
        "minutes": "00:00",
        "reb": 0,
        "ast": random.randint(0, 5),
        "fgm": 0,
        "fga": 0,
        "fg_percent": 0.0,
        "tpm": 0,
        "tpa": 0,
        "tp_percent": 0.0,
        "ftm": 0,
        "fta": 0,
        "ft_percent": 0.0,
        "oreb": 0,
        "dreb": 0,
        "stl": random.randint(0, 3),
        "blk": random.randint(0, 2),
        "tov": 0,
        "pf": random.randint(1, 4),
        "plus_minus": random.randint(-5, 15),
        "reb_conceded": 0,
    }


def _get_shot_location(shot_type):
    if shot_type == "2pt":
        x = random.randint(150, 350)
        y = random.randint(50, 200)
    elif shot_type == "3pt":
        if random.random() > 0.5:
            x = random.randint(50, 120)
            y = random.randint(100, 300)
        else:
            x = random.randint(380, 450)
            y = random.randint(100, 300)
    else:
        x = random.randint(200, 300)
        y = random.randint(30, 80)
    return float(x), float(y)


def _generate_lineup_segments(events, starters, bench):
    segments = []
    current_lineup = starters.copy()
    segment_id = 1

    start_ts = events[0]["timestamp"] if events else 0
    start_game_seconds = events[0].get("game_seconds", 0) if events else 0
    current_quarter = 1

    for i, event in enumerate(events):
        if event["event_type"] == "SUB_OUT":
            player_out = event["player_name"]
            if player_out in current_lineup:
                pass

        if event["event_type"] == "SUB_IN":
            player_in = event["player_name"]
            sub_out_event = None
            for j in range(i - 1, max(0, i - 5), -1):
                if events[j]["event_type"] == "SUB_OUT":
                    sub_out_event = events[j]
                    break

            if sub_out_event:
                player_out = sub_out_event["player_name"]
                if player_out in current_lineup:
                    idx = current_lineup.index(player_out)
                    current_lineup[idx] = player_in

                    sorted_players = sorted(current_lineup)
                    lineup_hash = hashlib.md5(
                        ",".join(sorted_players).encode()
                    ).hexdigest()

                    segments.append(
                        {
                            "id": segment_id,
                            "start_timestamp": start_ts,
                            "end_timestamp": event["timestamp"],
                            "quarter": current_quarter,
                            "players": current_lineup.copy(),
                            "lineup_hash": lineup_hash,
                            "points_scored": random.randint(2, 8),
                            "points_allowed": random.randint(2, 6),
                            "possessions": random.randint(3, 6),
                            "duration_seconds": event.get("game_seconds", 0)
                            - start_game_seconds,
                        }
                    )
                    segment_id += 1

                    start_ts = event["timestamp"]
                    start_game_seconds = event.get("game_seconds", 0)
                    current_quarter = event.get("quarter", current_quarter)

        if event.get("quarter", 1) != current_quarter:
            current_quarter = event.get("quarter", current_quarter)

    sorted_players = sorted(current_lineup)
    lineup_hash = hashlib.md5(",".join(sorted_players).encode()).hexdigest()

    segments.append(
        {
            "id": segment_id,
            "start_timestamp": start_ts,
            "end_timestamp": None,
            "quarter": current_quarter,
            "players": current_lineup.copy(),
            "lineup_hash": lineup_hash,
            "points_scored": random.randint(2, 8),
            "points_allowed": random.randint(2, 6),
            "possessions": random.randint(3, 6),
            "duration_seconds": 60,
        }
    )

    return segments


def _finalize_player_stats(stats, players):
    final_stats = []
    for player in players:
        name = player["name"]
        p = stats[name]

        p["minutes"] = f"{player['minutes']:02d}:{random.randint(0, 59):02d}"

        if p["fga"] > 0:
            p["fg_percent"] = round((p["fgm"] / p["fga"]) * 100, 1)
        if p["tpa"] > 0:
            p["tp_percent"] = round((p["tpm"] / p["tpa"]) * 100, 1)
        if p["fta"] > 0:
            p["ft_percent"] = round((p["ftm"] / p["fta"]) * 100, 1)

        p["reb"] = p["oreb"] + p["dreb"]

        final_stats.append(p)

    return final_stats


if __name__ == "__main__":
    payload = generate_test_game_payload()

    print(f"Generated test game payload:")
    print(
        f"  - Score: {payload['game']['team_score']} - {payload['game']['opponent_score']}"
    )
    print(f"  - Total events: {payload['metadata']['total_events']}")
    print(f"  - Total shots: {payload['metadata']['total_shots']}")
    print(
        f"  - Lineup combinations: {payload['metadata']['total_lineup_combinations']}"
    )
    print(f"  - Players: {len(payload['players'])}")

    output_path = "/Users/giuliomastromartino/Documents/basket/Game_STATS/Basketball_Stats/Basketball-stats/test_game_payload.json"
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nPayload saved to: {output_path}")
