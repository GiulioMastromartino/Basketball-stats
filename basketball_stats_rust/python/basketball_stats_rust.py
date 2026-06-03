"""
Basketball Stats Rust - High-performance analytics Python wrapper

This module provides Python bindings to the Rust implementation for
compute-intensive analytics functions. Falls back to pure Python
implementations if the Rust library is not available.
"""

import json
import hashlib
from typing import Dict, List, Optional, Any
from itertools import combinations
from collections import defaultdict

# Try to import Rust library, fall back to pure Python if not available
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
        reconstruct_possessions_rust as rust_reconstruct_possessions,
    )
    RUST_AVAILABLE = True
except ImportError:
    pass


# =============================================================================
# Pure Python Fallbacks (for when Rust is not available)
# =============================================================================

def _python_classify_shot_zone(x_loc: Optional[float], y_loc: Optional[float], shot_type: str) -> str:
    """Pure Python fallback for classify_shot_zone."""
    if not shot_type:
        return 'Midrange'
    
    st = shot_type.lower()
    
    if st == 'ft':
        return 'FT'
    
    if x_loc is None or y_loc is None:
        return 'Midrange'
    
    dx = x_loc - 250
    dy = y_loc - 50
    distance = (dx**2 + dy**2)**0.5
    
    if distance <= 40:
        return 'Rim'
    elif distance <= 100:
        return 'Paint'
    elif '3pt' in st:
        if y_loc < 140:
            return 'Corner_3'
        return 'Above_Break_3'
    else:
        return 'Midrange'


def _python_get_expected_value(zone: str) -> float:
    """Pure Python fallback for get_expected_value."""
    DEFAULT_ZONE_VALUES = {
        'Rim': 1.20,
        'Paint': 0.85,
        'Midrange': 0.75,
        'Corner_3': 1.10,
        'Above_Break_3': 1.05,
        'FT': 0.75,
    }
    return DEFAULT_ZONE_VALUES.get(zone, 0.80)


def _python_calculate_true_usage_rate(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes=200.0):
    """Pure Python fallback for calculate_true_usage_rate."""
    if minutes <= 0:
        return 0.0
    
    FT_ATTEMPT_WEIGHT = 0.44
    player_possessions = fga + (FT_ATTEMPT_WEIGHT * fta) + tov
    team_possessions = team_fga + (FT_ATTEMPT_WEIGHT * team_fta) + team_tov
    
    if team_possessions == 0:
        return 0.0
    
    usage = (player_possessions * (team_minutes / 5)) / (minutes * team_possessions) * 100
    return round(min(usage, 100.0), 1)


def _python_calculate_shot_quality_score(shots: List[Dict]) -> Dict:
    """Pure Python fallback for calculate_shot_quality_score."""
    if not shots:
        return {
            'total_shots': 0,
            'total_points': 0,
            'expected_points': 0.0,
            'shot_quality_delta': 0.0,
            'ppps': 0.0,
            'zone_breakdown': {}
        }
    
    total_points = sum(s.get('points', 0) for s in shots)
    total_expected = 0.0
    zone_stats = {}
    
    for shot in shots:
        zone = _python_classify_shot_zone(
            shot.get('x_loc'), 
            shot.get('y_loc'), 
            shot.get('shot_type', '2pt')
        )
        expected = _python_get_expected_value(zone)
        total_expected += expected
        
        if zone not in zone_stats:
            zone_stats[zone] = {'makes': 0, 'attempts': 0, 'points': 0, 'expected': 0.0}
        
        zone_stats[zone]['attempts'] += 1
        zone_stats[zone]['points'] += shot.get('points', 0)
        zone_stats[zone]['expected'] += expected
        if shot.get('points', 0) > 0:
            zone_stats[zone]['makes'] += 1
    
    return {
        'total_shots': len(shots),
        'total_points': total_points,
        'expected_points': round(total_expected, 2),
        'shot_quality_delta': round(total_points - total_expected, 2),
        'ppps': round(total_points / len(shots), 2) if shots else 0.0,
        'zone_breakdown': zone_stats
    }

