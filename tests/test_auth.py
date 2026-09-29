import unittest
from web import create_app, db
from core.models import (
    AccountToken, User, Organization, Team,
    OrganizationMembership, TeamAssignment,
)
import os

class TestAuth(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create a default organization and team
        org = Organization(name="Test Org", slug="test-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(team)
        db.session.flush()
        
        # Create a test user
        self.username = 'auth_test_user'
        self.password = 'password'
        self.email = 'auth_test@example.com'
        user = User(username=self.username, email=self.email, organization_id=org.id)
        user.set_password(self.password)
        db.session.add(user)
        db.session.flush()
        membership = OrganizationMembership(user_id=user.id, organization_id=org.id, is_gm=False)
        db.session.add(membership)
        ta = TeamAssignment(user_id=user.id, team_id=team.id)
        db.session.add(ta)
        db.session.commit()
        
        # Set current team in session
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team.id

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

        # Test Logout. Default scope is this account only; the login above
        # left the account remembered on the device, so the message reflects
        # that other remembered accounts would survive.
        response = self.client.get('/auth/logout', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Other accounts on this device are still remembered',
                      response.data)

        # The protected dashboard must bounce to login again.
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_logout_scope_all_revokes_remembered_login(self):
        self.client.post('/auth/login', data={
            'username': self.username,
            'password': self.password
        }, follow_redirects=True)

        response = self.client.get('/auth/logout?scope=all', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'signed out of all accounts', response.data)

        # The remembered-login row must be revoked, not merely dropped
        # client-side, or a copied cookie would still work.
        live = AccountToken.query.filter_by(
            user_id=self._user_id(), revoked_at=None).count()
        self.assertEqual(live, 0)

    def _user_id(self):
        return User.query.filter_by(username=self.username).first().id

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
