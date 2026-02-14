import unittest
from web import create_app, db
from core.models import User, Play

class TestPlays(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create test user (admin for delete access)
        self.username = 'plays_test_user'
        user = User(username=self.username, email='plays@example.com', role='admin', is_admin=True)
        user.set_password('password')
        db.session.add(user)
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

    def test_play_lifecycle(self):
        # 1. Create Play
        response = self.client.post('/plays/add', data={
            'name': 'New Play',
            'play_type': 'Offense',
            'description': 'Test Description'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Check flash message or content redirection
        # The response.data might be the view page content
        self.assertIn(b'Play', response.data) # Generic check
        
        play = Play.query.filter_by(name='New Play').first()
        self.assertIsNotNone(play)
        
        # 2. View Play
        response = self.client.get(f'/plays/{play.id}') # URL is /plays/<int:play_id>, view_play function
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'New Play', response.data)
        
        # 3. Edit Play
        response = self.client.post(f'/plays/edit/{play.id}', data={
            'name': 'Updated Play',
            'play_type': 'Defense',
            'description': 'Updated Desc'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        play = Play.query.get(play.id)
        self.assertEqual(play.name, 'Updated Play')
        self.assertEqual(play.play_type, 'Defense')
        
        # 4. Delete Play
        response = self.client.post(f'/plays/{play.id}/delete', follow_redirects=True) # URL is /plays/<int:play_id>/delete
        self.assertEqual(response.status_code, 200)
        
        play = Play.query.get(play.id)
        self.assertIsNone(play)
