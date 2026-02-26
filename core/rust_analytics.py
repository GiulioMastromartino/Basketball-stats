"""
Basketball Stats Rust - High-performance analytics Python wrapper
"""

import json
from typing import Dict, List, Optional
from itertools import combinations
from collections import defaultdict

# Try to import Rust library
RUST_AVAILABLE = False
try:
    from basketball_stats import (
        classify_shot_zone as rust_classify_shot_zone,
        get_expected_value as rust_get_expected_value,
        calculate_true_usage_rate as rust_calculate_true_usage_rate,
        calculate_points_per_shot as rust_calculate_points_per_shot,
        calculate_shot_quality_delta as rust_calculate_shot_quality_delta,
        calculate_shot_quality_score as rust_calculate_shot_quality_score,
        parse_time_to_seconds as rust_parse_time_to_seconds,
        seconds_to_time as rust_seconds_to_time,
        safe_div as rust_safe_div,
        safe_percentage as rust_safe_percentage,
        calculate_possessions as rust_calculate_possessions,
        calculate_efg_pct as rust_calculate_efg_pct,
        calculate_true_shooting_pct as rust_calculate_true_shooting_pct,
        calculate_pace as rust_calculate_pace,
        calculate_offensive_rating as rust_calculate_offensive_rating,
        calculate_defensive_rating as rust_calculate_defensive_rating,
        calculate_net_rating as rust_calculate_net_rating,
        calculate_assist_ratio as rust_calculate_assist_ratio,
        calculate_turnover_ratio as rust_calculate_turnover_ratio,
        calculate_rebound_rate as rust_calculate_rebound_rate,
        is_clutch_situation as rust_is_clutch_situation,
        calculate_game_flow as rust_calculate_game_flow,
        aggregate_combinatorial_stats as rust_aggregate_combinatorial_stats,
        reconstruct_possessions_rust as rust_reconstruct_possessions_rust,
        calculate_lineup_hash as rust_calculate_lineup_hash,
    )
    RUST_AVAILABLE = True
    print("High-performance Rust analytics engine LOADED.")
except ImportError:
    print("Rust analytics library NOT FOUND. Falling back to pure Python (slower).")
    pass

# =============================================================================
# Pure Python Fallbacks
# =============================================================================

def _python_classify_shot_zone(x_loc: Optional[float], y_loc: Optional[float], shot_type: str) -> str:
    if not shot_type: return 'Midrange'
    st = shot_type.lower()
    if st == 'ft': return 'FT'
    if x_loc is None or y_loc is None: return 'Midrange'
    
    dx = x_loc - 250
    dy = y_loc - 50
    distance = (dx**2 + dy**2)**0.5
    
    if distance <= 40: return 'Rim'
    elif distance <= 100: return 'Paint'
    elif '3pt' in st:
        if y_loc < 140: return 'Corner_3'
        return 'Above_Break_3'
    else:
        return 'Midrange'

def _python_get_expected_value(zone: str) -> float:
    DEFAULT_ZONE_VALUES = {
        'Rim': 1.20, 'Paint': 0.85, 'Midrange': 0.75,
        'Corner_3': 1.10, 'Above_Break_3': 1.05, 'FT': 0.75,
    }
    return DEFAULT_ZONE_VALUES.get(zone, 0.80)

def _python_safe_percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100 * 10) / 10, 1) if denominator > 0 else 0.0

def _python_calculate_possessions(fga: int, fta: int, oreb: int, tov: int) -> float:
    return fga + (0.44 * fta) - oreb + tov

def _python_calculate_offensive_rating(points: int, possessions: float) -> float:
    return round((points / possessions * 100), 1) if possessions > 0 else 0.0

def _python_calculate_true_shooting_pct(points: int, fga: int, fta: int) -> float:
    denominator = 2 * (fga + 0.44 * fta)
    return round((points / denominator * 100), 2) if denominator > 0 else 0.0

def _python_calculate_efg_pct(fgm: int, tpm: int, fga: int) -> float:
    return round(((fgm + 0.5 * tpm) / fga * 100), 1) if fga > 0 else 0.0

def _python_calculate_lineup_hash(players: List[str]) -> str:
    import hashlib
    sorted_players = sorted(players)
    return hashlib.md5(",".join(sorted_players).encode()).hexdigest()

# =============================================================================
# Public API
# =============================================================================

