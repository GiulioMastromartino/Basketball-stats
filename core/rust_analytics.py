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
        calculate_impact_metrics as rust_calculate_impact_metrics,
        calculate_shot_heatmap as rust_calculate_shot_heatmap,
        enhance_possession_tracking as rust_enhance_possession_tracking,
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


def _python_aggregate_combinatorial_stats(segments: List[Dict]) -> Dict:
    duo_stats = defaultdict(
        lambda: {"segments": 0, "points_scored": 0, "points_allowed": 0, "possessions": 0.0, "duration_seconds": 0, "reb_conceded": 0}
    )
    trio_stats = defaultdict(
        lambda: {"segments": 0, "points_scored": 0, "points_allowed": 0, "possessions": 0.0, "duration_seconds": 0, "reb_conceded": 0}
    )
    totals = {"segments": 0, "points_scored": 0, "points_allowed": 0, "possessions": 0.0, "duration_seconds": 0, "reb_conceded": 0}

    for segment in segments or []:
        players = segment.get("players") or []
        if isinstance(players, str):
            try:
                players = json.loads(players)
            except Exception:
                players = []

        points_scored = int(segment.get("points_scored", 0) or 0)
        points_allowed = int(segment.get("points_allowed", 0) or 0)
        possessions = float(segment.get("possessions", 0) or 0)
        duration_seconds = int(segment.get("duration_seconds", 0) or 0)
        reb_conceded = int(segment.get("reb_conceded", 0) or 0)

        totals["segments"] += 1
        totals["points_scored"] += points_scored
        totals["points_allowed"] += points_allowed
        totals["possessions"] += possessions
        totals["duration_seconds"] += duration_seconds
        totals["reb_conceded"] += reb_conceded

        if len(players) < 2:
            continue

        sorted_players = sorted(players)

        for duo in combinations(sorted_players, 2):
            key = ",".join(duo)
            s = duo_stats[key]
            s["segments"] += 1
            s["points_scored"] += points_scored
            s["points_allowed"] += points_allowed
            s["possessions"] += possessions
            s["duration_seconds"] += duration_seconds
            s["reb_conceded"] += reb_conceded

        if len(sorted_players) >= 3:
            for trio in combinations(sorted_players, 3):
                key = ",".join(trio)
                s = trio_stats[key]
                s["segments"] += 1
                s["points_scored"] += points_scored
                s["points_allowed"] += points_allowed
                s["possessions"] += possessions
                s["duration_seconds"] += duration_seconds
                s["reb_conceded"] += reb_conceded

    return {"duos": dict(duo_stats), "trios": dict(trio_stats), "totals": totals}

def _python_calculate_impact_metrics(segments: List[Dict], combination_type: str, min_poss: float) -> List[Dict]:
    """Pure python fallback for impact metrics calculation."""
    stats = _python_aggregate_combinatorial_stats(segments)
    combo_key = "duos" if combination_type == "duo" else "trios"
    combo_stats = stats.get(combo_key, {})
    totals = stats.get("totals", {})
    
    total_possessions = float(totals.get("possessions", 0))
    total_points_scored = float(totals.get("points_scored", 0))
    total_points_allowed = float(totals.get("points_allowed", 0))
    
    results = []
    for key, on_stats in combo_stats.items():
        on_poss = float(on_stats.get("possessions", 0))
        if on_poss < min_poss:
            continue
            
        on_pts_scored = float(on_stats.get("points_scored", 0))
        on_pts_allowed = float(on_stats.get("points_allowed", 0))
        
        on_ortg = (on_pts_scored / on_poss * 100) if on_poss > 0 else 0
        on_drtg = (on_pts_allowed / on_poss * 100) if on_poss > 0 else 0
        on_net = on_ortg - on_drtg
        
        off_poss = total_possessions - on_poss
        if off_poss <= 0:
            continue
            
        off_pts_scored = total_points_scored - on_pts_scored
        off_pts_allowed = total_points_allowed - on_pts_allowed
        
        off_ortg = (off_pts_scored / off_poss * 100) if off_poss > 0 else 0
        off_drtg = (off_pts_allowed / off_poss * 100) if off_poss > 0 else 0
        off_net = off_ortg - off_drtg
        
        results.append({
            "players": key.split(","),
            "on": {
                "ortg": round(on_ortg, 1),
                "drtg": round(on_drtg, 1),
                "net": round(on_net, 1),
                "possessions": round(on_poss, 1),
                "minutes": round(float(on_stats.get("duration_seconds", 0)) / 60, 1),
                "points_scored": on_pts_scored,
                "points_allowed": on_pts_allowed
            },
            "off": {
                "ortg": round(off_ortg, 1),
                "drtg": round(off_drtg, 1),
                "net": round(off_net, 1),
                "possessions": round(off_poss, 1)
            },
            "impact": {
                "offense_delta": round(on_ortg - off_ortg, 1),
                "defense_delta": round(off_drtg - on_drtg, 1),
                "net_differential": round(on_net - off_net, 1)
            },
            "segments": on_stats.get("segments", 0)
        })
        
    results.sort(key=lambda x: x["impact"]["net_differential"], reverse=True)
    return results

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
    return _python_aggregate_combinatorial_stats(segments)

