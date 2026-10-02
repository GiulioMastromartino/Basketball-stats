"""
Basketball Stats Rust - High-performance analytics Python wrapper
"""

import json
import logging
from typing import Dict, List, Optional
from itertools import combinations
from collections import defaultdict

log = logging.getLogger(__name__)

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
        calculate_possessions_batch as rust_calculate_possessions_batch,
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
        batch_is_clutch as rust_batch_is_clutch,
        calculate_game_flow as rust_calculate_game_flow,
        aggregate_combinatorial_stats as rust_aggregate_combinatorial_stats,
        reconstruct_possessions_rust as rust_reconstruct_possessions_rust,
        calculate_lineup_hash as rust_calculate_lineup_hash,
        calculate_impact_metrics as rust_calculate_impact_metrics,
        calculate_shot_heatmap as rust_calculate_shot_heatmap,
        enhance_possession_tracking as rust_enhance_possession_tracking,
    )
    # Import batch-only symbols separately so older installed .so without them
    # does not break the whole bridge (fallback to Python for those only).
    try:
        from basketball_stats import classify_shot_zones_batch as rust_classify_shot_zones_batch
    except ImportError:
        rust_classify_shot_zones_batch = None
    try:
        from basketball_stats import parse_details_batch as rust_parse_details_batch
    except ImportError:
        rust_parse_details_batch = None
    try:
        from basketball_stats import parse_times_batch as rust_parse_times_batch
    except ImportError:
        rust_parse_times_batch = None
    try:
        from basketball_stats import aggregate_hexbins as rust_aggregate_hexbins
    except ImportError:
        rust_aggregate_hexbins = None
    RUST_AVAILABLE = True
    log.debug("High-performance Rust analytics engine LOADED.")
except ImportError:
    log.debug("Rust analytics library NOT FOUND. Falling back to pure Python (slower).")
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


def _normalize_combo_type(combination_type: str) -> str:
    t = (combination_type or "").strip().lower()
    if t.endswith("s"):
        t = t[:-1]
    return "trio" if t == "trio" else "duo"


def _shot_data(s: Dict) -> Dict:
    """Complete ShotData dict for the typed Rust bridge (no JSON).

    The Rust structs extract strictly by key, so every key must be present;
    nullability is fine (Option fields). Cheap dict build, no serialization.
    """
    return {
        "points": s.get("points", 0) or 0,
        "x_loc": s.get("x_loc"),
        "y_loc": s.get("y_loc"),
        "shot_type": s.get("shot_type") or "",
    }


def _segment_data(s: Dict) -> Dict:
    """Complete LineupSegmentData dict (parses players-as-JSON-string)."""
    players = s.get("players") or []
    if isinstance(players, str):
        try:
            players = json.loads(players)
        except Exception:
            players = []
    return {
        "players": list(players),
        "points_scored": int(s.get("points_scored", 0) or 0),
        "points_allowed": int(s.get("points_allowed", 0) or 0),
        "possessions": float(s.get("possessions", 0) or 0),
        "reb_conceded": s.get("reb_conceded"),
        "duration_seconds": int(s.get("duration_seconds", 0) or 0),
    }


def _event_data(e: Dict) -> Dict:
    """Complete GameEventData dict for the typed Rust bridge."""
    q = e.get("quarter")
    return {
        "id": int(e.get("id", 0) or 0),
        "event_type": e.get("event_type") or "",
        "timestamp": float(e.get("timestamp", 0) or 0),
        "quarter": None if q is None else int(q),
        "shot_attempt": e.get("shot_attempt"),
    }


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
    combination_type = _normalize_combo_type(combination_type)
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
    if RUST_AVAILABLE:
        try:
            return rust_classify_shot_zone(x_loc, y_loc, shot_type or "")
        except TypeError:
            return _python_classify_shot_zone(x_loc, y_loc, shot_type or "")
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
        try: return rust_calculate_shot_quality_score([_shot_data(s) for s in shots])
        except Exception: pass
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
    if RUST_AVAILABLE:
        try:
            return rust_parse_time_to_seconds(time_str if time_str is not None else "")
        except (TypeError, ValueError):
            pass
    return _python_parse_time_to_seconds(time_str)


def _python_parse_time_to_seconds(time_str):
    try:
        if time_str is None:
            return 0
        if ':' in time_str:
            parts = time_str.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        return int(time_str)
    except (TypeError, ValueError):
        return 0


def parse_times_batch(times):
    """Batch MM:SS parse: [str|None, ...] -> [seconds, ...]. One crossing."""
    if not times:
        return []
    if RUST_AVAILABLE and rust_parse_times_batch is not None:
        try:
            return rust_parse_times_batch(list(times))
        except Exception as e:
            log.debug("Rust parse-times batch error: %s", e)
    return [_python_parse_time_to_seconds(t) for t in times]

