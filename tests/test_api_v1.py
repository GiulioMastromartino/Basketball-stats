import unittest
import json
from web import create_app, db
from core.models import User, Play

class TestApiV1(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create test user
        self.username = 'api_test_user'
        user = User(username=self.username, email='api@example.com', role='editor', is_admin=False)
        user.set_password('password')
        db.session.add(user)
        
        # Create plays
        play1 = Play(name='PickAndRoll', play_type='Offense', description='Basic PnR')
        play2 = Play(name='ZoneDefense', play_type='Defense', description='2-3 Zone')
        db.session.add_all([play1, play2])
        db.session.commit()
        
        # Login
        self.client.post('/auth/login', data={
            'username': self.username,
            'password': 'password'
        }, follow_redirects=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_get_plays_all(self):
        response = self.client.get('/api/v1/api/plays?type=All')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        
    def test_get_plays_filtered(self):
        response = self.client.get('/api/v1/api/plays?type=Offense')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'PickAndRoll')

    def test_get_play_types(self):
        response = self.client.get('/api/v1/api/plays/types')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('Offense', data)
        self.assertIn('Defense', data)
