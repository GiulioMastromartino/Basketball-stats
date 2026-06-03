"""
Test data factories for basketball stats tests.

Provides factory classes to easily create test data with sensible defaults.
Usage:
    game = GameFactory.create()
    stat = PlayerStatFactory.create(game=game, points=25)
"""

from datetime import datetime
from web import db
from core.models import (
    User, Game, PlayerStat, ShotEvent, GameEvent,
    Play, PlayType, LineupSegment, Possession
)


class UserFactory:
    """Factory for creating User instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, **kwargs):
        cls._counter += 1
        defaults = {
            'username': f'user_{cls._counter}',
            'email': f'user_{cls._counter}@test.com',
            'role': 'editor'
        }
        defaults.update(kwargs)
        
        user = User(**defaults)
        password = kwargs.pop('password', 'password123')
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        return user
    
    @classmethod
    def create_admin(cls, **kwargs):
        kwargs['role'] = 'admin'
        return cls.create(**kwargs)
    
    @classmethod
    def create_editor(cls, **kwargs):
        kwargs['role'] = 'editor'
        return cls.create(**kwargs)


class GameFactory:
    """Factory for creating Game instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, **kwargs):
        cls._counter += 1
        date_offset = cls._counter
        
        defaults = {
            'date': f'{date_offset:02d}-02-2024',
            'opponent': f'Opponent {cls._counter}',
            'team_score': 70,
            'opponent_score': 65,
            'result': 'W',
            'game_type': 'Season',
            'sort_date': f'2024-02-{date_offset:02d}',
            'source': 'MANUAL'
        }
        defaults.update(kwargs)
        
        game = Game(**defaults)
        db.session.add(game)
        db.session.commit()
        return game
    
    @classmethod
    def create_batch(cls, count, **kwargs):
        """Create multiple games."""
        return [cls.create(**kwargs) for _ in range(count)]
    
    @classmethod
    def create_with_stats(cls, player_count=5, **kwargs):
        """Create a game with player stats."""
        game = cls.create(**kwargs)
        for i in range(player_count):
            PlayerStatFactory.create(game=game, player_name=f'Player {i+1}')
        return game


class PlayerStatFactory:
    """Factory for creating PlayerStat instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, game=None, **kwargs):
        cls._counter += 1
        
        if game is None:
            game = GameFactory.create()
        
        defaults = {
            'player_name': f'Player {cls._counter}',
            'minutes': '20:00',
            'points': 10,
            'fgm': 4,
            'fga': 8,
            'fg_percent': 50.0,
            'tpm': 1,
            'tpa': 3,
            'tp_percent': 33.3,
            'ftm': 1,
            'fta': 2,
            'ft_percent': 50.0,
            'oreb': 1,
            'dreb': 3,
            'reb': 4,
            'ast': 2,
            'stl': 1,
            'blk': 0,
            'tov': 2,
            'pf': 2,
            'plus_minus': 0
        }
        defaults.update(kwargs)
        
        stat = PlayerStat(game_id=game.id, **defaults)
        db.session.add(stat)
        db.session.commit()
        return stat
    
    @classmethod
    def create_star_player(cls, game=None, **kwargs):
        """Create a high-performing player stat."""
        star_defaults = {
            'points': 25,
            'fgm': 10,
            'fga': 18,
            'tpm': 3,
            'tpa': 6,
            'ftm': 2,
            'fta': 3,
            'oreb': 2,
            'dreb': 6,
            'ast': 5,
            'stl': 3,
            'blk': 1,
            'tov': 2,
            'plus_minus': 15
        }
        star_defaults.update(kwargs)
        return cls.create(game=game, **star_defaults)
    
    @classmethod
    def create_batch(cls, game, count, **kwargs):
        """Create multiple player stats for a game."""
        return [cls.create(game=game, **kwargs) for _ in range(count)]


class ShotEventFactory:
    """Factory for creating ShotEvent instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, game=None, **kwargs):
        cls._counter += 1
        
        if game is None:
            game = GameFactory.create()
        
        defaults = {
            'player_name': f'Shooter {cls._counter}',
            'shot_type': '2pt',
            'result': 'made',
            'points': 2,
            'x_loc': 250.0,
            'y_loc': 100.0,
            'quarter': 1
        }
        defaults.update(kwargs)
        
        shot = ShotEvent(game_id=game.id, **defaults)
        db.session.add(shot)
        db.session.commit()
        return shot
    
    @classmethod
    def create_three_pointer(cls, game=None, made=True, **kwargs):
        """Create a 3-point shot."""
        kwargs['shot_type'] = '3pt'
        kwargs['result'] = 'made' if made else 'missed'
        kwargs['points'] = 3 if made else 0
        return cls.create(game=game, **kwargs)
    
    @classmethod
    def create_free_throw(cls, game=None, made=True, **kwargs):
        """Create a free throw shot."""
        kwargs['shot_type'] = 'ft'
        kwargs['result'] = 'made' if made else 'missed'
        kwargs['points'] = 1 if made else 0
        return cls.create(game=game, **kwargs)