def is_clutch_situation(margin, seconds):
    if RUST_AVAILABLE: return rust_is_clutch_situation(margin, seconds)
    return abs(margin) <= 5 and seconds <= 300

def safe_percentage(n, d, decimals=1):
    try:
        if RUST_AVAILABLE:
            return round(rust_safe_percentage(float(n or 0), float(d or 0)), decimals)
    except (TypeError, ValueError):
        pass
    return round(_python_safe_percentage(n, d), decimals)

def calculate_possessions(fga, fta, oreb, tov):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_possessions(int(fga), int(fta), int(oreb), int(tov))
        except (TypeError, ValueError):
            pass
    return _python_calculate_possessions(fga, fta, oreb, tov)

def calculate_possessions_batch(entries):
    """Batch possessions for [[fga, fta, oreb, tov], ...] -> [float, ...]. One crossing."""
    if RUST_AVAILABLE and rust_calculate_possessions_batch is not None:
        try:
            return rust_calculate_possessions_batch([list(e) for e in entries])
        except Exception as e:
            log.debug("Rust possessions batch error: %s", e)
    return [float(e[0]) + 0.44 * float(e[1]) - float(e[2]) + float(e[3]) for e in entries]

def calculate_offensive_rating(pts, poss):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_offensive_rating(int(pts), float(poss))
        except (TypeError, ValueError):
            pass
    return _python_calculate_offensive_rating(pts, poss)

def calculate_true_shooting_pct(pts, fga, fta):
    if RUST_AVAILABLE: return rust_calculate_true_shooting_pct(int(pts), int(fga), int(fta))
    return _python_calculate_true_shooting_pct(pts, fga, fta)

def calculate_efg_pct(fgm, tpm, fga):
    if RUST_AVAILABLE: return rust_calculate_efg_pct(int(fgm), int(tpm), int(fga))
    return _python_calculate_efg_pct(fgm, tpm, fga)

def calculate_defensive_rating(pts_allowed, opp_poss):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_defensive_rating(int(pts_allowed), float(opp_poss))
        except (TypeError, ValueError):
            pass
    return round((pts_allowed / opp_poss * 100), 1) if opp_poss else 0.0

def calculate_net_rating(off_rtg, def_rtg):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_net_rating(float(off_rtg), float(def_rtg))
        except (TypeError, ValueError):
            pass
    return (off_rtg or 0.0) - (def_rtg or 0.0)

def calculate_assist_ratio(ast, fga, tov, fta):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_assist_ratio(int(ast), int(fga), int(tov), int(fta))
        except (TypeError, ValueError):
            pass
    poss = (fga or 0) + (tov or 0) + (fta or 0) / 2.0
    return (ast / poss * 100.0) if poss else 0.0

def calculate_turnover_ratio(tov, fga, fta, ora=0):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_turnover_ratio(int(tov), int(fga), int(fta), int(ora))
        except (TypeError, ValueError):
            pass
    poss = (fga or 0) + (fta or 0) / 2.0 + (ora or 0)
    return (tov / poss * 100.0) if poss else 0.0

def calculate_rebound_rate(orb, team_orb, opp_drb):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_rebound_rate(int(orb), int(team_orb), int(opp_drb))
        except (TypeError, ValueError):
            pass
    total = (orb or 0) + (team_orb or 0) + (opp_drb or 0)
    return (orb / total * 100.0) if total else 0.0

def calculate_pace(team_poss, team_minutes, league_pace=100.0):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_pace(float(team_poss), float(team_minutes), float(league_pace))
        except (TypeError, ValueError):
            pass
    return (team_poss * 40.0 / team_minutes) if team_minutes else league_pace

def safe_div(numerator, denominator, default=0.0):
    if RUST_AVAILABLE:
        try:
            return rust_safe_div(float(numerator), float(denominator), float(default))
        except (TypeError, ValueError):
            pass
    return float(numerator) / float(denominator) if denominator else default

def seconds_to_time(seconds):
    if RUST_AVAILABLE:
        try:
            return rust_seconds_to_time(int(seconds))
        except (TypeError, ValueError):
            pass
    s = max(0, int(seconds or 0))
    return f"{s // 60:02d}:{s % 60:02d}"

def calculate_game_flow(scores):
    if RUST_AVAILABLE:
        try:
            return rust_calculate_game_flow(list(scores or []))
        except Exception as e:
            log.debug("Rust game flow error: %s", e)
    running = (0, 0)
    out = []
    for sp in scores or []:
        ts = int(sp.get("team_score", 0) or 0)
        os_ = int(sp.get("opp_score", 0) or 0)
        running = (running[0] + ts, running[1] + os_)
        row = dict(sp)
        row["running_team_score"] = running[0]
        row["running_opp_score"] = running[1]
        row["margin"] = running[0] - running[1]
        out.append(row)
    return out