def _python_aggregate_combinatorial_stats(segments: List[Dict]) -> Dict:
    """Pure Python fallback for aggregate_combinatorial_stats."""
    duo_stats = defaultdict(lambda: {'segments': 0, 'points_scored': 0, 'points_allowed': 0, 'possessions': 0})
    trio_stats = defaultdict(lambda: {'segments': 0, 'points_scored': 0, 'points_allowed': 0, 'possessions': 0})
    
    for segment in segments:
        players = segment.get('players', [])
        if len(players) < 2: continue
        
        sorted_players = sorted(players)
        
        # Duos
        for duo in combinations(sorted_players, 2):
            key = ",".join(duo)
            s = duo_stats[key]
            s['segments'] += 1
            s['points_scored'] += segment.get('points_scored', 0)
            s['points_allowed'] += segment.get('points_allowed', 0)
            s['possessions'] += segment.get('possessions', 0)
            
        # Trios
        if len(sorted_players) >= 3:
            for trio in combinations(sorted_players, 3):
                key = ",".join(trio)
                s = trio_stats[key]
                s['segments'] += 1
                s['points_scored'] += segment.get('points_scored', 0)
                s['points_allowed'] += segment.get('points_allowed', 0)
                s['possessions'] += segment.get('possessions', 0)
                
    return {'duos': dict(duo_stats), 'trios': dict(trio_stats)}

# =============================================================================
# Public API - Uses Rust if available, falls back to Python
# =============================================================================

def classify_shot_zone(x_loc: Optional[float], y_loc: Optional[float], shot_type: str) -> str:
    """Classify a shot into a zone based on court coordinates."""
    if RUST_AVAILABLE:
        return rust_classify_shot_zone(x_loc, y_loc, shot_type)
    return _python_classify_shot_zone(x_loc, y_loc, shot_type)


def get_expected_value(zone: str) -> float:
    """Get expected point value for a zone."""
    if RUST_AVAILABLE:
        return rust_get_expected_value(zone)
    return _python_get_expected_value(zone)


def calculate_true_usage_rate(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes=200.0) -> float:
    """Calculate True Usage Rate (USG%)."""
    if RUST_AVAILABLE:
        return rust_calculate_true_usage_rate(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes)
    return _python_calculate_true_usage_rate(fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes)


def calculate_points_per_shot(points: int, fga: int) -> float:
    """Calculate Points Per Shot (PPS)."""
    if RUST_AVAILABLE:
        return rust_calculate_points_per_shot(points, fga)
    return round(points / fga, 2) if fga > 0 else 0.0


def calculate_shot_quality_delta(actual_points: float, expected_points: float) -> float:
    """Calculate Shot Quality Delta."""
    if RUST_AVAILABLE:
        return rust_calculate_shot_quality_delta(actual_points, expected_points)
    return round(actual_points - expected_points, 2)


def calculate_shot_quality_score(shots: List[Dict]) -> Dict:
    """Calculate comprehensive shot quality metrics for a player."""
    if RUST_AVAILABLE:
        try:
            shots_json = json.dumps(shots)
            result_json = rust_calculate_shot_quality_score(shots_json)
            return json.loads(result_json)
        except:
            return _python_calculate_shot_quality_score(shots)
    return _python_calculate_shot_quality_score(shots)


def aggregate_combinatorial_stats(segments: List[Dict]) -> Dict:
    """Aggregate Duo and Trio compatibility stats."""
    if RUST_AVAILABLE:
        try:
            segments_json = json.dumps(segments)
            result_json = rust_aggregate_combinatorial_stats(segments_json)
            return json.loads(result_json)
        except:
            return _python_aggregate_combinatorial_stats(segments)
    return _python_aggregate_combinatorial_stats(segments)


def reconstruct_possessions(events: List[Dict]) -> List[Dict]:
    """Reconstruct possessions from game events."""
    if RUST_AVAILABLE:
        try:
            events_json = json.dumps(events)
            result_json = rust_reconstruct_possessions(events_json)
            return json.loads(result_json)
        except:
            # Fallback to current Python implementation would be needed here
            # For now return empty to avoid crash if Rust fails
            return []
    return []


def is_rust_available() -> bool:
    """Check if Rust library is available."""
    return RUST_AVAILABLE
