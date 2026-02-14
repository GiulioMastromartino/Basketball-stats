import unittest
from web import create_app, db
from core.models import User
import os

class TestAuth(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create a test user
        self.username = 'auth_test_user'
        self.password = 'password'
        self.email = 'auth_test@example.com'
        user = User(username=self.username, email=self.email, role='editor', is_admin=False)
        user.set_password(self.password)
        db.session.add(user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_login_logout(self):
        # Test Login
        response = self.client.post('/auth/login', data={
            'username': self.username,
            'password': self.password
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome back', response.data)
        
        # Test Logout
        response = self.client.get('/auth/logout', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'You have been logged out', response.data)

    def test_login_invalid_credentials(self):
        response = self.client.post('/auth/login', data={
            'username': self.username,
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid username or password', response.data)

    def test_protected_route_access(self):
        # Try to access a protected route without login
        response = self.client.get('/', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        # Should redirect to login page
        self.assertIn(b'Please log in', response.data)