def aggregate_combinatorial_stats(segments):
    if RUST_AVAILABLE:
        try:
            res = rust_aggregate_combinatorial_stats([_segment_data(s) for s in segments or []])
            # Backfill totals for callers on old payloads without duration_seconds.
            res.setdefault("totals", {})
            return res
        except Exception as e:
            log.debug("Rust combinatorial error: %s", e)
    return _python_aggregate_combinatorial_stats(segments)

def reconstruct_possessions(events):
    if RUST_AVAILABLE:
        try: return rust_reconstruct_possessions_rust([_event_data(e) for e in events or []])
        except Exception: pass
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
    combo_type = _normalize_combo_type(combo_type)
    if RUST_AVAILABLE:
        try:
            return rust_calculate_impact_metrics(
                [_segment_data(s) for s in segments], combo_type, float(min_poss))
        except Exception as e:
            log.debug("Rust Impact Metrics error: %s", e)
    return _python_calculate_impact_metrics(segments, combo_type, float(min_poss))

def calculate_shot_heatmap(shots):
    if not shots:
        return []
    if RUST_AVAILABLE:
        try:
            return rust_calculate_shot_heatmap([_shot_data(s) for s in shots])
        except Exception as e:
            log.debug("Rust Heatmap error: %s", e)
    return _python_calculate_shot_heatmap(shots)


def classify_shot_zones_batch(shots):
    """Batch zone classification: [ShotData, ...] -> [zone, ...]. One crossing."""
    if not shots:
        return []
    if RUST_AVAILABLE and rust_classify_shot_zones_batch is not None:
        try:
            return rust_classify_shot_zones_batch([_shot_data(s) for s in shots])
        except Exception as e:
            log.debug("Rust zone batch error: %s", e)
    return [
        _python_classify_shot_zone(s.get("x_loc"), s.get("y_loc"), s.get("shot_type", "2pt") or "")
        for s in shots
    ]


def batch_is_clutch(entries):
    """Batch clutch check: [[margin, seconds], ...] -> [bool, ...]."""
    if not entries:
        return []
    if RUST_AVAILABLE and rust_batch_is_clutch is not None:
        try:
            return rust_batch_is_clutch([list(e) for e in entries])
        except Exception as e:
            log.debug("Rust clutch batch error: %s", e)
    return [abs(int(e[0])) <= 5 and int(e[1]) <= 300 for e in entries]


def parse_details_batch(details):
    """Batch parse detail blobs (str/dict/None) -> [dict, ...]. Rust serde_json fast path."""
    if not details:
        return []
    if RUST_AVAILABLE and rust_parse_details_batch is not None:
        try:
            return rust_parse_details_batch(list(details))
        except Exception as e:
            log.debug("Rust parse-details batch error: %s", e)
    out = []
    for d in details:
        if isinstance(d, dict):
            out.append(d)
        elif isinstance(d, str) and d:
            try:
                parsed = json.loads(d)
                out.append(parsed if isinstance(parsed, dict) else {})
            except Exception:
                out.append({})
        else:
            out.append({})
    return out


def aggregate_hexbins(shots, hex_size=50):
    """Hexbin aggregation in Rust: [{x_loc, y_loc, points, result}] -> [{x, y, ...}]."""
    if not shots:
        return []
    if RUST_AVAILABLE and rust_aggregate_hexbins is not None:
        try:
            return rust_aggregate_hexbins(
                [
                    {
                        "x_loc": s.get("x_loc"),
                        "y_loc": s.get("y_loc"),
                        "points": s.get("points", 0) or 0,
                        "result": s.get("result"),
                    }
                    for s in shots
                ],
                float(hex_size),
            )
        except Exception as e:
            log.debug("Rust hexbin error: %s", e)
    from collections import defaultdict as _dd
    bins = _dd(lambda: {"makes": 0, "attempts": 0, "points": 0})
    hs = int(hex_size) or 50
    half = hs // 2
    for s in shots:
        x, y = s.get("x_loc"), s.get("y_loc")
        if x is None or y is None:
            continue
        hx = int(x // hs) * hs + half
        hy = int(y // hs) * hs + half
        b = bins[(hx, hy)]
        b["attempts"] += 1
        b["points"] += s.get("points") or 0
        if s.get("result") == "made":
            b["makes"] += 1
    out = [
        {"x": x, "y": y, "attempts": v["attempts"], "makes": v["makes"],
         "fg_pct": round(v["makes"] / v["attempts"] * 100, 1) if v["attempts"] else 0.0,
         "points": v["points"]}
        for (x, y), v in bins.items()
    ]
    out.sort(key=lambda r: r["attempts"], reverse=True)
    return out

def enhance_possession_tracking(events):
    if RUST_AVAILABLE:
        try: return rust_enhance_possession_tracking([_event_data(e) for e in events or []])
        except Exception: pass
    return []

def is_rust_available():
    return RUST_AVAILABLE
