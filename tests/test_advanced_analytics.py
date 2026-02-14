import unittest
import json
import os
from datetime import datetime
from web import create_app, db
from core.models import User, Game, PlayerStat, ShotEvent, GameEvent, Play, PlayType, LineupSegment, PlayerLineupStats, Possession

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
        
        # 2. Game Setup
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
        
        # 3. Create a Play
        play = Play(name="PickAndRoll", play_type="Offense", description="High PNR")
        db.session.add(play)
        db.session.commit()
        self.play_id = play.id

        # 4. Player Stats (Box Score)
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
        
        # 5. Shot Events (Shot Chart, Heatmap, Hexbin)
        # Add varied shots
        shots = [
            ShotEvent(game_id=game.id, player_name=self.player_name, shot_type='3PT', result='made', points=3, x_loc=25.0, y_loc=45.0, quarter=4, play_id=play.id), # Corner 3
            ShotEvent(game_id=game.id, player_name=self.player_name, shot_type='2PT', result='missed', points=0, x_loc=250.0, y_loc=50.0, quarter=4, play_id=play.id), # Rim
            ShotEvent(game_id=game.id, player_name=self.player_name, shot_type='2PT', result='made', points=2, x_loc=250.0, y_loc=200.0, quarter=3, play_id=play.id), # Midrange
            ShotEvent(game_id=game.id, player_name=self.player_name, shot_type='3PT', result='missed', points=0, x_loc=250.0, y_loc=400.0, quarter=2, play_id=play.id) # Top of key
        ]
        db.session.add_all(shots)
        
        # 6. Clutch Events
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
        
        # 7. Rotation Analysis Events
        rotation_events = [
            GameEvent(game_id=game.id, event_type='SUB_IN', player_name=self.player_name, timestamp=0, quarter=1),
            GameEvent(game_id=game.id, event_type='SUB_OUT', player_name=self.player_name, timestamp=500, quarter=1),
            GameEvent(game_id=game.id, event_type='SUB_IN', player_name='P2', timestamp=0, quarter=1), # P2 plays whole time
        ]
        db.session.add_all(rotation_events)

        # 8. Possession Reconstruction Events
        # Sequence: Rebound (Start) -> Shot (End)
        possession_events = [
            GameEvent(game_id=game.id, event_type='REBOUND_DEFENSIVE', player_name=self.player_name, timestamp=100, quarter=2),
            GameEvent(game_id=game.id, event_type='SHOT_2PT', player_name=self.player_name, shot_attempt='made', timestamp=120, quarter=2)
        ]
        db.session.add_all(possession_events)

        # 9. Lineup Segments (Duo/Trio/Lineup Analytics)
        # Segment 1: High performing trio
        # NOTE: Passing Python lists, not JSON strings, assuming SQLAlchemy/Model handles serialization or tests use Python objects
        # Update: Checked model, it's db.JSON. Passing Python list is correct for SQLAlchemy.
        
        segment_on = LineupSegment(
            game_id=game.id,
            start_timestamp=0, end_timestamp=500, quarter=1,
            players=[self.player_name, 'P2', 'P3', 'P4', 'P5'],
            lineup_hash='hash1',
            points_scored=20, points_allowed=10, possessions=15
        )
        
        # Segment 2: Poor performing duo
        segment_off = LineupSegment(
            game_id=game.id,
            start_timestamp=501, end_timestamp=1000, quarter=1,
            players=['P6', 'P7', 'P2', 'P8', 'P9'],
            lineup_hash='hash2',
            points_scored=5, points_allowed=15, possessions=15
        )
        db.session.add_all([segment_on, segment_off])
        
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

    # --- Existing Tests ---

    def test_get_player_advanced_stats(self):
        response = self.client.get(f'/api/advanced/player/{self.player_name}/advanced')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['player_name'], self.player_name)
        self.assertIn('shot_quality', data)
        self.assertEqual(data['shot_quality']['total_shots'], 4) # We added 4 shots

    def test_get_player_usage(self):
        response = self.client.get(f'/api/advanced/player/{self.player_name}/usage')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('usage_rate', data)
        self.assertGreater(data['usage_rate'], 0)

    def test_get_season_clutch_stats(self):
        response = self.client.get('/api/advanced/clutch/season?game_type=Season')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        found = False
        for p in data['players']:
            if p['player'] == self.player_name:
                found = True
                self.assertEqual(p['clutch_points'], 3)
        self.assertTrue(found)

    def test_get_four_factors(self):
        response = self.client.get(f'/api/advanced/four-factors?game_id={self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('four_factors', data)

    def test_get_shot_chart(self):
        response = self.client.get(f'/api/advanced/shots/chart?game_id={self.game_id}&player={self.player_name}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['total_shots'], 4)

    def test_get_on_off_splits(self):
        response = self.client.get(f'/api/advanced/lineup/on-off/{self.player_name}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        # Player is in segment 1 (Net +10) and not in segment 2
        self.assertIn('net_differential', data)
        # On court: +10 pts in 15 poss => ORTG ~133, DRTG ~66 => Net +67
        # Off court: -10 pts in 15 poss => ORTG ~33, DRTG ~100 => Net -67
        # Differential should be huge positive
        self.assertGreater(data['net_differential'], 0)

    def test_get_lineup_rankings(self):
        response = self.client.get('/api/advanced/lineup/rankings?min_possessions=0')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(len(data['rankings']) >= 1)
        # Our main lineup is 'TestPlayer', 'P2', 'P3', 'P4', 'P5'
        # With SQLAlchemy DB.JSON, it should work fine if input was list.
        # If SQLite support is shaky, it might be an issue, but let's assume it works with the fix.
        top_lineup = data['rankings'][0]
        self.assertEqual(top_lineup['points_scored'], 20)

    # --- New Tests ---

    def test_get_heatmap_data(self):
        """Test shot heatmap generation"""
        response = self.client.get(f'/api/advanced/shots/heatmap?player={self.player_name}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('heatmap', data)
        heatmap = data['heatmap']
        # We have a corner 3, so 'Corner_3' should be in heatmap
        self.assertIn('Corner_3', heatmap)
        self.assertEqual(heatmap['Corner_3']['makes'], 1)

    def test_get_hexbin_data(self):
        """Test hexbin aggregation"""
        response = self.client.get(f'/api/advanced/shots/hexbin?player={self.player_name}&hex_size=50')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('hexbins', data)
        self.assertTrue(len(data['hexbins']) > 0)
        # Check structure
        self.assertIn('x', data['hexbins'][0])
        self.assertIn('fg_pct', data['hexbins'][0])

    def test_get_duo_compatibility(self):
        """Test duo compatibility matrix"""
        response = self.client.get('/api/advanced/lineup/duos')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('duos', data)
        # We had TestPlayer and P2 together in segment 1
        found = False
        for duo in data['duos']:
            players = {duo['player1'], duo['player2']}
            if self.player_name in players and 'P2' in players:
                found = True
                self.assertGreater(duo['net_rating'], 0) # They did well together
                break
        self.assertTrue(found, "Duo TestPlayer-P2 not found")

    def test_get_trio_compatibility(self):
        """Test trio compatibility matrix"""
        response = self.client.get('/api/advanced/lineup/trios')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('trios', data)
        # TestPlayer, P2, P3 were together
        found = False
        for trio in data['trios']:
            players = set(trio['players'])
            if {self.player_name, 'P2', 'P3'}.issubset(players):
                found = True
                break
        self.assertTrue(found, "Trio TestPlayer-P2-P3 not found")

    def test_get_rotation_analysis(self):
        """Test rotation/stint analysis"""
        response = self.client.get(f'/api/advanced/rotation/{self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('player_stints', data)
        # TestPlayer had one stint (0 to 500)
        stints = data['player_stints'][self.player_name]
        self.assertEqual(len(stints), 1)
        self.assertEqual(stints[0]['start_timestamp'], 0)
        self.assertEqual(stints[0]['end_timestamp'], 500)

    def test_possession_reconstruction(self):
        """Test full possession reconstruction flow"""
        # 1. Trigger reconstruction
        response = self.client.post(f'/api/advanced/possessions/reconstruct/{self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertGreater(data['possessions_created'], 0)
        
        # 2. Fetch possessions
        response = self.client.get(f'/api/advanced/possessions/{self.game_id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        possessions = data['possessions']
        self.assertTrue(len(possessions) > 0)
        # Our manual events created a possession with 2 points (Shot Made)
        # Check for at least one possession with points > 0
        scoring_poss = [p for p in possessions if p['points'] > 0]
        self.assertTrue(len(scoring_poss) > 0)

    def test_get_play_rankings(self):
        """Test play effectiveness rankings"""
        response = self.client.get('/api/advanced/plays/rankings')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('rankings', data)
        # Check for our 'PickAndRoll' play
        found = False
        for p in data['rankings']:
            if p['play_name'] == "PickAndRoll":
                found = True
                # We added shots linked to this play (some made, some missed)
                self.assertGreater(p['total_shots'], 0)
        self.assertTrue(found, "Play 'PickAndRoll' not found in rankings")

    def test_zone_classification(self):
        """Test shot zone classifier endpoint"""
        # Test Corner 3 logic
        payload = {'x_loc': 25.0, 'y_loc': 45.0, 'shot_type': '3PT'}
        response = self.client.post('/api/advanced/zones/classify', 
                                  data=json.dumps(payload),
                                  content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['zone'], 'Corner_3')

if __name__ == '__main__':
    unittest.main()
