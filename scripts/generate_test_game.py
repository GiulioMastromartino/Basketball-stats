"""
Comprehensive test game generator for basketball stats.

Generates a complete, realistic game payload with:
- 10 players (5 starters, 5 bench)
- Chronologically ordered events across 4 quarters
- Shot locations with zone classification (Rim, Paint, Midrange, Corner_3, Above_Break_3)
- Play association for each shot
- Variable scoring and timing
- Lineup tracking
"""

import json
import hashlib
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import sys
import os
sys.path.append(os.getcwd())
from core import rust_analytics

# =============================================================================
# SHOT ZONE CONSTANTS
# =============================================================================

# Court coordinates: 0-500 (x), 0-470 (y), basket at (250, 50)
# x=0 is left sideline, x=500 is right sideline
# y=0 is baseline, y=470 is opposite end

SHOT_ZONES = {
    'Rim': {
        'x_range': (220, 280),
        'y_range': (40, 100),
        'fg_pct': 0.65,
        'description': 'Layups/dunks at the basket'
    },
    'Paint': {
        'x_range': (150, 350),
        'y_range': (50, 150),
        'fg_pct': 0.45,
        'description': 'Shots in the paint (non-rim)'
    },
    'Midrange': {
        'x_range': (100, 400),
        'y_range': (100, 280),
        'fg_pct': 0.38,
        'description': 'Mid-range jumpers'
    },
    'Corner_3': {
        'x_range': [(30, 100), (400, 470)],  # Two corners
        'y_range': (50, 140),
        'fg_pct': 0.38,
        'description': 'Corner 3-pointers'
    },
    'Above_Break_3': {
        'x_range': (80, 420),
        'y_range': (180, 400),
        'fg_pct': 0.35,
        'description': 'Above-the-break 3-pointers'
    },
}

# Zone distribution for 2PT shots
TWO_PT_ZONE_WEIGHTS = {
    'Rim': 0.35,
    'Paint': 0.30,
    'Midrange': 0.35,
}

# Zone distribution for 3PT shots
THREE_PT_ZONE_WEIGHTS = {
    'Corner_3': 0.35,
    'Above_Break_3': 0.65,
}

# Free throw line location (centered at x=250, y~150)
FT_LOCATION = {
    'x': 250.0,
    'y': 150.0,
}


# =============================================================================
# OFFENSIVE PLAYS
# =============================================================================

