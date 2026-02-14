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
        
        # Verify persistence first
        play = Play.query.filter_by(name='New Play').first()
        self.assertIsNotNone(play)
        
        # 2. View Play
        response = self.client.get(f'/plays/{play.id}') # URL is /plays/<int:play_id>
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'New Play', response.data)
        
        # 3. Edit Play
        # Note: edit route might be /plays/edit/<id> or similar, check plays.py
        # Based on previous file content: @plays_bp.route("/plays/edit/<int:play_id>", methods=["POST"])
        response = self.client.post(f'/plays/edit/{play.id}', data={
            'name': 'Updated Play',
            'play_type': 'Defense',
            'description': 'Updated Desc'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify Update
        db.session.refresh(play) # Refresh from DB
        self.assertEqual(play.name, 'Updated Play')
        self.assertEqual(play.play_type, 'Defense')
        
        # 4. Delete Play
        # Route: @plays_bp.route("/plays/<int:play_id>/delete", methods=["POST"])
        response = self.client.post(f'/plays/{play.id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        play = Play.query.get(play.id)
        self.assertIsNone(play)
