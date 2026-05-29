import unittest
import json
from web import create_app, db
from core.models import User, Organization, Team, OrganizationMembership, Play

class TestApiV1(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
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
        
        # Create test user
        self.username = 'api_test_user'
        user = User(username=self.username, email='api@example.com', organization_id=org.id)
        user.set_password('password')
        db.session.add(user)
        db.session.flush()
        membership = OrganizationMembership(user_id=user.id, organization_id=org.id, is_gm=False)
        db.session.add(membership)
        
        # Create plays
        play1 = Play(name='PickAndRoll', play_type='Offense', description='Basic PnR', team_id=self.team_id)
        play2 = Play(name='ZoneDefense', play_type='Defense', description='2-3 Zone', team_id=self.team_id)
        db.session.add_all([play1, play2])
        db.session.commit()
        
        # Set current team in session
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team.id
        
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
        # The route in api.py is defined as: @api_bp.route('/plays', ...)
        # And in __init__.py it is registered as: app.register_blueprint(api_bp, url_prefix="/api/v1")
        # So the correct URL is /api/v1/plays (not /api/v1/api/plays)
        response = self.client.get('/api/v1/plays?type=All')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        
    def test_get_plays_filtered(self):
        response = self.client.get('/api/v1/plays?type=Offense')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'PickAndRoll')

    def test_get_play_types(self):
        response = self.client.get('/api/v1/plays/types')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn('Offense', data)
        self.assertIn('Defense', data)
