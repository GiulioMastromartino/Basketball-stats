"""
Advanced Basketball Analytics Engine
Implements sophisticated metrics including:
- True Usage Rate (USG%)
- Points Per Shot (PPS)
- Shot Quality Model (ShotQS)
- Clutch Performance
- On/Off Splits
- Net Rating Differential
- Duo/Trio Compatibility
- Lineup Efficiency
"""
import hashlib
import json
from collections import defaultdict
from statistics import mean, stdev
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import func, case, and_, or_, desc
from sqlalchemy.sql import label

from core.models import (
    db, Game, PlayerStat, ShotEvent, GameEvent, Play,
    LineupSegment, Possession, ShotZone, PlayerLineupStats
)
from core.utils import (
    safe_divide, safe_percentage, parse_minutes,
    calculate_possessions, FT_ATTEMPT_WEIGHT
)
from core import rust_analytics


# =============================================================================
# SHOT QUALITY MODEL - Expected Point Values by Zone
# =============================================================================

# Default expected values for shot zones (can be customized via ShotZone table)
DEFAULT_ZONE_VALUES = {
    'Rim': 1.20,           # Layups/dunks at the basket
    'Paint': 0.85,         # Shots in the paint (non-rim)
    'Midrange': 0.75,      # Mid-range jumpers
    'Corner_3': 1.10,      # Corner 3-pointers (shorter distance)
    'Above_Break_3': 1.05, # Above-the-break 3-pointers
    'FT': 0.75,            # Free throws (per attempt)
}


def classify_shot_zone(x_loc: Optional[float], y_loc: Optional[float], 
                       shot_type: str) -> str:
    """
    Classify a shot into a zone based on court coordinates.
    Uses high-performance Rust implementation.
    """
    return rust_analytics.classify_shot_zone(x_loc, y_loc, shot_type)


def get_expected_value(zone: str) -> float:
    """Get expected point value for a zone using Rust implementation."""
    return rust_analytics.get_expected_value(zone)


# =============================================================================
# ADVANCED PLAYER STATISTICS
# =============================================================================

class AdvancedPlayerStats:
    """Advanced individual player metrics using Rust for performance."""
    
    @staticmethod
    def calculate_true_usage_rate(fga: int, fta: int, tov: int,
                                   team_fga: int, team_fta: int, team_tov: int,
                                   minutes: float, team_minutes: float = 200.0) -> float:
        """Calculate True Usage Rate (USG%) using Rust."""
        return rust_analytics.calculate_true_usage_rate(
            fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes
        )
    
    @staticmethod
    def calculate_points_per_shot(points: int, fga: int) -> float:
        """Calculate Points Per Shot (PPS) using Rust."""
        return rust_analytics.calculate_points_per_shot(points, fga)
    
    @staticmethod
    def calculate_shot_quality_delta(actual_points: float, expected_points: float) -> float:
        """Calculate Shot Quality Delta using Rust."""
        return rust_analytics.calculate_shot_quality_delta(actual_points, expected_points)
    
    @staticmethod
    def calculate_shot_quality_score(shots: List[Dict]) -> Dict:
        """Calculate comprehensive shot quality metrics for a player using Rust."""
        return rust_analytics.calculate_shot_quality_score(shots)


# =============================================================================
# CLUTCH PERFORMANCE
# =============================================================================

class ClutchPerformance:
    """Clutch time performance analysis (score within 5 points, < 5 minutes) using Rust."""
    
    CLUTCH_MARGIN = 5  # Points
    CLUTCH_TIME_SECONDS = 300  # 5 minutes
    
    @staticmethod
    def is_clutch_situation(score_margin: int, time_remaining_seconds: int) -> bool:
        """Determine if a situation qualifies as 'clutch' using Rust."""
        return rust_analytics.is_clutch_situation(score_margin, time_remaining_seconds)
    
    @staticmethod
    def get_clutch_stats(game_id: int, player_name: str = None) -> Dict:
        """
        Get clutch time statistics for a game or player.
        
        Args:
            game_id: Game ID to analyze
            player_name: Optional player filter
        
        Returns:
            Dictionary with clutch statistics
        """
        # Query events in clutch time
        query = GameEvent.query.filter(
            GameEvent.game_id == game_id,
            GameEvent.score_margin.isnot(None)
        )
        
        if player_name:
            query = query.filter(GameEvent.player_name == player_name)
        
        events = query.all()
        
        clutch_events = [
            e for e in events 
            if ClutchPerformance.is_clutch_situation(
                e.score_margin or 0, 
                parse_time_to_seconds(e.time_remaining or "5:00")
            )
        ]
        
        if not clutch_events:
            return {'clutch_plays': 0, 'clutch_points': 0, 'clutch_fg_pct': 0}
        
        # Aggregate clutch stats
        clutch_points = 0
        clutch_fga = 0
        clutch_fgm = 0
        clutch_tov = 0
        
        for event in clutch_events:
            if event.event_type in ['SHOT_2PT', 'SHOT_3PT']:
                clutch_fga += 1
                if event.shot_attempt == 'made':
                    clutch_fgm += 1
                    points = 2 if event.event_type == 'SHOT_2PT' else 3
                    clutch_points += points
            elif event.event_type == 'FT_MADE':
                clutch_points += 1
            elif event.event_type == 'TURNOVER':
                clutch_tov += 1
        
        return {
            'clutch_plays': len(clutch_events),
            'clutch_points': clutch_points,
            'clutch_fga': clutch_fga,
            'clutch_fgm': clutch_fgm,
            'clutch_fg_pct': round(safe_percentage(clutch_fgm, clutch_fga), 1),
            'clutch_tov': clutch_tov
        }


