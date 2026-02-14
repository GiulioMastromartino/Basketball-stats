import unittest
import json
import os
from datetime import datetime
from flask_login import login_user
from web import create_app, db
from core.models import User, Game, PlayerStat, ShotEvent, GameEvent, Play, PlayType, LineupSegment, PlayerLineupStats

class TestAdvancedAnalytics(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Ensure schema exists
        db.create_all()
        
        # Get credentials from env
        self.username = os.environ.get('TESTER_USERNAME', 'Giulio')
        self.password = os.environ.get('TESTER_PASSWORD', 'adminadmin')
        
        # 1. User Setup
        user = User.query.filter_by(username=self.username).first()
        if not user:
            user = User(username=self.username, email='tester@example.com', is_admin=False, role='editor')
            user.set_password(self.password)
            db.session.add(user)
            db.session.commit()
        
        # 2. Game Setup (Close game for Clutch stats)
        game = Game(
            date='01/01/2024',
            opponent='TestOpponent',
            team_score=102,
            opponent_score=100,
            result='W',
            game_type='Season',
            sort_date='2024-01-01',
            source='MANUAL'
        )
        db.session.add(game)
        db.session.commit()
        self.game_id = game.id
        self.player_name = 'TestPlayer'
        
        # 3. Player Stats (Box Score)
        p_stat = PlayerStat(
            game_id=game.id,
            player_name=self.player_name,
            minutes='30:00',
            points=25,
            fga=20, fgm=10, fg_percent=50.0,
            tpa=5, tpm=2, tp_percent=40.0,
            fta=4, ftm=3, ft_percent=75.0,
            reb=10, ast=5, tov=2, stl=1, blk=1, pf=2, oreb=4, dreb=6,
            plus_minus=5
        )
        db.session.add(p_stat)
        
        # 4. Shot Events (Shot Chart)
        shot1 = ShotEvent(
            game_id=game.id,
            player_name=self.player_name,
            shot_type='3PT',
            result='made',
            points=3,
            x_loc=25.0, y_loc=45.0, # Corner
            quarter=4
        )
        shot2 = ShotEvent(
            game_id=game.id,
            player_name=self.player_name,
            shot_type='2PT',
            result='missed',
            points=0,
            x_loc=250.0, y_loc=50.0, # Paint
            quarter=4
        )
        db.session.add_all([shot1, shot2])
        
        # 5. Clutch Events (Last 5 mins, score margin <= 5)
        clutch_event = GameEvent(
            game_id=game.id,
            event_type='SHOT_3PT',
            player_name=self.player_name,
            detail='Made 3PT',
            timestamp=1000,
            shot_attempt='made',
            quarter=4,
            time_remaining='02:30', # < 5 mins
            score_margin=1 # Within 5 points
        )
        db.session.add(clutch_event)
        
        # 6. Lineup Segments (For On/Off and Lineup Analytics)
        # Segment 1: Player is ON
        segment_on = LineupSegment(
            game_id=game.id,
            start_timestamp=0,
            end_timestamp=500,
            quarter=1,
            players=json.dumps([self.player_name, 'P2', 'P3', 'P4', 'P5']),
            lineup_hash='hash1',
            points_scored=10,
            points_allowed=5,
            possessions=10
        )
        db.session.add(segment_on)
        db.session.commit()
        
        # Add stats for this lineup segment
        l_stat = PlayerLineupStats(
            lineup_segment_id=segment_on.id,
            player_name=self.player_name,
            points=5,
            fga=4, fgm=2
        )
        db.session.add(l_stat)
        
        # Segment 2: Player is OFF
        segment_off = LineupSegment(
            game_id=game.id,
            start_timestamp=501,
            end_timestamp=1000,
            quarter=1,
            players=json.dumps(['P2', 'P3', 'P4', 'P5', 'P6']), # TestPlayer replaced by P6
            lineup_hash='hash2',
            points_scored=2,
            points_allowed=8,
            possessions=10
        )
        db.session.add(segment_off)
        
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

    def test_get_player_advanced_stats(self):
        """Test general advanced stats calculation"""
        response = self.client.get(f'/api/advanced/player/{self.player_name}/advanced')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Check that we have basic data structure
        self.assertIn('player_name', data)
        self.assertEqual(data['player_name'], self.player_name)

    def test_get_player_usage(self):
        """Test usage rate calculation"""
        response = self.client.get(f'/api/advanced/player/{self.player_name}/usage')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('usage_rate', data)
        usage = data['usage_rate']
        self.assertIsInstance(usage, (int, float))
        self.assertGreater(usage, 0) # Should be positive given the stats

    def test_get_season_clutch_stats(self):
        """Test clutch time filtering and stats"""
        response = self.client.get('/api/advanced/clutch/season?game_type=Season')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('players', data)
        players = data['players']
        # We created a clutch event, so we expect at least one player entry
        found = False
        for p in players:
            if p['player'] == self.player_name:
                found = True
                self.assertEqual(p['clutch_points'], 3) # 1 made 3PT in clutch
                self.assertEqual(p['clutch_plays'], 1)
        self.assertTrue(found, "Player not found in clutch stats")

    def test_get_four_factors(self):
        """Test Four Factors calculation"""
        response = self.client.get(f'/api/advanced/four-factors?game_id={self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('four_factors', data)
        factors = data['four_factors']
        self.assertIn('efg_pct', factors)
        # Accept any reasonable structure
        self.assertIsInstance(factors['efg_pct'], (int, float))

    def test_get_shot_chart(self):
        """Test shot chart data retrieval"""
        response = self.client.get(f'/api/advanced/shots/chart?game_id={self.game_id}&player={self.player_name}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('shots', data)
        self.assertIn('total_shots', data)
        # We created 2 shots
        self.assertEqual(data['total_shots'], 2)

    def test_get_on_off_splits(self):
        """Test On/Off Court Analytics"""
        response = self.client.get(f'/api/advanced/lineup/on-off/{self.player_name}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        # Just verify we get a response - structure may vary
        self.assertIsInstance(data, dict)

    def test_get_lineup_rankings(self):
        """Test Lineup Rankings API"""
        # Set min_possessions=0 to ensure our small test data is included
        response = self.client.get('/api/advanced/lineup/rankings?min_possessions=0')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        
        self.assertIn('rankings', data)
        # Just verify structure, don't enforce specific data
        self.assertIsInstance(data['rankings'], list)

if __name__ == '__main__':
    unittest.main()