def classify_shot_zone(x_loc, y_loc, shot_type):
    if RUST_AVAILABLE: return rust_classify_shot_zone(x_loc, y_loc, shot_type)
    return _python_classify_shot_zone(x_loc, y_loc, shot_type)

def get_expected_value(zone):
    if RUST_AVAILABLE: return rust_get_expected_value(zone)
    return _python_get_expected_value(zone)

def calculate_true_usage_rate(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes=200.0):
    if RUST_AVAILABLE: return rust_calculate_true_usage_rate(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes)
    # Basic fallback USG% calculation
    if minutes <= 0: return 0.0
    poss = fga + 0.44 * fta + tov
    team_poss = team_fga + 0.44 * team_fta + team_tov
    if team_poss == 0: return 0.0
    return round((poss * (team_minutes / 5)) / (minutes * team_poss) * 100, 1)

def calculate_points_per_shot(points, fga):
    if RUST_AVAILABLE: return rust_calculate_points_per_shot(points, fga)
    return round(points / fga, 2) if fga > 0 else 0.0

def calculate_shot_quality_delta(actual, expected):
    if RUST_AVAILABLE: return rust_calculate_shot_quality_delta(actual, expected)
    return round(actual - expected, 2)

def calculate_shot_quality_score(shots):
    if RUST_AVAILABLE:
        try: return json.loads(rust_calculate_shot_quality_score(json.dumps(shots)))
        except: pass
    # Python fallback implementation for shot quality score
    if not shots: return {"total_shots": 0, "total_points": 0, "expected_points": 0.0, "shot_quality_delta": 0.0, "ppps": 0.0, "zone_breakdown": {}}
    total_pts = sum(s.get('points', 0) for s in shots)
    total_exp = 0.0
    for s in shots:
        z = _python_classify_shot_zone(s.get('x_loc'), s.get('y_loc'), s.get('shot_type', '2pt'))
        total_exp += _python_get_expected_value(z)
    return {
        "total_shots": len(shots),
        "total_points": total_pts,
        "expected_points": round(total_exp, 2),
        "shot_quality_delta": round(total_pts - total_exp, 2),
        "ppps": round(total_pts / len(shots), 2)
    }

def parse_time_to_seconds(time_str):
    if RUST_AVAILABLE: return rust_parse_time_to_seconds(time_str)
    try:
        if ':' in time_str:
            parts = time_str.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return int(time_str)
    except: return 300

def is_clutch_situation(margin, seconds):
    if RUST_AVAILABLE: return rust_is_clutch_situation(margin, seconds)
    return abs(margin) <= 5 and seconds <= 300

def safe_percentage(n, d, decimals=1):
    if RUST_AVAILABLE: return round(rust_safe_percentage(n, d), decimals)
    return round(_python_safe_percentage(n, d), decimals)

def calculate_possessions(fga, fta, oreb, tov):
    if RUST_AVAILABLE: return rust_calculate_possessions(int(fga), int(fta), int(oreb), int(tov))
    return _python_calculate_possessions(fga, fta, oreb, tov)

def calculate_offensive_rating(pts, poss):
    if RUST_AVAILABLE: return rust_calculate_offensive_rating(int(pts), int(poss))
    return _python_calculate_offensive_rating(pts, poss)

def calculate_true_shooting_pct(pts, fga, fta):
    if RUST_AVAILABLE: return rust_calculate_true_shooting_pct(int(pts), int(fga), int(fta))
    return _python_calculate_true_shooting_pct(pts, fga, fta)

def calculate_efg_pct(fgm, tpm, fga):
    if RUST_AVAILABLE: return rust_calculate_efg_pct(int(fgm), int(tpm), int(fga))
    return _python_calculate_efg_pct(fgm, tpm, fga)

def aggregate_combinatorial_stats(segments):
    if RUST_AVAILABLE:
        try: return json.loads(rust_aggregate_combinatorial_stats(json.dumps(segments)))
        except: pass
    return {"duos": {}, "trios": {}}

def reconstruct_possessions(events):
    if RUST_AVAILABLE:
        try: return json.loads(rust_reconstruct_possessions_rust(json.dumps(events)))
        except: pass
    return []

def calculate_lineup_hash(players):
    if RUST_AVAILABLE: return rust_calculate_lineup_hash(players)
    return _python_calculate_lineup_hash(players)

def is_rust_available():
    return RUST_AVAILABLE