def parse_time_to_seconds(time_str: str) -> int:
    """Convert MM:SS to total seconds using Rust."""
    return rust_analytics.parse_time_to_seconds(time_str)


# =============================================================================
# TEAM & LINEUP ANALYTICS
# =============================================================================

class LineupAnalytics:
    """Advanced lineup and on/off court analysis."""
    
    @staticmethod
    def generate_lineup_hash(players: List[str]) -> str:
        """Generate a unique hash for a lineup combination."""
        sorted_players = sorted(players)
        return hashlib.md5(','.join(sorted_players).encode()).hexdigest()

    @staticmethod
    def _build_segment_payload(game_ids: List[int] = None) -> List[Dict]:
        """Build normalized lineup segment payload for aggregation engines."""
        query = LineupSegment.query
        if game_ids:
            query = query.filter(LineupSegment.game_id.in_(game_ids))

        payload = []
        for segment in query.all():
            players = segment.players
            if isinstance(players, str):
                try:
                    players = json.loads(players)
                except Exception:
                    players = []

            payload.append(
                {
                    "players": players or [],
                    "points_scored": segment.points_scored or 0,
                    "points_allowed": segment.points_allowed or 0,
                    "possessions": segment.possessions or 0,
                    "duration_seconds": segment.duration_seconds or 0,
                    "reb_conceded": segment.reb_conceded or 0,
                }
            )
        return payload

    @staticmethod
    def _rating(points_scored: float, points_allowed: float, possessions: float) -> Dict:
        """Return per-100 possession ORtg/DRtg/Net for a stat line."""
        if possessions <= 0:
            return {"ortg": 0.0, "drtg": 0.0, "net": 0.0}

        ortg = points_scored / possessions * 100
        drtg = points_allowed / possessions * 100
        return {
            "ortg": round(ortg, 1),
            "drtg": round(drtg, 1),
            "net": round(ortg - drtg, 1),
        }
    
    @staticmethod
    def calculate_on_off_splits(player_name: str, game_ids: List[int] = None) -> Dict:
        """
        Calculate team performance when player is ON vs OFF the court.
        
        Args:
            player_name: Player to analyze
            game_ids: Optional list of games to include
        
        Returns:
            Dictionary with on/off court statistics
        """
        query = LineupSegment.query
        if game_ids:
            query = query.filter(LineupSegment.game_id.in_(game_ids))
        
        segments = query.all()
        
        on_court = {'points_scored': 0, 'points_allowed': 0, 'possessions': 0, 'segments': 0}
        off_court = {'points_scored': 0, 'points_allowed': 0, 'possessions': 0, 'segments': 0}
        
        for segment in segments:
            # Handle potential JSON string vs List issue
            players = segment.players
            if isinstance(players, str):
                try:
                    players = json.loads(players)
                except:
                    players = []
            if not players:
                players = []

            if player_name in players:
                on_court['points_scored'] += segment.points_scored or 0
                on_court['points_allowed'] += segment.points_allowed or 0
                on_court['possessions'] += segment.possessions or 0
                on_court['segments'] += 1
            else:
                off_court['points_scored'] += segment.points_scored or 0
                off_court['points_allowed'] += segment.points_allowed or 0
                off_court['possessions'] += segment.possessions or 0
                off_court['segments'] += 1
        
        # Calculate per-100-possession ratings
        def calc_rating(stats):
            if stats['possessions'] == 0:
                return {'ortg': 0, 'drtg': 0, 'net': 0}
            ortg = round(stats['points_scored'] / stats['possessions'] * 100, 1)
            drtg = round(stats['points_allowed'] / stats['possessions'] * 100, 1)
            return {'ortg': ortg, 'drtg': drtg, 'net': ortg - drtg}
        
        return {
            'player': player_name,
            'on_court': {
                **on_court,
                'rating': calc_rating(on_court)
            },
            'off_court': {
                **off_court,
                'rating': calc_rating(off_court)
            },
            'net_differential': round(
                calc_rating(on_court)['net'] - calc_rating(off_court)['net'], 1
            )
        }
    
    @staticmethod
    def calculate_duo_compatibility(game_ids: List[int] = None) -> List[Dict]:
        """
        Calculate synergy metrics for all 2-player combinations using high-performance aggregation.
        
        Returns:
            List of duo combinations with compatibility metrics
        """
        segment_data = LineupAnalytics._build_segment_payload(game_ids)

        # Use Rust-backed aggregator
        stats = rust_analytics.aggregate_combinatorial_stats(segment_data)
        duo_stats = stats.get('duos', {})
        
        # Calculate net ratings and format results
        results = []
        for key, s in duo_stats.items():
            if s['possessions'] > 0:
                p1, p2 = key.split(',')
                ortg = s['points_scored'] / s['possessions'] * 100
                drtg = s['points_allowed'] / s['possessions'] * 100
                results.append({
                    'player1': p1,
                    'player2': p2,
                    'segments': s['segments'],
                    'possessions': s['possessions'],
                    'ortg': round(ortg, 1),
                    'drtg': round(drtg, 1),
                    'net_rating': round(ortg - drtg, 1)
                })
        
        return sorted(results, key=lambda x: x['net_rating'], reverse=True)
    
    @staticmethod
    def calculate_trio_compatibility(game_ids: List[int] = None) -> List[Dict]:
        """Calculate synergy metrics for all 3-player combinations using high-performance aggregation."""
        segment_data = LineupAnalytics._build_segment_payload(game_ids)

        # Use Rust-backed aggregator
        stats = rust_analytics.aggregate_combinatorial_stats(segment_data)
        trio_stats = stats.get('trios', {})
        
        results = []
        for key, s in trio_stats.items():
            if s['possessions'] > 0:
                ortg = s['points_scored'] / s['possessions'] * 100
                drtg = s['points_allowed'] / s['possessions'] * 100
                results.append({
                    'players': key.split(','),
                    'segments': s['segments'],
                    'possessions': s['possessions'],
                    'ortg': round(ortg, 1),
                    'drtg': round(drtg, 1),
                    'net_rating': round(ortg - drtg, 1)
                })
        
        return sorted(results, key=lambda x: x['net_rating'], reverse=True)

    @staticmethod
    def get_combination_net_differentials(
        combination_type: str,
        game_ids: List[int] = None,
        min_possessions: float = 0.0,
        top_n: int = 10,
        require_positive: bool = True,
        total_pts_scored_override: float = None,
        total_pts_allowed_override: float = None,
        total_possessions_override: float = None,
        rank_by: str = "overall",  # overall, offensive, defensive
    ) -> List[Dict]:
        """
        Rank duo/trio combinations by ON vs OFF rating differential.
        Restored Python version for maximum accuracy and flexibility.
        """
        if combination_type not in {"duo", "trio"}:
            raise ValueError("combination_type must be 'duo' or 'trio'")

        segment_data = LineupAnalytics._build_segment_payload(game_ids)
        # Filter out segments with 0 possessions
        segment_data = [s for s in segment_data if s.get('possessions', 0) > 0]
        if not segment_data:
            return []

        # Use Python for aggregation to ensure reb_conceded and other new metrics are handled perfectly
        stats = rust_analytics.aggregate_combinatorial_stats(segment_data)
        combo_key = "duos" if combination_type == "duo" else "trios"
        combo_stats = stats.get(combo_key, {})

        # Robust totals calculation
        totals = stats.get("totals") or {}
        total_points_scored = float(total_pts_scored_override if total_pts_scored_override is not None else (totals.get("points_scored") or sum(s.get("points_scored", 0) for s in segment_data)))
        total_points_allowed = float(total_pts_allowed_override if total_pts_allowed_override is not None else (totals.get("points_allowed") or sum(s.get("points_allowed", 0) for s in segment_data)))
        total_possessions = float(total_possessions_override if total_possessions_override is not None else (totals.get("possessions") or sum(s.get("possessions", 0) for s in segment_data)))
        total_duration = float(totals.get("duration_seconds") or sum(s.get("duration_seconds", 0) for s in segment_data))

        results = []
        for key, on_stats in combo_stats.items():
            on_duration = float(on_stats.get("duration_seconds") or 0)
            on_possessions = float(on_stats.get("possessions", 0) or 0)
            
            # Fallback for minutes if duration is missing but possessions exist
            if on_duration <= 0 and on_possessions > 0 and total_possessions > 0:
                on_duration = (on_possessions / total_possessions) * total_duration
            
            on_minutes = on_duration / 60.0
            if on_possessions < float(min_possessions or 0):
                continue
            
            off_possessions = total_possessions - on_possessions
            if off_possessions <= 0:
                continue
                
            off_duration = max(total_duration - on_duration, 0.0)
            off_minutes = off_duration / 60.0

            on_points_scored = float(on_stats.get("points_scored", 0) or 0)
            on_points_allowed = float(on_stats.get("points_allowed", 0) or 0)
            off_points_scored = total_points_scored - on_points_scored
            off_points_allowed = total_points_allowed - on_points_allowed

            on_rating = LineupAnalytics._rating(
                on_points_scored, on_points_allowed, on_possessions
            )
            off_rating = LineupAnalytics._rating(
                off_points_scored, off_points_allowed, off_possessions
            )
            
            net_diff = round(on_rating["net"] - off_rating["net"], 1)
            off_diff = round(on_rating["ortg"] - off_rating["ortg"], 1)
            def_diff = round(off_rating["drtg"] - on_rating["drtg"], 1)

            if require_positive:
                if rank_by == "overall" and net_diff <= 0: continue
                if rank_by == "offensive" and off_diff <= 0: continue
                if rank_by == "defensive" and def_diff <= 0: continue

            players = key.split(",")
            results.append(
                {
                    "type": combination_type,
                    "players": players,
                    "segments": int(on_stats.get("segments", 0) or 0),
                    "on": {
                        "minutes": round(on_minutes, 1),
                        "possessions": round(on_possessions, 1),
                        "points_scored": round(on_points_scored, 1),
                        "points_allowed": round(on_points_allowed, 1),
                        **on_rating,
                    },
                    "off": {
                        "minutes": round(off_minutes, 1),
                        "possessions": round(off_possessions, 1),
                        "points_scored": round(off_points_scored, 1),
                        "points_allowed": round(off_points_allowed, 1),
                        **off_rating,
                    },
                    "impact": {
                        "offense_delta": off_diff,
                        "defense_delta": def_diff,
                        "net_differential": net_diff,
                    },
                }
            )

        if rank_by == "offensive":
            results.sort(key=lambda item: (item["impact"]["offense_delta"], item["on"]["minutes"]), reverse=True)
        elif rank_by == "defensive":
            results.sort(key=lambda item: (item["impact"]["defense_delta"], item["on"]["minutes"]), reverse=True)
        else:
            results.sort(key=lambda item: (item["impact"]["net_differential"], item["on"]["minutes"]), reverse=True)
            
        return results[:top_n]

    @staticmethod
    def get_combination_detail(
        combination_type: str,
        players: List[str],
        game_ids: List[int] = None,
        min_possessions: float = 0.0,
    ) -> Optional[Dict]:
        """Get ON vs OFF detail card data for a specific duo/trio."""
        if combination_type not in {"duo", "trio"}:
            raise ValueError("combination_type must be 'duo' or 'trio'")

        expected_size = 2 if combination_type == "duo" else 3
        normalized_players = sorted(
            [str(p).strip() for p in (players or []) if str(p).strip()]
        )
        if len(normalized_players) != expected_size:
            return None

        segment_data = LineupAnalytics._build_segment_payload(game_ids)
        if not segment_data:
            return None

        stats = rust_analytics.aggregate_combinatorial_stats(segment_data)
        combo_key = "duos" if combination_type == "duo" else "trios"
        combo_stats = stats.get(combo_key, {})
        key = ",".join(normalized_players)
        on_stats = combo_stats.get(key)
        if not on_stats:
            return None

        # Robust totals calculation
        totals = stats.get("totals") or {}
        total_points_scored = float(totals.get("points_scored") or sum(s.get("points_scored", 0) for s in segment_data))
        total_points_allowed = float(totals.get("points_allowed") or sum(s.get("points_allowed", 0) for s in segment_data))
        total_possessions = float(totals.get("possessions") or sum(s.get("possessions", 0) for s in segment_data))
        total_duration = float(totals.get("duration_seconds") or sum(s.get("duration_seconds", 0) for s in segment_data))

        on_possessions = float(on_stats.get("possessions", 0) or 0)
        on_duration = float(on_stats.get("duration_seconds") or 0)
        
        # Fallback for minutes
        if on_duration <= 0 and on_possessions > 0 and total_possessions > 0:
            on_duration = (on_possessions / total_possessions) * total_duration
            
        on_minutes = on_duration / 60.0
        if on_possessions < float(min_possessions or 0):
            return None
        off_possessions = total_possessions - on_possessions
        if off_possessions <= 0:
            return None
        off_duration = max(total_duration - on_duration, 0.0)
        off_minutes = off_duration / 60.0

        on_points_scored = float(on_stats.get("points_scored", 0) or 0)
        on_points_allowed = float(on_stats.get("points_allowed", 0) or 0)
        off_points_scored = total_points_scored - on_points_scored
        off_points_allowed = total_points_allowed - on_points_allowed

        on_rating = LineupAnalytics._rating(on_points_scored, on_points_allowed, on_possessions)
        off_rating = LineupAnalytics._rating(off_points_scored, off_points_allowed, off_possessions)

        return {
            "type": combination_type,
            "players": normalized_players,
            "segments": int(on_stats.get("segments", 0) or 0),
            "on": {
                "minutes": round(on_minutes, 1),
                "possessions": round(on_possessions, 1),
                "points_scored": round(on_points_scored, 1),
                "points_allowed": round(on_points_allowed, 1),
                **on_rating,
            },
            "off": {
                "minutes": round(off_minutes, 1),
                "possessions": round(off_possessions, 1),
                "points_scored": round(off_points_scored, 1),
                "points_allowed": round(off_points_allowed, 1),
                **off_rating,
            },
            "impact": {
                "offense_delta": round(on_rating["ortg"] - off_rating["ortg"], 1),
                "defense_delta": round(off_rating["drtg"] - on_rating["drtg"], 1),
                "net_differential": round(on_rating["net"] - off_rating["net"], 1),
            },
        }
    
    @staticmethod
    def get_lineup_efficiency_rankings(game_ids: List[int] = None, 
                                        min_possessions: int = 10,
                                        rank_by: str = "overall") -> List[Dict]:
        """
        Rank 5-man lineups by performance metrics.
        
        Args:
            game_ids: Optional game filter
            min_possessions: Minimum possessions to qualify
            rank_by: 'overall', 'offensive', or 'defensive'
        
        Returns:
            List of lineup rankings
        """
        query = LineupSegment.query
        if game_ids:
            query = query.filter(LineupSegment.game_id.in_(game_ids))
        
        segments = query.all()
        
        # Aggregate by lineup hash
        lineup_stats = defaultdict(lambda: {
            'players': [], 'segments': 0, 'points_scored': 0, 
            'points_allowed': 0, 'possessions': 0, 'total_seconds': 0,
            'games': set(), 'lineup_id': None
        })
        
        for segment in segments:
            # Handle potential JSON string vs List issue
            players = segment.players
            if isinstance(players, str):
                try:
                    players = json.loads(players)
                except:
                    players = []
            if not players:
                players = []

            if len(players) != 5:
                continue
            
            lineup_hash = segment.lineup_hash
            lineup_stats[lineup_hash]['players'] = players
            lineup_stats[lineup_hash]['segments'] += 1
            lineup_stats[lineup_hash]['points_scored'] += segment.points_scored or 0
            lineup_stats[lineup_hash]['points_allowed'] += segment.points_allowed or 0
            lineup_stats[lineup_hash]['possessions'] += segment.possessions or 0
            lineup_stats[lineup_hash]['total_seconds'] += segment.duration_seconds or 0
            lineup_stats[lineup_hash]['games'].add(segment.game_id)
            if segment.lineup_id:
                lineup_stats[lineup_hash]['lineup_id'] = segment.lineup_id
        
        # Calculate ratings and filter
        results = []
        for lineup_hash, stats in lineup_stats.items():
            if stats['possessions'] >= min_possessions:
                ortg = stats['points_scored'] / stats['possessions'] * 100
                drtg = stats['points_allowed'] / stats['possessions'] * 100
                results.append({
                    'id': stats['lineup_id'],
                    'lineup_hash': lineup_hash,
                    'players': stats['players'],
                    'segments': stats['segments'],
                    'games_played': len(stats['games']),
                    'possessions': stats['possessions'],
                    'total_minutes': round(stats['total_seconds'] / 60, 1),
                    'points_scored': stats['points_scored'],
                    'points_allowed': stats['points_allowed'],
                    'ortg': round(ortg, 1),
                    'drtg': round(drtg, 1),
                    'net_rating': round(ortg - drtg, 1)
                })
        
        # Performance-based sorting
        if rank_by == "offensive":
            results.sort(key=lambda x: (x['ortg'], x['total_minutes']), reverse=True)
        elif rank_by == "defensive":
            results.sort(key=lambda x: (x['drtg'], -x['total_minutes'])) # Lower DRtg first, then more mins
        else:
            results.sort(key=lambda x: (x['net_rating'], x['total_minutes']), reverse=True)
            
        return results
    
    @staticmethod
    def get_rotation_analysis(game_id: int) -> Dict:
        """
        Generate rotation analysis with substitution patterns.
        
        Returns:
            Dictionary with rotation timeline data
        """
        events = GameEvent.query.filter(
            GameEvent.game_id == game_id,
            GameEvent.event_type.in_(['SUB_IN', 'SUB_OUT'])
        ).order_by(GameEvent.timestamp).all()
        
        # Track player stints
        player_stints = defaultdict(list)
        current_on_court = set()
        
        for event in events:
            player = event.player_name
            quarter = event.quarter or 1
            
            if event.event_type == 'SUB_IN':
                current_on_court.add(player)
                player_stints[player].append({
                    'start_timestamp': event.timestamp,
                    'start_quarter': quarter,
                    'end_timestamp': None,
                    'end_quarter': None
                })
            elif event.event_type == 'SUB_OUT':
                current_on_court.discard(player)
                if player_stints[player] and player_stints[player][-1]['end_timestamp'] is None:
                    player_stints[player][-1]['end_timestamp'] = event.timestamp
                    player_stints[player][-1]['end_quarter'] = quarter
        
        # Close any open stints
        for player, stints in player_stints.items():
            for stint in stints:
                if stint['end_timestamp'] is None:
                    stint['end_timestamp'] = float('inf')
                    stint['end_quarter'] = 4
        
        return {
            'game_id': game_id,
            'player_stints': dict(player_stints),
            'rotation_data': LineupAnalytics._format_rotation_gantt(player_stints)
        }
    
    @staticmethod
    def _format_rotation_gantt(player_stints: Dict) -> List[Dict]:
        """Format rotation data for Gantt chart visualization."""
        gantt_data = []
        
        for player, stints in player_stints.items():
            for stint in stints:
                gantt_data.append({
                    'player': player,
                    'start': stint['start_timestamp'],
                    'end': stint['end_timestamp'],
                    'quarter': stint['start_quarter']
                })
        
        return gantt_data

    @staticmethod
    def get_game_lineup_rankings(
        game_id: int,
        top_n: int = 4,
        rank_by: str = "overall",
        min_possessions: float = 2.0,
        total_pts_scored_override: float = None,
        total_pts_allowed_override: float = None,
        total_possessions_override: float = None,
    ) -> List[Dict]:
        """
        Get top N 5-player lineups for a specific game, ranked by performance impact.
        
        Impact is calculated relative to the team's overall performance in that game.
        """
        # Filter out segments with 0 possessions (can't calculate meaningful ratings)
        segments = LineupSegment.query.filter(
            LineupSegment.game_id == game_id,
            LineupSegment.possessions > 0
        ).all()
        
        # Calculate game-wide averages for delta comparison
        game_ortg = 0
        game_drtg = 0
        if total_possessions_override and total_possessions_override > 0:
            game_ortg = (total_pts_scored_override / total_possessions_override) * 100
            game_drtg = (total_pts_allowed_override / total_possessions_override) * 100

        # Aggregate by lineup_hash
        lineup_stats = defaultdict(lambda: {
            'players': [],
            'total_seconds': 0,
            'points_scored': 0,
            'points_allowed': 0,
            'possessions': 0,
            'segment_count': 0
        })
        
        for segment in segments:
            players = segment.players
            if isinstance(players, str):
                try: players = json.loads(players)
                except: players = []
            
            if not players or len(players) != 5:
                continue
            
            key = segment.lineup_hash
            lineup_stats[key]['players'] = players
            lineup_stats[key]['total_seconds'] += segment.duration_seconds or 0
            lineup_stats[key]['points_scored'] += segment.points_scored or 0
            lineup_stats[key]['points_allowed'] += segment.points_allowed or 0
            lineup_stats[key]['possessions'] += segment.possessions or 0
            lineup_stats[key]['segment_count'] += 1
        
        results = []
        for lineup_hash, stats in lineup_stats.items():
            possessions = stats['possessions']
            if stats['total_seconds'] <= 0 or possessions < min_possessions:
                continue
                
            ortg = round(stats['points_scored'] / possessions * 100, 1)
            drtg = round(stats['points_allowed'] / possessions * 100, 1)
            net = round(ortg - drtg, 1)
            
            # Calculate impact deltas
            off_delta = round(ortg - game_ortg, 1)
            def_delta = round(game_drtg - drtg, 1) # Higher is better (positive = allowed fewer than avg)
            net_delta = round(net - (game_ortg - game_drtg), 1)
            
            results.append({
                'lineup_hash': lineup_hash,
                'players': stats['players'],
                'total_seconds': stats['total_seconds'],
                'total_minutes': round(stats['total_seconds'] / 60, 1),
                'points_scored': stats['points_scored'],
                'points_allowed': stats['points_allowed'],
                'possessions': stats['possessions'],
                'segment_count': stats['segment_count'],
                'ortg': ortg,
                'drtg': drtg,
                'net_rating': net,
                'impact': {
                    'offense_delta': off_delta,
                    'defense_delta': def_delta,
                    'net_delta': net_delta
                }
            })
        
        # Sort by impact delta (higher is always better)
        if rank_by == "offensive":
            results.sort(key=lambda x: (x['impact']['offense_delta'], x['total_seconds']), reverse=True)
        elif rank_by == "defensive":
            results.sort(key=lambda x: (x['impact']['defense_delta'], x['total_seconds']), reverse=True)
        else:
            results.sort(key=lambda x: (x['impact']['net_delta'], x['total_seconds']), reverse=True)
            
        return results[:top_n]