OFFENSIVE_PLAYS = [
    {"name": "Pick and Roll", "weight": 0.20},
    {"name": "Horns Twist", "weight": 0.08},
    {"name": "Spain PNR", "weight": 0.06},
    {"name": "Dribble Handoff", "weight": 0.10},
    {"name": "Pick and Pop", "weight": 0.08},
    {"name": "Transition Offense", "weight": 0.12},
    {"name": "Ball Screen", "weight": 0.10},
    {"name": "Isolation", "weight": 0.08},
    {"name": "Flare Screen", "weight": 0.06},
    {"name": "Motion Offense", "weight": 0.06},
    {"name": "Post Up", "weight": 0.04},
    {"name": "Drive and Kick", "weight": 0.02},
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_zone_for_shot_type(shot_type: str) -> str:
    """Select an appropriate zone based on shot type and zone weights."""
    if shot_type == "2pt":
        zones = list(TWO_PT_ZONE_WEIGHTS.keys())
        weights = list(TWO_PT_ZONE_WEIGHTS.values())
    elif shot_type == "3pt":
        zones = list(THREE_PT_ZONE_WEIGHTS.keys())
        weights = list(THREE_PT_ZONE_WEIGHTS.values())
    else:
        return 'Midrange'
    
    return random.choices(zones, weights=weights)[0]


def _get_shot_location_for_zone(zone: str) -> Tuple[float, float]:
    """Generate x, y coordinates for a specific zone."""
    zone_data = SHOT_ZONES.get(zone, SHOT_ZONES['Midrange'])
    
    x_range = zone_data['x_range']
    y_range = zone_data['y_range']
    
    # Handle corner 3 which has two possible x ranges
    if isinstance(x_range, list):
        # x_range is a list of tuples like [(30, 100), (400, 470)]
        chosen_range = random.choice(x_range)
        x = float(random.randint(chosen_range[0], chosen_range[1]))
    else:
        x = float(random.randint(x_range[0], x_range[1]))
    
    y = float(random.randint(y_range[0], y_range[1]))
    
    return x, y


def _get_shot_location(shot_type: str, zone: Optional[str] = None) -> Tuple[float, float, str]:
    """
    Generate shot location coordinates.
    
    Args:
        shot_type: '2pt', '3pt', or 'opp'
        zone: Optional specific zone. If None, selects based on shot type.
    
    Returns:
        Tuple of (x, y, zone_name)
    """
    if shot_type == "opp":
        # Opponent shots - random location
        x = float(random.randint(200, 300))
        y = float(random.randint(30, 120))
        return x, y, 'Paint'
    
    if zone is None:
        zone = _get_zone_for_shot_type(shot_type)
    
    x, y = _get_shot_location_for_zone(zone)
    return x, y, zone


def _classify_shot_zone(x_loc: float, y_loc: float, shot_type: str) -> str:
    """
    Classify a shot into a zone based on court coordinates.
    Uses high-performance Rust implementation.
    """
    return rust_analytics.classify_shot_zone(x_loc, y_loc, shot_type)


def _get_make_probability(zone: str) -> float:
    """Get make probability for a zone with some randomness."""
    base_pct = SHOT_ZONES.get(zone, SHOT_ZONES['Midrange'])['fg_pct']
    # Add ±5% variance
    variance = random.uniform(-0.05, 0.05)
    return max(0.20, min(0.75, base_pct + variance))


def _select_play() -> Dict:
    """Select a random play based on weights."""
    plays = [p['name'] for p in OFFENSIVE_PLAYS]
    weights = [p['weight'] for p in OFFENSIVE_PLAYS]
    play_name = random.choices(plays, weights=weights)[0]
    return {"name": play_name, "play_type": "Offense"}


def _generate_variable_scores() -> Tuple[int, int]:
    """Generate variable final scores with team winning."""
    # Higher score range for more realistic games
    team_score = random.randint(78, 102)
    # Opponent scores slightly lower (team wins)
    opp_score = team_score - random.randint(3, 12)
    
    return team_score, opp_score


def _distribute_quarter_scoring(team_total: int, opp_total: int) -> Dict[int, Dict[str, int]]:
    """Distribute total scoring across 4 quarters with variability."""
    quarters = {1: {}, 2: {}, 3: {}, 4: {}}
    
    # Distribute team score
    remaining = team_total
    for q in range(1, 5):
        if q == 4:
            quarters[q]['team'] = remaining
        else:
            # Average quarter score with ±30% variance
            avg = team_total / 4
            score = int(avg * random.uniform(0.7, 1.3))
            score = max(10, min(30, score))  # Clamp between 10-30
            score = min(score, remaining - (4 - q) * 10)  # Leave enough for remaining quarters
            quarters[q]['team'] = score
            remaining -= score
    
    # Distribute opponent score
    remaining = opp_total
    for q in range(1, 5):
        if q == 4:
            quarters[q]['opp'] = remaining
        else:
            avg = opp_total / 4
            score = int(avg * random.uniform(0.7, 1.3))
            score = max(10, min(28, score))
            score = min(score, remaining - (4 - q) * 10)
            quarters[q]['opp'] = score
            remaining -= score
    
    return quarters


def _generate_variable_sub_schedule() -> List[Tuple[int, int, List[Tuple[str, str]]]]:
    """Generate substitution schedule with timing variability."""
    base_schedule = [
        (1, [("Davis", "Miller")]),
        (1, [("Brown", "Wilson")]),
        (2, [("Williams", "Moore"), ("Smith", "Taylor")]),
        (2, [("Miller", "Davis"), ("Wilson", "Brown")]),
        (3, [("Moore", "Williams"), ("Taylor", "Smith")]),
        (3, [("Davis", "Anderson"), ("Brown", "Wilson")]),
        (4, [("Anderson", "Davis"), ("Wilson", "Brown"), ("Moore", "Williams")]),
        (4, [("Miller", "Taylor")]),
    ]
    
    variable_schedule = []
    for quarter, subs in base_schedule:
        # Add ±60 seconds variance to timing
        base_time = random.randint(360, 540) if quarter in [1, 3] else random.randint(240, 480)
        # Ensure subs happen at different times within the quarter
        for i, sub in enumerate(subs):
            sub_time = base_time + i * 60 + random.randint(-30, 30)
            sub_time = max(60, min(580, sub_time))  # Keep within quarter
            variable_schedule.append((quarter, sub_time, [sub]))
    
    return variable_schedule


def _create_empty_stats(name: str) -> Dict:
    """Create empty player stats dict."""
    return {
        "player_name": name,
        "points": 0,
        "minutes": "00:00",
        "reb": 0,
        "ast": 0,
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
        "stl": 0,
        "blk": 0,
        "tov": 0,
        "pf": random.randint(1, 4),
        "plus_minus": random.randint(-5, 15),
        "reb_conceded": 0,
    }


def _generate_lineup_segments(events: List[Dict], starters: List[str], bench: List[str]) -> List[Dict]:
    """Generate lineup segments tracking which players are on court."""
    segments = []
    current_lineup = starters.copy()
    segment_id = 1

    start_ts = events[0]["timestamp"] if events else 0
    start_game_seconds = events[0].get("game_seconds", 0) if events else 0
    current_quarter = 1

    for i, event in enumerate(events):
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

                    lineup_hash = rust_analytics.calculate_lineup_hash(current_lineup)

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

    lineup_hash = rust_analytics.calculate_lineup_hash(current_lineup)

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


def _finalize_player_stats(stats: Dict, players: List[Dict]) -> List[Dict]:
    """Finalize and format player statistics."""
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


# =============================================================================
# MAIN GENERATOR FUNCTION
# =============================================================================

def generate_test_game_payload():
    """
    Generate a comprehensive test game payload with:
    - Variable scoring
    - Zone-aware shot locations
    - Play association for each shot
    - Realistic shot distribution
    """

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
    opponent_shot_events = []  # Track opponent shots separately
    player_stats = {p["name"]: _create_empty_stats(p["name"]) for p in players}

    # Generate variable scores
    final_team_score, final_opp_score = _generate_variable_scores()
    quarter_scoring = _distribute_quarter_scoring(final_team_score, final_opp_score)

    team_score = 0
    opp_score = 0
    timestamp = 1700000000000
    event_id = 1
    shot_id = 1

    # Generate variable substitution schedule
    sub_schedule = _generate_variable_sub_schedule()

    # Track plays used in this game for play_id assignment
    plays_used = {}  # play_name -> play_id (would be assigned by DB)
    play_counter = 1

    for quarter in range(1, 5):
        quarter_events = []
        quarter_start_seconds = (quarter - 1) * 600

        q_team_score = quarter_scoring[quarter]["team"]
        q_opp_score = quarter_scoring[quarter]["opp"]
        
        # Track opponent score for THIS quarter specifically
        q_opp_score_tracker = 0
        
        # Track team score for THIS quarter specifically  
        q_team_score_tracker = 0

        # Calculate shot distribution for this quarter (team)
        shots_2pt = int(q_team_score * 0.50) // 2  # ~50% of points from 2pt
        shots_3pt = int(q_team_score * 0.35) // 3  # ~35% of points from 3pt
        fts = q_team_score - (shots_2pt * 2) - (shots_3pt * 3)
        
        # Ensure non-negative
        fts = max(0, fts)

        made_2pt = shots_2pt
        made_3pt = shots_3pt

        for minute in range(10, 0, -1):
            # Add variability to timing
            second_in_minute = random.randint(0, 59)
            timing_variance = random.randint(-50, 50)
            
            game_seconds = quarter_start_seconds + (
                600 - minute * 60 - second_in_minute
            )
            time_remaining = f"{minute:02d}:{(60 - second_in_minute) % 60:02d}"
            ts = (
                timestamp
                + (quarter_start_seconds + (600 - minute * 60 - second_in_minute))
                * 1000
                + timing_variance
            )

            # Handle substitutions with variable timing
            for q, q_time, subs in sub_schedule:
                if q == quarter and abs(q_time // 60 - minute) <= 1:
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

            # 2PT shots with zone and play tracking
            if minute in [9, 8, 7, 6, 5, 4, 3, 2, 1] and made_2pt > 0:
                shooter = random.choice(current_lineup)
                
                # Select zone and get location
                zone = _get_zone_for_shot_type("2pt")
                x, y = _get_shot_location_for_zone(zone)
                
                # Zone-aware make probability with dynamic adjustment
                make_prob = _get_make_probability(zone)
                # Increase make rate if we need more points this quarter
                remaining_team_pts = q_team_score - q_team_score_tracker
                if remaining_team_pts > made_2pt * 2:
                    make_prob = min(0.80, make_prob + 0.20)
                is_made = random.random() < make_prob
                
                # Select play
                play = _select_play()
                play_name = play["name"]
                
                # Assign play_id (simulated - in real usage would be from DB)
                if play_name not in plays_used:
                    plays_used[play_name] = play_counter
                    play_counter += 1
                play_id = plays_used[play_name]

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "SHOT_2PT",
                        "player_name": shooter,
                        "detail": json.dumps({"zone": zone, "play_name": play_name}),
                        "timestamp": ts,
                        "shot_attempt": "made" if is_made else "missed",
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                        "x_loc": x,
                        "y_loc": y,
                        "zone": zone,
                        "play_id": play_id,
                        "play_name": play_name,
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
                        "zone": zone,
                        "play_id": play_id,
                        "play_name": play_name,
                    }
                )
                shot_id += 1

                player_stats[shooter]["fga"] += 1
                if is_made:
                    player_stats[shooter]["fgm"] += 1
                    player_stats[shooter]["points"] += 2
                    team_score += 2
                    q_team_score_tracker += 2
                    made_2pt -= 1
                    
                    # Assist chance varies by zone (higher for Rim/Paint)
                    assist_chance = 0.6 if zone in ['Rim', 'Paint'] else 0.4
                    if random.random() < assist_chance:
                        passer = random.choice(
                            [p for p in current_lineup if p != shooter]
                        )
                        quarter_events.append(
                            {
                                "id": event_id,
                                "event_type": "AST",
                                "player_name": passer,
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
                        player_stats[passer]["ast"] += 1
                else:
                    # Rebound on miss
                    rebounder = random.choice(current_lineup)
                    is_oreb = random.random() > 0.6
                    reb_type = "OREB" if is_oreb else "DREB"
                    quarter_events.append(
                        {
                            "id": event_id,
                            "event_type": reb_type,
                            "player_name": rebounder,
                            "detail": None,
                            "timestamp": ts + 50,
                            "shot_attempt": None,
                            "quarter": quarter,
                            "time_remaining": time_remaining,
                            "score_margin": team_score - opp_score,
                            "game_seconds": game_seconds,
                        }
                    )
                    event_id += 1
                    if is_oreb:
                        player_stats[rebounder]["oreb"] += 1
                    else:
                        player_stats[rebounder]["dreb"] += 1
                    player_stats[rebounder]["reb"] += 1

            # 3PT shots with zone and play tracking
            if minute in [8, 6, 4, 2] and made_3pt > 0:
                shooter = random.choice(current_lineup)
                
                # Select zone (Corner_3 or Above_Break_3)
                zone = _get_zone_for_shot_type("3pt")
                x, y = _get_shot_location_for_zone(zone)
                
                # Zone-aware make probability with dynamic adjustment
                make_prob = _get_make_probability(zone)
                # Increase make rate if we need more points this quarter
                remaining_team_pts = q_team_score - q_team_score_tracker
                if remaining_team_pts > made_3pt * 3:
                    make_prob = min(0.75, make_prob + 0.20)
                is_made = random.random() < make_prob
                
                # Select play
                play = _select_play()
                play_name = play["name"]
                
                if play_name not in plays_used:
                    plays_used[play_name] = play_counter
                    play_counter += 1
                play_id = plays_used[play_name]

                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "SHOT_3PT",
                        "player_name": shooter,
                        "detail": json.dumps({"zone": zone, "play_name": play_name}),
                        "timestamp": ts,
                        "shot_attempt": "made" if is_made else "missed",
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                        "x_loc": x,
                        "y_loc": y,
                        "zone": zone,
                        "play_id": play_id,
                        "play_name": play_name,
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
                        "zone": zone,
                        "play_id": play_id,
                        "play_name": play_name,
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
                    q_team_score_tracker += 3
                    made_3pt -= 1
                    
                    # Higher assist rate on 3s
                    if random.random() < 0.5:
                        passer = random.choice(
                            [p for p in current_lineup if p != shooter]
                        )
                        quarter_events.append(
                            {
                                "id": event_id,
                                "event_type": "AST",
                                "player_name": passer,
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
                        player_stats[passer]["ast"] += 1

            # Free throws
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
                        "zone": "FT",
                        "x_loc": FT_LOCATION['x'],
                        "y_loc": FT_LOCATION['y'],
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
                            "zone": "FT",
                        "x_loc": FT_LOCATION['x'],
                        "y_loc": FT_LOCATION['y'],
                    }
                )
                event_id += 1

                player_stats[shooter]["fta"] += fta
                player_stats[shooter]["ftm"] += ftm
                player_stats[shooter]["points"] += ftm
                team_score += ftm
                q_team_score_tracker += ftm
                fts -= ftm

            # Random rebounds
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

            # Turnovers with variable frequency
            if minute in [8, 5, 2]:
                turnover_player = random.choice(current_lineup)

                if random.random() > 0.5:
                    quarter_events.append(
                        {
                            "id": event_id,
                            "event_type": "STL",
                            "player_name": None,
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

                        # Opponent shots generated based on quarter score target
            # Generate opponent shots throughout the quarter to match target score
            if minute in [9, 8, 7, 6, 5, 4, 3, 2, 1] and q_opp_score_tracker < q_opp_score:
                # Probability of shot this minute based on remaining needed
                remaining_to_score = q_opp_score - q_opp_score_tracker
                minutes_left = minute if minute > 0 else 1
                shot_probability = min(0.95, remaining_to_score / (minutes_left * 2.5))
                
                if random.random() < shot_probability:
                    # Determine shot type and zone
                    opp_shot_type = random.choices(["2pt", "3pt"], weights=[0.65, 0.35])[0]
                    opp_zone = _get_zone_for_shot_type(opp_shot_type)
                    x, y = _get_shot_location_for_zone(opp_zone)
                    
                    # Get make probability for zone
                    base_make_prob = _get_make_probability(opp_zone) - 0.05
                    opp_make_prob = max(0.20, min(0.70, base_make_prob))
                    
                    # Dynamically adjust make probability to meet target
                    # If we need a lot of points, increase make rate
                    if remaining_to_score > 0:
                        # Boost make probability proportionally
                        boost = min(0.40, remaining_to_score * 0.08)
                        opp_make_prob = min(0.85, opp_make_prob + boost)
                    
                    opp_is_made = random.random() < opp_make_prob
                    
                    if opp_is_made:
                        opp_points = 3 if opp_shot_type == "3pt" else 2
                        opp_score += opp_points
                        q_opp_score_tracker += opp_points
                        
                        quarter_events.append(
                            {
                                "id": event_id,
                                "event_type": "OPP_SCORE",
                                "player_name": None,
                                "detail": json.dumps(
                                    {"points": opp_points, "result": "made", "zone": opp_zone}
                                ),
                                "timestamp": ts + 400,
                                "shot_attempt": None,
                                "quarter": quarter,
                                "time_remaining": time_remaining,
                                "score_margin": team_score - opp_score,
                                "game_seconds": game_seconds,
                                "x_loc": x,
                                "y_loc": y,
                                "zone": opp_zone,
                            }
                        )
                        event_id += 1
                        
                        # Track opponent made shot
                        opponent_shot_events.append({
                            "id": len(opponent_shot_events) + 1,
                            "player_name": "Opponent",
                            "shot_type": opp_shot_type,
                            "result": "made",
                            "points": opp_points,
                            "x_loc": x,
                            "y_loc": y,
                            "quarter": quarter,
                            "zone": opp_zone,
                            "play_id": None,
                            "play_name": None,
                        })
                    else:
                        # Opponent missed shot
                        quarter_events.append(
                            {
                                "id": event_id,
                                "event_type": "OPP_MISS",
                                "player_name": None,
                                "detail": json.dumps(
                                    {"points": 0, "result": "missed", "zone": opp_zone, "shot_type": opp_shot_type}
                                ),
                                "timestamp": ts + 400,
                                "shot_attempt": None,
                                "quarter": quarter,
                                "time_remaining": time_remaining,
                                "score_margin": team_score - opp_score,
                                "game_seconds": game_seconds,
                                "x_loc": x,
                                "y_loc": y,
                                "zone": opp_zone,
                            }
                        )
                        event_id += 1
                        
                        # Track opponent missed shot
                        opponent_shot_events.append({
                            "id": len(opponent_shot_events) + 1,
                            "player_name": "Opponent",
                            "shot_type": opp_shot_type,
                            "result": "missed",
                            "points": 0,
                            "x_loc": x,
                            "y_loc": y,
                            "quarter": quarter,
                            "zone": opp_zone,
                            "play_id": None,
                            "play_name": None,
                        })
                        
                        # Rebound after miss
                        reb_chance = random.random()
                        if reb_chance < 0.70:  # 70% team defensive rebound
                            rebounder = random.choice(current_lineup)
                            quarter_events.append(
                                {
                                    "id": event_id,
                                    "event_type": "DREB",
                                    "player_name": rebounder,
                                    "detail": None,
                                    "timestamp": ts + 450,
                                    "shot_attempt": None,
                                    "quarter": quarter,
                                    "time_remaining": time_remaining,
                                    "score_margin": team_score - opp_score,
                                    "game_seconds": game_seconds,
                                }
                            )
                            event_id += 1
                            player_stats[rebounder]["dreb"] += 1
                            player_stats[rebounder]["reb"] += 1
                        else:  # 30% opponent offensive rebound
                            quarter_events.append(
                                {
                                    "id": event_id,
                                    "event_type": "OPP_OREB",
                                    "player_name": None,
                                    "detail": None,
                                    "timestamp": ts + 450,
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

            # Blocks with variable frequency
            if minute in [7, 3]:
                blocker = random.choice(current_lineup)
                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "BLK",
                        "player_name": blocker,
                        "detail": None,
                        "timestamp": ts + 450,
                        "shot_attempt": None,
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                    }
                )
                event_id += 1
                player_stats[blocker]["blk"] += 1

            # Steals with variable frequency
            if minute in [6, 2]:
                stealer = random.choice(current_lineup)
                quarter_events.append(
                    {
                        "id": event_id,
                        "event_type": "STL",
                        "player_name": stealer,
                        "detail": None,
                        "timestamp": ts + 350,
                        "shot_attempt": None,
                        "quarter": quarter,
                        "time_remaining": time_remaining,
                        "score_margin": team_score - opp_score,
                        "game_seconds": game_seconds,
                    }
                )
                event_id += 1
                player_stats[stealer]["stl"] += 1

            # Opponent offensive rebounds
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

        events.extend(sorted(quarter_events, key=lambda x: x["timestamp"]))

    # Use actual tracked scores from the events
    # (final_team_score and final_opp_score were targets, actual may differ slightly)
    # Team score is already tracked accurately in team_score
    # Opponent score is tracked in opp_score during generation

    lineup_segments = _generate_lineup_segments(events, starter_names, bench_names)

    final_player_stats = _finalize_player_stats(player_stats, players)

    # Convert shot_events to shot_locations format with zone and play info
    shot_locations = []
    for s in shot_events:
        shot_locations.append(
            {
                "shooter": s["player_name"],
                "type": s["shot_type"],
                "result": s["result"],
                "points": s["points"],
                "x": s.get("x_loc", 250),
                "y": s.get("y_loc", 150),
                "quarter": s["quarter"],
                "zone": s.get("zone", "Midrange"),
                "play_id": s.get("play_id"),
                "play_name": s.get("play_name"),
                "is_opponent": False,
            }
        )
    
    # Add opponent shots to shot_locations
    for s in opponent_shot_events:
        shot_locations.append(
            {
                "shooter": s["player_name"],
                "type": s["shot_type"],
                "result": s["result"],
                "points": s["points"],
                "x": s.get("x_loc", 250),
                "y": s.get("y_loc", 150),
                "quarter": s["quarter"],
                "zone": s.get("zone", "Midrange"),
                "play_id": s.get("play_id"),
                "play_name": s.get("play_name"),
                "is_opponent": True,
            }
        )

    # Create plays list for reference (these would be created in DB on import)
    plays_list = [
        {"id": pid, "name": pname, "play_type": "Offense"}
        for pname, pid in plays_used.items()
    ]

    game_data = {
        "game": {
            "id": 1,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "opponent": "Test Opponents",
            "team_score": team_score,
            "opponent_score": opp_score,
            "result": "W" if team_score > opp_score else "L",
            "game_type": "Season",
            "sort_date": datetime.now().strftime("%Y-%m-%d"),
            "source": "TEST_GENERATOR",
        },
        "players": players,
        "starting_lineup": starter_names,
        "game_events": events,
        "shot_events": shot_events,
        "opponent_shot_events": opponent_shot_events,
        "shot_locations": shot_locations,
        "player_stats": final_player_stats,
        "lineup_segments": lineup_segments,
        "plays": plays_list,  # NEW: List of plays used in this game
        "metadata": {
            "total_events": len(events),
            "total_shots": len(shot_events),
            "total_opponent_shots": len(opponent_shot_events),
            "total_lineup_combinations": len(
                set(seg["lineup_hash"] for seg in lineup_segments)
            ),
            "total_plays_used": len(plays_used),
            "generated_at": datetime.now().isoformat(),
            "schema_version": 3,  # Bumped for new fields
            "zones_used": list(set(s.get("zone", "Midrange") for s in shot_events)),
        },
        "features": {
            "LINEUP_TRACKING": True,
            "SHOT_ZONES": True,
            "PLAY_TRACKING": True,
        },
        # Top-level fields for create_game_from_live_data (flat format)
        "date": datetime.now().strftime("%Y-%m-%d"),
        "opponent": "Test Opponents",
        "team_score": team_score,
        "opponent_score": opp_score,
        "game_type": "Season",
        "schema_version": 3,
    }

    return game_data


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import gc
    import psutil
    
    process = psutil.Process(os.getpid())
    print(f"Initial Memory Usage: {process.memory_info().rss / 1024 / 1024:.1f} MB")
    
    payload = generate_test_game_payload()
    gc.collect()
    
    print(f"Memory after payload generation: {process.memory_info().rss / 1024 / 1024:.1f} MB")

    print(f"Generated test game payload:")
    print(
        f"  - Score: {payload['game']['team_score']} - {payload['game']['opponent_score']}"
    )
    print(f"  - Total events: {payload['metadata']['total_events']}")
    print(f"  - Total shots: {payload['metadata']['total_shots']}")
    print(f"  - Total plays used: {payload['metadata']['total_plays_used']}")
    print(f"  - Zones used: {payload['metadata']['zones_used']}")
    print(
        f"  - Lineup combinations: {payload['metadata']['total_lineup_combinations']}"
    )
    print(f"  - Players: {len(payload['players'])}")

    output_path = "/Users/giuliomastromartino/Documents/basket/Game_STATS/Basketball_Stats/Basketball-stats/test_game_payload.json"
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"\nPayload saved to: {output_path}")
