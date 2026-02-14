import unittest
import json
import os
from datetime import datetime
from web import create_app, db
from core.models import User, Game, PlayerStat, ShotEvent, GameEvent, Play, PlayType

class TestAdvancedAnalytics(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Get credentials from env
        self.username = os.environ.get('TESTER_USERNAME', 'Giulio')
        self.password = os.environ.get('TESTER_PASSWORD', 'adminadmin')
        self.email = 'tester@example.com'

        # Create test user
        user = User(username=self.username, email=self.email, is_admin=True)
        user.set_password(self.password)
        db.session.add(user)
        
        # Create dummy data
        game = Game(
            date='01-01-2024',
            opponent='TestOpponent',
            team_score=100,
            opponent_score=90,
            result='W',
            game_type='Season',
            sort_date='2024-01-01',
            source='MANUAL'
        )
        db.session.add(game)
        db.session.commit()
        
        self.game_id = game.id
        self.player_name = 'TestPlayer'
        
        # Add player stats
        p_stat = PlayerStat(
            game_id=game.id,
            player_name=self.player_name,
            minutes='30:00',
            points=20,
            fga=15, fgm=8, fg_percent=53.3,
            tpa=5, tpm=2, tp_percent=40.0,
            fta=4, ftm=2, ft_percent=50.0,
            reb=5, ast=5, tov=2, stl=1, blk=0, pf=2
        )
        db.session.add(p_stat)
        
        # Add shot events
        shot = ShotEvent(
            game_id=game.id,
            player_name=self.player_name,
            shot_type='3PT',
            result='made',
            points=3,
            x_loc=25.0,
            y_loc=45.0, # Corner 3 roughly
            quarter=4
        )
        db.session.add(shot)
        
        db.session.commit()

        # Login
        login_response = self.client.post('/auth/login', data={
            'username': self.username,
            'password': self.password
        }, follow_redirects=True)
        
        # Verify login success
        if b'Invalid username' in login_response.data:
            self.fail("Login failed: Invalid credentials")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_get_player_advanced_stats(self):
        response = self.client.get(f'/api/advanced/player/{self.player_name}/advanced')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('season_stats', data)
        self.assertIn('shot_quality', data)

    def test_get_player_usage(self):
        response = self.client.get(f'/api/advanced/player/{self.player_name}/usage')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('usage_rate', data)

    def test_get_season_clutch_stats(self):
        response = self.client.get('/api/advanced/clutch/season?game_type=Season')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('players', data)

    def test_get_four_factors(self):
        response = self.client.get(f'/api/advanced/four-factors?game_id={self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('four_factors', data)
        self.assertIn('efg_pct', data['four_factors'])

    def test_get_shot_chart(self):
        response = self.client.get(f'/api/advanced/shots/chart?game_id={self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('shots', data)
        self.assertTrue(len(data['shots']) > 0)

if __name__ == '__main__':
    unittest.main()