class GameEventFactory:
    """Factory for creating GameEvent instances."""
    
    _counter = 0
    _timestamp = 1000
    
    @classmethod
    def create(cls, game=None, **kwargs):
        cls._counter += 1
        cls._timestamp += 100
        
        if game is None:
            game = GameFactory.create()
        
        defaults = {
            'event_type': 'SHOT_2PT',
            'player_name': f'Player {cls._counter}',
            'detail': None,
            'timestamp': cls._timestamp,
            'quarter': 1,
            'time_remaining': '8:00',
            'score_margin': 0,
            'game_seconds': 120,
            'possession_number': 1
        }
        defaults.update(kwargs)
        
        event = GameEvent(game_id=game.id, **defaults)
        db.session.add(event)
        db.session.commit()
        return event
    
    @classmethod
    def create_substitution(cls, game=None, player_name=None, sub_in=True):
        """Create a substitution event."""
        return cls.create(
            game=game,
            event_type='SUB_IN' if sub_in else 'SUB_OUT',
            player_name=player_name or f'Player {cls._counter}'
        )
    
    @classmethod
    def create_opponent_score(cls, game=None, points=2, shot_type='2pt'):
        """Create an opponent score event."""
        import json
        return cls.create(
            game=game,
            event_type='OPP_SCORE',
            player_name=None,
            detail=json.dumps({'points': points, 'shot_type': shot_type, 'result': 'made'})
        )
    
    @classmethod
    def create_turnover(cls, game=None, player_name=None):
        """Create a turnover event."""
        return cls.create(
            game=game,
            event_type='TURNOVER',
            player_name=player_name or f'Player {cls._counter}'
        )
    
    @classmethod
    def create_ft_trip(cls, game=None, player_name=None, ftm=1, fta=2):
        """Create a FT trip event."""
        import json
        return cls.create(
            game=game,
            event_type='FT',
            player_name=player_name or f'Player {cls._counter}',
            detail=json.dumps({'ftm': ftm, 'fta': fta})
        )


class PlayFactory:
    """Factory for creating Play instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, **kwargs):
        cls._counter += 1
        
        # Create play type if not provided
        play_type_id = kwargs.get('play_type_id')
        if play_type_id is None:
            play_type = PlayType(name=f'Play Type {cls._counter}')
            db.session.add(play_type)
            db.session.commit()
            play_type_id = play_type.id
        
        defaults = {
            'name': f'Play {cls._counter}',
            'play_type_id': play_type_id,
            'description': f'Description for play {cls._counter}'
        }
        defaults.update(kwargs)
        
        play = Play(**defaults)
        db.session.add(play)
        db.session.commit()
        return play


class LineupSegmentFactory:
    """Factory for creating LineupSegment instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, game=None, **kwargs):
        cls._counter += 1
        
        if game is None:
            game = GameFactory.create()
        
        defaults = {
            'start_timestamp': cls._counter * 100,
            'end_timestamp': (cls._counter + 1) * 100,
            'quarter': 1,
            'players': ['Player 1', 'Player 2', 'Player 3', 'Player 4', 'Player 5'],
            'lineup_hash': 'abc123',
            'points_scored': 5,
            'points_allowed': 3,
            'possessions': 4
        }
        defaults.update(kwargs)
        
        # Generate lineup hash if players provided
        if 'players' in defaults and isinstance(defaults['players'], list):
            import hashlib
            sorted_players = sorted(defaults['players'])
            defaults['lineup_hash'] = hashlib.md5(
                ','.join(sorted_players).encode()
            ).hexdigest()
        
        segment = LineupSegment(game_id=game.id, **defaults)
        db.session.add(segment)
        db.session.commit()
        return segment


class PossessionFactory:
    """Factory for creating Possession instances."""
    
    _counter = 0
    
    @classmethod
    def create(cls, game=None, start_event=None, **kwargs):
        cls._counter += 1
        
        if game is None:
            game = GameFactory.create()
        
        if start_event is None:
            start_event = GameEventFactory.create(game=game)
        
        defaults = {
            'quarter': 1,
            'team_possession': True,
            'points': 2
        }
        defaults.update(kwargs)
        
        possession = Possession(
            game_id=game.id,
            start_event_id=start_event.id,
            **defaults
        )
        db.session.add(possession)
        db.session.commit()
        return possession


# =============================================================================
# Utility Functions
# =============================================================================

def create_full_game_scenario():
    """
    Create a complete game scenario with all related entities.
    
    Returns:
        dict: Contains game, stats, shots, and events
    """
    game = GameFactory.create()
    stats = PlayerStatFactory.create_batch(game, 5)
    
    # Create shot events for each stat
    shots = []
    for stat in stats:
        shots.append(ShotEventFactory.create(game=game, player_name=stat.player_name))
    
    # Create game events
    events = [
        GameEventFactory.create_substitution(game=game, sub_in=True),
        GameEventFactory.create(game=game, player_name=stats[0].player_name),
        GameEventFactory.create_opponent_score(game=game),
    ]
    
    return {
        'game': game,
        'stats': stats,
        'shots': shots,
        'events': events
    }
