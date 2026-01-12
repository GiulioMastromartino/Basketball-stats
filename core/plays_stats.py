"""Plays-based statistics aggregation module.

Provides efficient data aggregation for play-based analytics including:
- Game-level plays statistics
- Player performance by play type
- Team-level player rankings per play
"""

from sqlalchemy import func, desc, and_
from flask import current_app
from datetime import datetime


class PlaysStatsAggregator:
    """Aggregates plays-based statistics from database."""

    @staticmethod
    def get_game_plays_stats(game_id):
        """Get all plays statistics for a game.
        
        Args:
            game_id: Game ID to analyze
            
        Returns:
            dict with keys:
                - game: Game object
                - plays_used: List of plays with stats
                - plays_coverage: Percentage of plays used
                - shots_by_play: Dict mapping play_id to shot details
                - total_attempts: Total shots attempted
        """
        from web import db
        from web.models import Game, ShotEvent, Play
        
        game = Game.query.get(game_id)
        if not game:
            return {'error': 'Game not found', 'status': 404}
        
        try:
            # Get all plays stats for this game
            plays_stats = db.session.query(
                Play.id,
                Play.name,
                func.count(ShotEvent.id).label('attempts'),
                func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made'),
                func.sum(ShotEvent.points).label('points')
            ).outerjoin(
                ShotEvent, and_(
                    Play.id == ShotEvent.play_id,
                    ShotEvent.game_id == game_id
                )
            ).filter(
                Play.is_active == True
            ).group_by(
                Play.id, Play.name
            ).all()
            
            # Filter out plays with no attempts
            plays_used = []
            total_attempts = 0
            plays_with_attempts = 0
            
            for play_id, play_name, attempts, made, points in plays_stats:
                if attempts and attempts > 0:
                    fg_pct = (made / attempts * 100) if attempts > 0 else 0
                    ppa = (points / attempts) if attempts > 0 else 0
                    
                    plays_used.append({
                        'id': play_id,
                        'name': play_name,
                        'attempts': attempts,
                        'made': made,
                        'missed': attempts - made,
                        'fg_pct': round(fg_pct, 1),
                        'points': points,
                        'ppa': round(ppa, 2)
                    })
                    total_attempts += attempts
                    plays_with_attempts += 1
            
            # Calculate coverage percentage
            all_plays_count = Play.query.filter(Play.is_active == True).count()
            plays_coverage = round((plays_with_attempts / all_plays_count * 100) if all_plays_count > 0 else 0, 1)
            
            # Get shots by play for detailed breakdown
            shots_by_play = db.session.query(
                ShotEvent.play_id,
                ShotEvent.player_name,
                ShotEvent.result,
                ShotEvent.points
            ).filter(
                ShotEvent.game_id == game_id
            ).all()
            
            return {
                'game': game,
                'plays_used': plays_used,
                'plays_coverage': plays_coverage,
                'shots_by_play': shots_by_play,
                'total_attempts': total_attempts,
                'status': 200
            }
        except Exception as e:
            current_app.logger.error(f"Error getting game plays stats: {str(e)}")
            return {'error': str(e), 'status': 500}

    @staticmethod
    def get_player_plays_stats(player_name, game_id=None):
        """Get player's performance breakdown by play type.
        
        Args:
            player_name: Player name to analyze
            game_id: Optional game ID to limit analysis to single game
            
        Returns:
            dict with keys:
                - player_name: Player name
                - plays_stats: List of plays with player's performance
                - total_attempts: Total shots attempted
                - total_made: Total shots made
                - overall_fg_pct: Overall field goal percentage
                - total_points: Total points scored
        """
        from web import db
        from web.models import ShotEvent, Play, Game
        
        try:
            query = db.session.query(
                Play.id,
                Play.name,
                func.count(ShotEvent.id).label('attempts'),
                func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made'),
                func.sum(ShotEvent.points).label('points')
            ).outerjoin(
                ShotEvent, Play.id == ShotEvent.play_id
            ).filter(
                ShotEvent.player_name == player_name
            )
            
            if game_id:
                query = query.filter(ShotEvent.game_id == game_id)
            
            plays_stats_raw = query.group_by(
                Play.id, Play.name
            ).all()
            
            plays_stats = []
            total_attempts = 0
            total_made = 0
            total_points = 0
            
            for play_id, play_name, attempts, made, points in plays_stats_raw:
                if attempts and attempts > 0:
                    fg_pct = (made / attempts * 100) if attempts > 0 else 0
                    ppa = (points / attempts) if attempts > 0 else 0
                    
                    plays_stats.append({
                        'play_id': play_id,
                        'play_name': play_name,
                        'attempts': attempts,
                        'made': made,
                        'fg_pct': round(fg_pct, 1),
                        'points': points,
                        'ppa': round(ppa, 2)
                    })
                    total_attempts += attempts
                    total_made += made
                    total_points += points
            
            overall_fg_pct = (total_made / total_attempts * 100) if total_attempts > 0 else 0
            
            return {
                'player_name': player_name,
                'plays_stats': plays_stats,
                'total_attempts': total_attempts,
                'total_made': total_made,
                'overall_fg_pct': round(overall_fg_pct, 1),
                'total_points': total_points,
                'game_id': game_id,
                'status': 200
            }
        except Exception as e:
            current_app.logger.error(f"Error getting player plays stats: {str(e)}")
            return {'error': str(e), 'status': 500}

    @staticmethod
    def get_team_plays_rankings(game_id):
        """Get player rankings for each play type.
        
        Args:
            game_id: Game ID to analyze
            
        Returns:
            dict with keys:
                - game: Game object
                - plays: List of plays with player rankings
                - total_plays_used: Count of plays used
                - plays_coverage: Percentage of plays used
        """
        from web import db
        from web.models import Game, ShotEvent, Play
        
        game = Game.query.get(game_id)
        if not game:
            return {'error': 'Game not found', 'status': 404}
        
        try:
            # Get all plays for this game
            all_plays = Play.query.filter(Play.is_active == True).all()
            
            plays_with_rankings = []
            plays_used = 0
            
            for play in all_plays:
                # Get player rankings for this play
                player_rankings = db.session.query(
                    ShotEvent.player_name,
                    func.count(ShotEvent.id).label('attempts'),
                    func.sum(func.cast(ShotEvent.result == 'Made', db.Integer)).label('made'),
                    func.sum(ShotEvent.points).label('points')
                ).filter(
                    ShotEvent.game_id == game_id,
                    ShotEvent.play_id == play.id
                ).group_by(
                    ShotEvent.player_name
                ).order_by(
                    desc('points')
                ).all()
                
                if player_rankings:
                    plays_used += 1
                    
                    rankings_data = []
                    for player_name, attempts, made, points in player_rankings:
                        fg_pct = (made / attempts * 100) if attempts > 0 else 0
                        ppa = (points / attempts) if attempts > 0 else 0
                        
                        rankings_data.append({
                            'player_name': player_name,
                            'attempts': attempts,
                            'made': made,
                            'fg_pct': round(fg_pct, 1),
                            'points': points,
                            'ppa': round(ppa, 2)
                        })
                    
                    plays_with_rankings.append({
                        'play_id': play.id,
                        'play_name': play.name,
                        'player_rankings': rankings_data
                    })
            
            plays_coverage = round((plays_used / len(all_plays) * 100) if len(all_plays) > 0 else 0, 1)
            
            return {
                'game': game,
                'plays': plays_with_rankings,
                'total_plays_used': plays_used,
                'plays_coverage': plays_coverage,
                'status': 200
            }
        except Exception as e:
            current_app.logger.error(f"Error getting team plays rankings: {str(e)}")
            return {'error': str(e), 'status': 500}

    @staticmethod
    def get_all_plays():
        """Get list of all active plays.
        
        Returns:
            List of Play objects
        """
        from web.models import Play
        return Play.query.filter(Play.is_active == True).order_by(Play.name).all()
