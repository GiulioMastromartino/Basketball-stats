import unittest
from web import create_app, db
from core.models import User, Play
from unittest.mock import patch

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
        self.user = User(username=self.username, email='plays@example.com', role='admin', is_admin=True)
        self.user.set_password('password')
        db.session.add(self.user)
        db.session.commit()
        
        # Login
        # Use patch to prevent actual email sending
        with patch('web.routes.auth.send_otp_email', return_value=True):
            login_resp = self.client.post('/auth/login', data={
                'username': self.username,
                'password': 'password'
            }, follow_redirects=True)
            
        # Check if we were redirected to OTP page (Admin users trigger OTP)
        if b'verify-otp' in login_resp.data or b'Verification code sent' in login_resp.data:
            # We are in OTP flow. Fetch the code from DB (it was set in auth.login route).
            db.session.refresh(self.user)
            otp_code = self.user.otp_code
            
            # Submit OTP
            otp_resp = self.client.post('/auth/verify-otp', data={
                'otp_code': otp_code
            }, follow_redirects=True)
            
            if b'Verification successful' not in otp_resp.data and b'Welcome back' not in otp_resp.data:
                 print("DEBUG: OTP Response Data:", otp_resp.data.decode('utf-8', errors='ignore')[:500])
                 raise RuntimeError("OTP verification failed")

        elif b'Welcome back' in login_resp.data:
            pass # No OTP required?
        else:
             print("DEBUG: Login Response Data:", login_resp.data.decode('utf-8', errors='ignore')[:500])
             # Check if we are still on login page with error
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
            'description': 'Test Description'
        }, follow_redirects=False)
        
        # If status is 302, it redirected. Check where.
        if response.status_code == 302:
            location = response.headers['Location']
            if '/auth/login' in location:
                self.fail(f"Redirected to login page - User not authenticated. Location: {location}")
            
            # Follow redirect manually to capture final page
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
        
        # 4. Delete Play
        response = self.client.post(f'/plays/{play.id}/delete', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        play = Play.query.get(play.id)
        self.assertIsNone(play)