# =============================================================================
# POSSESSION RECONSTRUCTION
# =============================================================================

class PossessionReconstructor:
    """Parse GameEvent logs to define distinct possessions."""
    
    # Events that end a possession
    POSSESSION_END_EVENTS = [
        'SHOT_2PT', 'SHOT_3PT', 'TURNOVER', 
        'FOUL_DEFENSIVE', 'OPP_SCORE'
    ]
    
    # Events that start a new possession
    POSSESSION_START_EVENTS = [
        'REBOUND_DEFENSIVE', 'OPP_TURNOVER', 'OPP_MISS',
        'SUB_IN', 'TIMEOUT'
    ]
    
    @staticmethod
    def reconstruct_possessions(game_id: int) -> List[Dict]:
        """
        Reconstruct all possessions from game events using high-performance Rust implementation.
        
        Args:
            game_id: Game to analyze
        
        Returns:
            List of possession dictionaries
        """
        events = GameEvent.query.filter(
            GameEvent.game_id == game_id
        ).order_by(GameEvent.timestamp).all()
        
        if not events:
            return []
        
        # Prepare event data for Rust
        event_data = []
        for e in events:
            event_data.append({
                'id': e.id,
                'event_type': e.event_type,
                'timestamp': float(e.timestamp or 0),
                'quarter': e.quarter or 1,
                'shot_attempt': e.shot_attempt
            })
            
        return rust_analytics.reconstruct_possessions(event_data)
    
    @staticmethod
    def save_possessions(game_id: int) -> int:
        """
        Reconstruct and save possessions to database.
        
        Returns:
            Number of possessions saved
        """
        # Clear existing possessions for this game
        Possession.query.filter_by(game_id=game_id).delete()
        
        possessions_data = PossessionReconstructor.reconstruct_possessions(game_id)
        
        for p_data in possessions_data:
            possession = Possession(
                game_id=game_id,
                start_event_id=p_data['start_event_id'],
                end_event_id=p_data.get('end_event_id'),
                team_possession=p_data['team_possession'],
                quarter=p_data.get('quarter'),
                points=p_data.get('points', 0)
            )
            db.session.add(possession)
        
        db.session.commit()
        return len(possessions_data)


