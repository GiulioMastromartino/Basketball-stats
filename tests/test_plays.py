import unittest
from web import create_app, db
from core.models import User, Organization, Team, OrganizationMembership, Play

class TestPlays(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create default org and team
        org = Organization(name="Test Org", slug="test-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(team)
        db.session.flush()
        self.team_id = team.id
        
        # Create test user (Editor - no OTP required)
        self.username = 'plays_test_user'
        self.user = User(username=self.username, email='plays@example.com', organization_id=org.id)
        self.user.set_password('password')
        db.session.add(self.user)
        db.session.flush()
        membership = OrganizationMembership(user_id=self.user.id, organization_id=org.id, is_gm=False)
        db.session.add(membership)
        db.session.commit()
        
        # Set current team before login
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team.id
        
        # Login
        login_resp = self.client.post('/auth/login', data={
            'username': self.username,
            'password': 'password'
        }, follow_redirects=True)
            
        # Verify login success
        if b'Welcome back' not in login_resp.data and b'Dashboard' not in login_resp.data:
             print("DEBUG: Login Response Data:", login_resp.data.decode('utf-8', errors='ignore')[:500])
             if b'Invalid username' in login_resp.data:
                 raise RuntimeError("Login failed: Invalid credentials")
             raise RuntimeError(f"Login failed or unexpected state. Status: {login_resp.status_code}")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_play_lifecycle(self):
        # 1. Create Play - Check redirect target explicitly
        response = self.client.post('/plays/add', data={
            'name': 'New Play',
            'play_type': 'Offense',
            'description': 'Test Description',
            'team_id': self.team_id,
        }, follow_redirects=False)
        
        # Handle redirects manually for debugging
        if response.status_code == 302:
            location = response.headers['Location']
            if '/auth/login' in location:
                self.fail(f"Redirected to login page - User not authenticated. Location: {location}")
            
            # Follow redirect manually
            response = self.client.get(location)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify persistence first
        play = Play.query.filter_by(name='New Play').first()
        self.assertIsNotNone(play)
        
        # 2. View Play
        response = self.client.get(f'/plays/{play.id}') 
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'New Play', response.data)
        
        # 3. Edit Play
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
        
        # 4. Try Delete Play (Should FAIL for Editor)
        response = self.client.post(f'/plays/{play.id}/delete', follow_redirects=True)
        
        # Editors should be redirected to dashboard with error, NOT allowed to delete
        # Check if play still exists
        play = Play.query.get(play.id)
        self.assertIsNotNone(play, "Editor should not be able to delete plays")
        
        # Check for permission denied message (flash)
        # Based on decorators.py: "You do not have permission to perform this action."
        self.assertIn(b'permission', response.data)