def reconstruct_possessions(events):
    if RUST_AVAILABLE:
        try: return json.loads(rust_reconstruct_possessions_rust(json.dumps(events)))
        except: pass
    return []

def calculate_lineup_hash(players):
    if RUST_AVAILABLE: return rust_calculate_lineup_hash(players)
    return _python_calculate_lineup_hash(players)

def _python_calculate_shot_heatmap(shots: List[Dict]) -> List[Dict]:
    """Pure python fallback for shot heatmap calculation."""
    if not shots:
        return []
        
    total_attempts = len(shots)
    zone_stats = defaultdict(lambda: {'makes': 0, 'attempts': 0, 'points': 0})
    
    for shot in shots:
        zone = _python_classify_shot_zone(shot.get('x_loc'), shot.get('y_loc'), shot.get('shot_type', '2pt'))
        zone_stats[zone]['attempts'] += 1
        zone_stats[zone]['points'] += shot.get('points', 0)
        if shot.get('points', 0) > 0:
            zone_stats[zone]['makes'] += 1
            
    results = []
    for zone, stats in zone_stats.items():
        freq = (stats['attempts'] / total_attempts * 100) if total_attempts > 0 else 0
        fg_pct = (stats['makes'] / stats['attempts'] * 100) if stats['attempts'] > 0 else 0
        pps = (stats['points'] / stats['attempts']) if stats['attempts'] > 0 else 0
        expected = _python_get_expected_value(zone)
        
        results.append({
            "zone": zone,
            "makes": stats['makes'],
            "attempts": stats['attempts'],
            "frequency": round(freq, 1),
            "fg_pct": round(fg_pct, 1),
            "pps": round(pps, 2),
            "actual_pps": round(pps, 2),
            "expected_value": expected,
            "efficiency_delta": round(pps - expected, 2)
        })
    return results

def calculate_impact_metrics(segments, combo_type, min_poss):
    if not segments:
        return []
    if RUST_AVAILABLE:
        try:
            print(f"[RustAnalytics] Calling Rust calculate_impact_metrics for {combo_type}")
            res = rust_calculate_impact_metrics(json.dumps(segments), combo_type, float(min_poss))
            results = json.loads(res)
            print(f"[RustAnalytics] Rust returned {len(results)} results")
            return results
        except Exception as e:
            print(f"Rust Impact Metrics error: {e}")
            pass
    print(f"[RustAnalytics] Using Python fallback for {combo_type}")
    return _python_calculate_impact_metrics(segments, combo_type, float(min_poss))

def calculate_shot_heatmap(shots):
    if not shots:
        return []
    if RUST_AVAILABLE:
        try:
            res = rust_calculate_shot_heatmap(json.dumps(shots))
            return json.loads(res)
        except Exception as e:
            print(f"Rust Heatmap error: {e}")
            pass
    return _python_calculate_shot_heatmap(shots)

def enhance_possession_tracking(events):
    if RUST_AVAILABLE:
        try: return json.loads(rust_enhance_possession_tracking(json.dumps(events)))
        except: pass
    return []

def is_rust_available():
    return RUST_AVAILABLE
