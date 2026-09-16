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


class TestPlayTypeMove(unittest.TestCase):
    """PATCH /plays/<id>/type — library drag-and-drop re-filing."""

    def setUp(self):
        from core.models import PlayType, TeamAssignment

        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        org = Organization(name="Move Org", slug="move-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Move Team", organization_id=org.id, slug="move-team")
        db.session.add(team)
        db.session.flush()
        self.team = team
        db.session.add(PlayType(name="Offense", team_id=team.id))
        db.session.add(PlayType(name="Defense", team_id=team.id))
        user = User(username='move_user', email='move@example.com', organization_id=org.id)
        user.set_password('password')
        db.session.add(user)
        db.session.flush()
        db.session.add(OrganizationMembership(user_id=user.id, organization_id=org.id, is_gm=False))
        db.session.add(TeamAssignment(user_id=user.id, team_id=team.id))
        db.session.commit()
        self.user = user

        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team.id
        self.client.post('/auth/login', data={
            'username': 'move_user', 'password': 'password',
        }, follow_redirects=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _make_play(self, name='Horns', play_type='Offense'):
        play = Play(name=name, play_type=play_type, team_id=self.team.id)
        db.session.add(play)
        db.session.commit()
        return play

    def test_move_play_to_known_type(self):
        play = self._make_play()
        response = self.client.patch(f'/plays/{play.id}/type', json={'play_type': 'Defense'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['play_type'], 'Defense')
        db.session.refresh(play)
        self.assertEqual(play.play_type, 'Defense')

    def test_move_unknown_type_400(self):
        play = self._make_play()
        response = self.client.patch(f'/plays/{play.id}/type', json={'play_type': 'Nope'})
        self.assertEqual(response.status_code, 400)
        db.session.refresh(play)
        self.assertEqual(play.play_type, 'Offense')

    def test_move_cross_team_404(self):
        from core.models import Organization as Org, Team as T
        org2 = Org(name="Other Org", slug="other-org-mv")
        db.session.add(org2)
        db.session.flush()
        team2 = T(name="Other Team", organization_id=org2.id, slug="other-team-mv")
        db.session.add(team2)
        db.session.flush()
        other = Play(name='Foreign', play_type='Offense', team_id=team2.id)
        db.session.add(other)
        db.session.commit()
        response = self.client.patch(f'/plays/{other.id}/type', json={'play_type': 'Defense'})
        self.assertEqual(response.status_code, 404)

    def test_move_auditor_403(self):
        play = self._make_play()
        self.user.is_auditor = True
        db.session.commit()
        response = self.client.patch(f'/plays/{play.id}/type', json={'play_type': 'Defense'})
        self.assertEqual(response.status_code, 403)
        db.session.refresh(play)
        self.assertEqual(play.play_type, 'Offense')

    def test_move_requires_auth(self):
        # Flask-Login caches the user on flask.g for the pushed app context:
        # drop it so the anonymous client really resolves anonymous.
        from flask import g

        play = self._make_play()
        anon = self.app.test_client()
        g.pop('_login_user', None)
        response = anon.patch(f'/plays/{play.id}/type', json={'play_type': 'Defense'})
        self.assertIn(response.status_code, (302, 401))

    def test_builder_uses_shared_halfcourt(self):
        response = self.client.get('/plays/create')
        self.assertEqual(response.status_code, 200)
        # Court is canvas-drawn (court_backdrop.js): identical pixels in
        # every browser, no DOM/SVG/CSS background involved.
        self.assertIn(b'court_backdrop.js', response.data)
        self.assertNotIn(b'e8c89b', response.data)
