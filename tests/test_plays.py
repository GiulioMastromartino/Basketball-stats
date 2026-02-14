import unittest
from web import create_app, db
from core.models import User, Play

class TestPlays(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
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
        login_resp = self.client.post('/auth/login', data={
            'username': self.username,
            'password': 'password'
        }, follow_redirects=True)
        
        # Check login success using known dashboard content
        # test_auth uses b'Welcome back', let's stick to that or generic check
        if login_resp.status_code != 200:
             raise RuntimeError(f"Login failed with status {login_resp.status_code}")
             
        # If we are redirected to login, the title would likely be "Sign In" or similar
        if b'Sign In' in login_resp.data and b'Dashboard' not in login_resp.data:
             raise RuntimeError("Login failed: Still on login page")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_play_lifecycle(self):
        # 1. Create Play - Check redirect target explicitly
        response = self.client.post('/plays/add', data={
            'name': 'New Play',
            'play_type': 'Offense',
            'description': 'Test Description'
        }, follow_redirects=False)
        
        # If status is 302, it redirected. Check where.
        if response.status_code == 302:
            location = response.headers['Location']
            if '/auth/login' in location:
                self.fail(f"Redirected to login page - User not authenticated. Location: {location}")
            if '/plays' in location and 'view' not in location:
                 # It might be redirecting to list_plays (/plays/)
                 # We need to know WHY. The flash message would tell us.
                 # Follow to get flash
                 followed = self.client.get(location)
                 print("DEBUG: Redirected to list. Page content:", followed.data.decode('utf-8', errors='ignore')[:1000])
                 self.fail(f"Redirected to plays list - Validation failed. Location: {location}")
            
            # Follow redirect manually to capture final page
            response = self.client.get(location)
        else:
            print(f"DEBUG: Status Code {response.status_code}")
            print("DEBUG: Response Data:", response.data.decode('utf-8', errors='ignore')[:500])
        
        self.assertEqual(response.status_code, 200)
        
        # Verify persistence first
        play = Play.query.filter_by(name='New Play').first()
        if play is None:
            # Check if any plays exist
            all_plays = Play.query.all()
            print(f"DEBUG: All Plays in DB: {[p.name for p in all_plays]}")
            self.fail("Play was not created in DB")

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
        
        # 4. Delete Play
        response = self.client.post(f'/plays/{play.id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        play = Play.query.get(play.id)
        self.assertIsNone(play)
