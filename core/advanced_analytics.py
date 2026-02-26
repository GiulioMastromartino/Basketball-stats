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
        query = LineupSegment.query
        if game_ids:
            query = query.filter(LineupSegment.game_id.in_(game_ids))
        
        segments = query.all()
        
        # Prepare data for high-performance aggregator
        segment_data = []
        for s in segments:
            players = s.players
            if isinstance(players, str):
                try: players = json.loads(players)
                except: players = []
            
            segment_data.append({
                'players': players or [],
                'points_scored': s.points_scored or 0,
                'points_allowed': s.points_allowed or 0,
                'possessions': s.possessions or 0
            })

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
        query = LineupSegment.query
        if game_ids:
            query = query.filter(LineupSegment.game_id.in_(game_ids))
        
        segments = query.all()
        
        # Prepare data for high-performance aggregator
        segment_data = []
        for s in segments:
            players = s.players
            if isinstance(players, str):
                try: players = json.loads(players)
                except: players = []
            
            segment_data.append({
                'players': players or [],
                'points_scored': s.points_scored or 0,
                'points_allowed': s.points_allowed or 0,
                'possessions': s.possessions or 0
            })

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
    def get_lineup_efficiency_rankings(game_ids: List[int] = None, 
                                        min_possessions: int = 10) -> List[Dict]:
        """
        Rank 5-man lineups by Net Rating.
        
        Args:
            game_ids: Optional game filter
            min_possessions: Minimum possessions to qualify
        
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
            'points_allowed': 0, 'possessions': 0
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
        
        # Calculate ratings and filter
        results = []
        for lineup_hash, stats in lineup_stats.items():
            if stats['possessions'] >= min_possessions:
                ortg = stats['points_scored'] / stats['possessions'] * 100
                drtg = stats['points_allowed'] / stats['possessions'] * 100
                results.append({
                    'lineup_hash': lineup_hash,
                    'players': stats['players'],
                    'segments': stats['segments'],
                    'possessions': stats['possessions'],
                    'points_scored': stats['points_scored'],
                    'points_allowed': stats['points_allowed'],
                    'ortg': round(ortg, 1),
                    'drtg': round(drtg, 1),
                    'net_rating': round(ortg - drtg, 1)
                })
        
        return sorted(results, key=lambda x: x['net_rating'], reverse=True)
    
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
    def get_game_lineup_rankings(game_id: int, top_n: int = 4) -> List[Dict]:
        """
        Get top N 5-player lineups for a specific game, ranked by minutes played.
        
        This provides per-game lineup analysis to see which combinations played
        the most and performed best together.
        
        Args:
            game_id: ID of the game to analyze
            top_n: Number of top lineups to return (default: 4)
        
        Returns:
            List of dictionaries with lineup stats sorted by total_seconds descending:
            - lineup_hash: Unique identifier for the lineup
            - players: List of 5 player names
            - total_seconds: Total time on court together
            - total_minutes: Time in minutes (rounded)
            - points_scored, points_allowed, possessions
            - ortg: Offensive rating (points per 100 possessions)
            - drtg: Defensive rating (points allowed per 100 possessions)
            - net_rating: ortg - drtg
            - segment_count: Number of separate stints this lineup played
        """
        segments = LineupSegment.query.filter_by(game_id=game_id).all()
        
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
            
            key = segment.lineup_hash
            lineup_stats[key]['players'] = players
            lineup_stats[key]['total_seconds'] += segment.duration_seconds or 0
            lineup_stats[key]['points_scored'] += segment.points_scored or 0
            lineup_stats[key]['points_allowed'] += segment.points_allowed or 0
            lineup_stats[key]['possessions'] += segment.possessions or 0
            lineup_stats[key]['segment_count'] += 1
        
        # Calculate ratings and build results
        results = []
        for lineup_hash, stats in lineup_stats.items():
            possessions = stats['possessions'] or 1  # Avoid division by zero
            ortg = round(stats['points_scored'] / possessions * 100, 1)
            drtg = round(stats['points_allowed'] / possessions * 100, 1)
            
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
                'net_rating': round(ortg - drtg, 1)
            })
        
        # Sort by minutes played (descending)
        return sorted(results, key=lambda x: x['total_seconds'], reverse=True)[:top_n]


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
        Generate heatmap data for shot zones.
        
        Returns:
            Dictionary with zone-based shooting percentages
        """
        shots = ShotChartAnalytics.get_shot_chart_data(
            player_name=player_name, game_ids=game_ids
        )
        
        zone_stats = defaultdict(lambda: {'makes': 0, 'attempts': 0, 'points': 0})
        
        for shot in shots:
            zone = shot['zone']
            zone_stats[zone]['attempts'] += 1
            zone_stats[zone]['points'] += shot['points'] or 0
            if shot['result'] == 'made':
                zone_stats[zone]['makes'] += 1
        
        heatmap = {}
        for zone, stats in zone_stats.items():
            fg_pct = safe_percentage(stats['makes'], stats['attempts'])
            expected = get_expected_value(zone)
            actual_pps = safe_divide(stats['points'], stats['attempts'])
            
            heatmap[zone] = {
                'attempts': stats['attempts'],
                'makes': stats['makes'],
                'fg_pct': fg_pct,
                'expected_value': expected,
                'actual_pps': round(actual_pps, 2),
                'efficiency_delta': round(actual_pps - expected, 2)
            }
        
        return heatmap
    
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
