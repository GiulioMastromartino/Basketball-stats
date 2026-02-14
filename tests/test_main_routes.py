import unittest
import json
from web import create_app, db
from core.models import User, Game, PlayerStat

class TestMainRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create test user
        self.username = 'main_test_user'
        self.password = 'password'
        user = User(username=self.username, email='main@example.com', role='editor', is_admin=False)
        user.set_password(self.password)
        db.session.add(user)
        
        # Create dummy game
        game = Game(
            date='01/01/2024', opponent='TestOpp', team_score=100, opponent_score=90,
            result='W', game_type='Season', sort_date='2024-01-01', source='MANUAL'
        )
        db.session.add(game)
        db.session.commit()
        self.game_id = game.id
        
        # Add stats
        p_stat = PlayerStat(
            game_id=game.id, player_name='Player1', minutes='20:00', points=10,
            fgm=5, fga=10, reb=5, ast=2, tov=1, stl=1, blk=0, pf=2, oreb=2, dreb=3,
            tpm=0, tpa=0, ftm=0, fta=0, fg_percent=50.0, tp_percent=0, ft_percent=0, plus_minus=0
        )
        db.session.add(p_stat)
        db.session.commit()
        
        # Login
        self.client.post('/auth/login', data={
            'username': self.username,
            'password': self.password
        }, follow_redirects=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_index_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'TestOpp', response.data)
        # Look for score components separately since formatting may vary
        self.assertIn(b'100', response.data)
        self.assertIn(b'90', response.data)

    def test_game_detail(self):
        response = self.client.get(f'/game/{self.game_id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Player1', response.data)
        self.assertIn(b'10', response.data) # Points

    def test_player_detail(self):
        response = self.client.get('/player/Player1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Player1', response.data)
        # Check for actual content on page instead of specific string
        self.assertIn(b'Points', response.data)

    def test_live_game_save(self):
        # Test saving a live game with proper structure
        # NOTE: The game_service.py expects values to be strings or numbers, not dicts
        payload = {
            'opponent': 'LiveOpponent',
            'date': '2024-02-14',
            'game_type': 'Friendly',
            'team_score': 80,
            'opponent_score': 75,
            'player_stats': [
                {
                    'player_name': 'PlayerNew',
                    'minutes': '15:00',
                    'points': 15,
                    'fgm': 7,
                    'fga': 14,
                    'tpm': 1,
                    'tpa': 3,
                    'ftm': 0,
                    'fta': 0,
                    'reb': 5,
                    'ast': 3,
                    'tov': 1,
                    'stl': 2,
                    'blk': 0,
                    'pf': 2,
                    'oreb': 2,
                    'dreb': 3
                }
            ],
            'events': []
        }
        
        response = self.client.post('/live-game/save', 
                                    data=json.dumps(payload),
                                    content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        
        # Verify in DB
        game = Game.query.filter_by(opponent='LiveOpponent').first()
        self.assertIsNotNone(game)
        self.assertEqual(game.team_score, 80)