# =============================================================================
# ANALYTICS ENGINE - Aggregation Queries
# =============================================================================

class AnalyticsEngine:
    """
    High-performance analytics engine using optimized aggregation queries.
    Replaces N+1 query patterns with single aggregation queries.
    """
    
    @staticmethod
    def get_team_plays_rankings(game_ids: List[int] = None) -> List[Dict]:
        """
        Get play effectiveness rankings using a single aggregation query.
        Replaces the previous N+1 query pattern.
        
        Args:
            game_ids: Optional list of games to include
        
        Returns:
            List of plays with their effectiveness metrics
        """
        # Single aggregation query instead of loops
        query = db.session.query(
            Play.id.label('play_id'),
            Play.name.label('play_name'),
            Play.play_type.label('play_type'),
            func.count(ShotEvent.id).label('total_shots'),
            func.sum(case((ShotEvent.result == 'made', 1), else_=0)).label('makes'),
            func.sum(ShotEvent.points).label('total_points'),
            func.avg(ShotEvent.points).label('avg_points'),
            Play.description.label('description')
        ).outerjoin(
            ShotEvent, ShotEvent.play_id == Play.id
        )
        
        if game_ids:
            query = query.filter(ShotEvent.game_id.in_(game_ids))
        
        results = query.group_by(Play.id, Play.name, Play.play_type, Play.description).all()
        
        rankings = []
        for r in results:
            total_shots = r.total_shots or 0
            makes = r.makes or 0
            fg_pct = round(makes / total_shots * 100, 1) if total_shots > 0 else 0
            
            rankings.append({
                'play_id': r.play_id,
                'play_name': r.play_name,
                'play_type': r.play_type,
                'total_shots': total_shots,
                'makes': makes,
                'fg_pct': fg_pct,
                'total_points': r.total_points or 0,
                'avg_points': round(r.avg_points, 2) if r.avg_points else 0,
                'description': r.description
            })
        
        return sorted(rankings, key=lambda x: x['total_points'] or 0, reverse=True)
    
    @staticmethod
    def get_player_season_stats(player_name: str, game_type: str = 'ALL') -> Dict:
        """
        Get comprehensive season statistics for a player using aggregation.
        
        Args:
            player_name: Player to analyze
            game_type: Filter by game type ('ALL', 'Season', 'Friendly')
        
        Returns:
            Dictionary with all player statistics
        """
        query = db.session.query(
            func.count(PlayerStat.id).label('games'),
            func.sum(PlayerStat.points).label('points'),
            func.sum(PlayerStat.fgm).label('fgm'),
            func.sum(PlayerStat.fga).label('fga'),
            func.sum(PlayerStat.tpm).label('tpm'),
            func.sum(PlayerStat.tpa).label('tpa'),
            func.sum(PlayerStat.ftm).label('ftm'),
            func.sum(PlayerStat.fta).label('fta'),
            func.sum(PlayerStat.reb).label('reb'),
            func.sum(PlayerStat.oreb).label('oreb'),
            func.sum(PlayerStat.dreb).label('dreb'),
            func.sum(PlayerStat.ast).label('ast'),
            func.sum(PlayerStat.stl).label('stl'),
            func.sum(PlayerStat.blk).label('blk'),
            func.sum(PlayerStat.tov).label('tov'),
            func.sum(PlayerStat.pf).label('pf'),
            func.sum(PlayerStat.plus_minus).label('plus_minus')
        ).filter(PlayerStat.player_name == player_name)
        
        if game_type == 'Season':
            query = query.join(Game).filter(Game.game_type == 'Season')
        elif game_type == 'Friendly':
            query = query.join(Game).filter(Game.game_type == 'Friendly')
        
        result = query.first()
        
        if not result or result.games == 0:
            return {}
        
        games = result.games
        totals = {
            'games': games,
            'points': result.points or 0,
            'fgm': result.fgm or 0,
            'fga': result.fga or 0,
            'tpm': result.tpm or 0,
            'tpa': result.tpa or 0,
            'ftm': result.ftm or 0,
            'fta': result.fta or 0,
            'reb': result.reb or 0,
            'oreb': result.oreb or 0,
            'dreb': result.dreb or 0,
            'ast': result.ast or 0,
            'stl': result.stl or 0,
            'blk': result.blk or 0,
            'tov': result.tov or 0,
            'pf': result.pf or 0,
            'plus_minus': result.plus_minus or 0
        }
        
        # Calculate advanced metrics
        totals['ppg'] = round(totals['points'] / games, 1)
        totals['rpg'] = round(totals['reb'] / games, 1)
        totals['apg'] = round(totals['ast'] / games, 1)
        totals['fg_pct'] = safe_percentage(totals['fgm'], totals['fga'])
        totals['tp_pct'] = safe_percentage(totals['tpm'], totals['tpa'])
        totals['ft_pct'] = safe_percentage(totals['ftm'], totals['fta'])
        totals['ts_pct'] = calculate_ts_percent(
            totals['points'], totals['fga'], totals['fta']
        )
        totals['efg_pct'] = safe_percentage(
            totals['fgm'] + 0.5 * totals['tpm'], totals['fga']
        )
        
        # True Usage Rate
        player_poss = totals['fga'] + (FT_ATTEMPT_WEIGHT * totals['fta']) + totals['tov']
        totals['possessions'] = round(player_poss, 1)
        totals['usage_rate'] = round(player_poss / games, 1)  # Per game
        
        # Points Per Shot
        totals['pps'] = round(safe_divide(totals['points'], totals['fga']), 2)
        
        return totals
    
    @staticmethod
    def get_four_factors(game_id: int = None, game_ids: List[int] = None) -> Dict:
        """
        Calculate Dean Oliver's Four Factors.
        
        1. Effective Field Goal Percentage (eFG%)
        2. Turnover Percentage (TOV%)
        3. Offensive Rebound Percentage (ORB%)
        4. Free Throw Rate (FTR)
        
        Args:
            game_id: Single game to analyze
            game_ids: Multiple games to analyze
        
        Returns:
            Dictionary with four factors
        """
        query = db.session.query(
            func.sum(PlayerStat.fgm).label('fgm'),
            func.sum(PlayerStat.fga).label('fga'),
            func.sum(PlayerStat.tpm).label('tpm'),
            func.sum(PlayerStat.tpa).label('tpa'),
            func.sum(PlayerStat.ftm).label('ftm'),
            func.sum(PlayerStat.fta).label('fta'),
            func.sum(PlayerStat.oreb).label('oreb'),
            func.sum(PlayerStat.dreb).label('dreb'),
            func.sum(PlayerStat.reb).label('reb'),
            func.sum(PlayerStat.tov).label('tov'),
            func.sum(PlayerStat.points).label('points')
        )
        
        if game_id:
            query = query.filter(PlayerStat.game_id == game_id)
        elif game_ids:
            query = query.filter(PlayerStat.game_id.in_(game_ids))
        
        result = query.first()
        
        if not result:
            return {}
        
        fgm = result.fgm or 0
        fga = result.fga or 0
        tpm = result.tpm or 0
        tov = result.tov or 0
        oreb = result.oreb or 0
        ftm = result.ftm or 0
        fta = result.fta or 0
        points = result.points or 0
        
        # Calculate possessions for TOV%
        possessions = fga + (FT_ATTEMPT_WEIGHT * fta) - oreb + tov
        
        return {
            'efg_pct': safe_percentage(fgm + 0.5 * tpm, fga),
            'tov_pct': safe_percentage(tov, possessions),
            'orb_pct': safe_percentage(oreb, result.reb or 1),
            'ft_rate': safe_percentage(ftm, fga),
            'ts_pct': calculate_ts_percent(points, fga, fta)
        }


def calculate_ts_percent(points: int, fga: int, fta: int) -> float:
    """Calculate True Shooting Percentage."""
    denominator = 2 * (fga + FT_ATTEMPT_WEIGHT * fta)
    return safe_percentage(points, denominator)


# =============================================================================
# SHOT CHART ANALYTICS
# =============================================================================

class ShotChartAnalytics:
    """Shot chart and court mapping analytics."""
    
    @staticmethod
    def get_shot_chart_data(game_id: int = None, player_name: str = None,
                            play_id: int = None, game_ids: List[int] = None) -> List[Dict]:
        """
        Get shot chart data with coordinates and results.
        
        Args:
            game_id: Single game filter
            player_name: Player filter
            play_id: Play type filter
            game_ids: Multiple games filter
        
        Returns:
            List of shot dictionaries with coordinates
        """
        query = ShotEvent.query
        
        if game_id:
            query = query.filter(ShotEvent.game_id == game_id)
        elif game_ids:
            query = query.filter(ShotEvent.game_id.in_(game_ids))
        
        if player_name:
            query = query.filter(ShotEvent.player_name == player_name)
        if play_id:
            query = query.filter(ShotEvent.play_id == play_id)
        
        shots = query.all()
        
        return [
            {
                'id': s.id,
                'game_id': s.game_id,
                'player_name': s.player_name,
                'shot_type': s.shot_type,
                'result': s.result,
                'points': s.points,
                'x_loc': s.x_loc,
                'y_loc': s.y_loc,
                'quarter': s.quarter,
                'play_id': s.play_id,
                'zone': classify_shot_zone(s.x_loc, s.y_loc, s.shot_type)
            }
            for s in shots
        ]
    
    @staticmethod
    def get_heatmap_data(game_ids: List[int] = None, player_name: str = None) -> Dict:
        """
        Generate heatmap data for shot zones using optimized Rust backend.
        
        Returns:
            Dict mapping zone names to {makes, attempts, frequency, fg_pct, pps}
        """
        query = ShotEvent.query
        if game_ids:
            query = query.filter(ShotEvent.game_id.in_(game_ids))
        if player_name:
            query = query.filter(ShotEvent.player_name == player_name)
            
        shots = query.all()
        
        # Prepare data for Rust
        shot_data = [
            {
                "points": s.points or 0,
                "x_loc": s.x_loc,
                "y_loc": s.y_loc,
                "shot_type": s.shot_type or ""
            }
            for s in shots
        ]
        
        # Calculate in Rust
        # The wrapper in core/rust_analytics.py already does json.loads
        heatmap_list = rust_analytics.calculate_shot_heatmap(shot_data)
        
        if not heatmap_list:
            return {}
        
        # Convert list back to dict keyed by zone
        return {item['zone']: item for item in heatmap_list}
    
    @staticmethod
    def get_hexbin_data(game_ids: List[int] = None, player_name: str = None,
                        hex_size: int = 50) -> List[Dict]:
        """
        Generate hexbin data for shot chart visualization.
        
        Args:
            hex_size: Size of each hexagon in coordinate units
        
        Returns:
            List of hexbin data with aggregated stats
        """
        shots = ShotChartAnalytics.get_shot_chart_data(
            player_name=player_name, game_ids=game_ids
        )
        
        # Group shots into hexbins
        hexbins = defaultdict(lambda: {'makes': 0, 'attempts': 0, 'points': 0})
        
        for shot in shots:
            if shot['x_loc'] is None or shot['y_loc'] is None:
                continue
            
            # Calculate hexbin coordinates
            hex_x = int(shot['x_loc'] // hex_size) * hex_size + hex_size // 2
            hex_y = int(shot['y_loc'] // hex_size) * hex_size + hex_size // 2
            hex_key = (hex_x, hex_y)
            
            hexbins[hex_key]['attempts'] += 1
            hexbins[hex_key]['points'] += shot['points'] or 0
            if shot['result'] == 'made':
                hexbins[hex_key]['makes'] += 1
        
        # Convert to list format
        hexbin_list = []
        for (x, y), stats in hexbins.items():
            fg_pct = safe_percentage(stats['makes'], stats['attempts'])
            hexbin_list.append({
                'x': x,
                'y': y,
                'attempts': stats['attempts'],
                'makes': stats['makes'],
                'fg_pct': fg_pct,
                'points': stats['points']
            })
        
        return hexbin_list
