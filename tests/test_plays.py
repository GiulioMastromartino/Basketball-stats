import unittest
from web import create_app, db
from core.models import User, Organization, Team, OrganizationMembership, TeamAssignment, Play

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
        db.session.add(TeamAssignment(user_id=self.user.id, team_id=team.id))
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


class TestPlayActiveToggle(unittest.TestCase):
    """PATCH /plays/<id>/active + ?status=&type= filters + live selector."""

    def setUp(self):
        from core.models import TeamAssignment

        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        org = Organization(name="Toggle Org", slug="toggle-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Toggle Team", organization_id=org.id, slug="toggle-team")
        db.session.add(team)
        db.session.flush()
        self.team = team
        user = User(username='toggle_user', email='toggle@example.com', organization_id=org.id)
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
            'username': 'toggle_user', 'password': 'password',
        }, follow_redirects=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _make_play(self, name='Horns', play_type='Offense', is_active=True):
        play = Play(name=name, play_type=play_type, team_id=self.team.id, is_active=is_active)
        db.session.add(play)
        db.session.commit()
        return play

    def test_default_is_active(self):
        play = Play(name='Fresh', play_type='Offense', team_id=self.team.id)
        db.session.add(play)
        db.session.commit()
        self.assertTrue(play.is_active)

    def test_toggle_off_and_on(self):
        play = self._make_play()
        response = self.client.patch(f'/plays/{play.id}/active', json={'is_active': False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'id': play.id, 'is_active': False})
        db.session.refresh(play)
        self.assertFalse(play.is_active)
        response = self.client.patch(f'/plays/{play.id}/active', json={'is_active': True})
        self.assertEqual(response.status_code, 200)
        db.session.refresh(play)
        self.assertTrue(play.is_active)

    def test_toggle_rejects_non_boolean(self):
        play = self._make_play()
        for bad in ('false', 0, 1, None):
            response = self.client.patch(f'/plays/{play.id}/active', json={'is_active': bad})
            self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/plays/{play.id}/active', json={})
        self.assertEqual(response.status_code, 400)
        db.session.refresh(play)
        self.assertTrue(play.is_active)

    def test_toggle_cross_team_404(self):
        from core.models import Organization as Org, Team as T
        org2 = Org(name="Other Org", slug="other-org-tg")
        db.session.add(org2)
        db.session.flush()
        team2 = T(name="Other Team", organization_id=org2.id, slug="other-team-tg")
        db.session.add(team2)
        db.session.flush()
        other = Play(name='Foreign', play_type='Offense', team_id=team2.id)
        db.session.add(other)
        db.session.commit()
        response = self.client.patch(f'/plays/{other.id}/active', json={'is_active': False})
        self.assertEqual(response.status_code, 404)

    def test_toggle_auditor_403(self):
        play = self._make_play()
        self.user.is_auditor = True
        db.session.commit()
        response = self.client.patch(f'/plays/{play.id}/active', json={'is_active': False})
        self.assertEqual(response.status_code, 403)
        db.session.refresh(play)
        self.assertTrue(play.is_active)

    def test_toggle_requires_auth(self):
        from flask import g

        play = self._make_play()
        anon = self.app.test_client()
        g.pop('_login_user', None)
        response = anon.patch(f'/plays/{play.id}/active', json={'is_active': False})
        self.assertIn(response.status_code, (302, 401))

    def test_list_status_filter(self):
        self._make_play(name='On One')
        self._make_play(name='Off One', is_active=False)
        response = self.client.get('/plays/?status=active')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'On One', response.data)
        self.assertNotIn(b'Off One', response.data)
        response = self.client.get('/plays/?status=inactive')
        self.assertIn(b'Off One', response.data)
        self.assertNotIn(b'On One', response.data)
        response = self.client.get('/plays/?status=all')
        self.assertIn(b'On One', response.data)
        self.assertIn(b'Off One', response.data)

    def test_list_invalid_status_defaults_all(self):
        self._make_play(name='On Two')
        self._make_play(name='Off Two', is_active=False)
        response = self.client.get('/plays/?status=bogus')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'On Two', response.data)
        self.assertIn(b'Off Two', response.data)

    def test_list_type_and_status_intersection(self):
        self._make_play(name='Off A', play_type='Offense', is_active=True)
        self._make_play(name='Off B', play_type='Offense', is_active=False)
        self._make_play(name='Def A', play_type='Defense', is_active=True)
        response = self.client.get('/plays/?status=active&type=Offense')
        self.assertIn(b'Off A', response.data)
        self.assertNotIn(b'Off B', response.data)
        self.assertNotIn(b'Def A', response.data)

    def test_api_plays_excludes_inactive(self):
        self._make_play(name='Live One')
        self._make_play(name='Bench One', is_active=False)
        response = self.client.get('/api/plays')
        self.assertEqual(response.status_code, 200)
        names = [p['name'] for p in response.get_json()]
        self.assertIn('Live One', names)
        self.assertNotIn('Bench One', names)


class TestPlayFileTransfer(unittest.TestCase):
    """GET /plays/<id>/export + POST /plays/import — play file round-trip."""

    def setUp(self):
        import io as _io  # noqa: F401 (re-exported for test methods)

        self.app = create_app('testing')
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        org = Organization(name="File Org", slug="file-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="File Team", organization_id=org.id, slug="file-team")
        db.session.add(team)
        db.session.flush()
        self.team = team
        user = User(username='file_user', email='file@example.com', organization_id=org.id)
        user.set_password('password')
        db.session.add(user)
        db.session.flush()
        db.session.add(OrganizationMembership(user_id=user.id, organization_id=org.id, is_gm=False))
        db.session.add(TeamAssignment(user_id=user.id, team_id=team.id))
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team.id
        self.client.post('/auth/login', data={
            'username': 'file_user', 'password': 'password',
        }, follow_redirects=True)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _make_full_play(self, name='Horns Twist'):
        from core.models import PlaySequence

        play = Play(
            name=name, play_type='Offense', team_id=self.team.id,
            description='Elbow action', court_type='half', difficulty='Hard',
            personnel_required='5', tags='elbows',
            canvas_data={'objects': [{'type': 'circle'}]},
            diagram_svg='<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        )
        db.session.add(play)
        db.session.flush()
        db.session.add(PlaySequence(
            play_id=play.id, sequence_number=1,
            element_data={'step': 1}, caption='Entry',
            svg_snapshot='<svg>entry</svg>'))
        db.session.add(PlaySequence(
            play_id=play.id, sequence_number=2,
            element_data={'step': 2}, caption='Finish'))
        db.session.commit()
        return play

    def _upload(self, content, filename='Play_Horns_Twist.json', follow=True):
        import io

        payload = content if isinstance(content, bytes) else content.encode('utf-8')
        return self.client.post('/plays/import', data={
            'play_file': (io.BytesIO(payload), filename),
        }, content_type='multipart/form-data', follow_redirects=follow)

    def test_export_download(self):
        import json

        play = self._make_full_play()
        resp = self.client.get(f'/plays/{play.id}/export')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp.content_type)
        self.assertIn('.json', resp.headers.get('Content-Disposition', ''))
        body = json.loads(resp.data)
        self.assertEqual(body['kind'], 'play')
        self.assertEqual(body['play']['name'], 'Horns Twist')
        self.assertEqual(body['play']['canvas_data'], {'objects': [{'type': 'circle'}]})
        self.assertIn('<svg', body['play']['diagram_svg'])
        self.assertEqual(len(body['play']['frames']), 2)
        self.assertEqual(body['play']['frames'][0]['caption'], 'Entry')
        self.assertEqual(body['play']['frames'][0]['svg_snapshot'], '<svg>entry</svg>')

    def test_export_cross_team_404(self):
        from core.models import Organization as Org, Team as T

        org2 = Org(name="Other Org", slug="other-org-file")
        db.session.add(org2)
        db.session.flush()
        team2 = T(name="Other Team", organization_id=org2.id, slug="other-team-file")
        db.session.add(team2)
        db.session.flush()
        other = Play(name='Foreign', play_type='Offense', team_id=team2.id)
        db.session.add(other)
        db.session.commit()
        resp = self.client.get(f'/plays/{other.id}/export')
        self.assertEqual(resp.status_code, 404)

    def test_import_round_trip_with_rename(self):
        import json

        play = self._make_full_play()
        exported = self.client.get(f'/plays/{play.id}/export').data

        # name clash -> auto-renamed copy with identical content
        resp = self._upload(exported)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Horns Twist (imported)', resp.data)
        copy = Play.query.filter_by(name='Horns Twist (imported)').first()
        self.assertIsNotNone(copy)
        self.assertEqual(copy.team_id, self.team.id)
        self.assertEqual(copy.canvas_data, {'objects': [{'type': 'circle'}]})
        self.assertIn('<svg', copy.diagram_svg)
        self.assertEqual(copy.play_type, 'Offense')
        self.assertEqual(copy.court_type, 'half')
        self.assertEqual(
            [f.caption for f in sorted(copy.sequences, key=lambda f: f.sequence_number)],
            ['Entry', 'Finish'])
        self.assertEqual(
            sorted(copy.sequences, key=lambda f: f.sequence_number)[0].svg_snapshot,
            '<svg>entry</svg>')

        # no clash -> original name kept
        db.session.delete(play)
        db.session.delete(copy)
        db.session.commit()
        resp = self._upload(exported)
        self.assertIn(b'Horns Twist', resp.data)
        self.assertIsNotNone(Play.query.filter_by(name='Horns Twist').first())

    def test_import_rejects_bad_files(self):
        # not JSON
        resp = self._upload(b'not json at all')
        self.assertIn(b'not valid JSON', resp.data)
        # missing name
        resp = self._upload('{"play": {"play_type": "Offense"}}')
        self.assertIn(b'must contain a name', resp.data)
        # wrong extension
        resp = self._upload(b'{}', filename='play.txt')
        self.assertIn(b'must be a .json export', resp.data)
        # no file
        resp = self.client.post('/plays/import', data={},
                                content_type='multipart/form-data',
                                follow_redirects=True)
        self.assertIn(b'Select a play file', resp.data)
        self.assertEqual(Play.query.count(), 0)

    def test_import_lands_in_current_team(self):
        import json
        from core.models import Organization as Org, Team as T
        from core.models import TeamAssignment as TA

        play = self._make_full_play()
        exported = self.client.get(f'/plays/{play.id}/export').data
        org2 = Org(name="Other Org", slug="other-org-file2")
        db.session.add(org2)
        db.session.flush()
        team2 = T(name="Other Team", organization_id=org2.id, slug="other-team-file2")
        db.session.add(team2)
        db.session.flush()
        user = User.query.filter_by(username='file_user').first()
        db.session.add(TA(user_id=user.id, team_id=team2.id))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team2.id
        self._upload(exported)
        imported = Play.query.filter_by(name='Horns Twist (imported)').first()
        self.assertIsNotNone(imported)
        self.assertEqual(imported.team_id, team2.id)

    def test_save_canvas_stores_phase_snapshots(self):
        import json as _json
        from core.models import PlaySequence

        payload = {
            'play_id': None,
            'metadata': {'name': 'Snap Play', 'play_type': 'Offense', 'court_type': 'half'},
            'canvas_json': {'objects': []},
            'diagram_svg': '<svg></svg>',
            'frames': [
                {'data': {'objects': []}, 'caption': 'Start', 'svg': '<svg>phase1</svg>'},
                {'data': {'objects': []}, 'caption': 'Step 2'},
            ],
        }
        resp = self.client.post('/api/v1/plays/api/save-canvas',
                                data=_json.dumps(payload),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200, resp.data[:300])
        seqs = PlaySequence.query.order_by(PlaySequence.sequence_number).all()
        self.assertEqual(len(seqs), 2)
        self.assertEqual(seqs[0].svg_snapshot, '<svg>phase1</svg>')
        self.assertIsNone(seqs[1].svg_snapshot)

    def test_load_canvas_reports_snapshot_presence(self):
        import json as _json

        play = self._make_full_play()
        resp = self.client.get(f'/api/v1/plays/api/load-canvas/{play.id}')
        self.assertEqual(resp.status_code, 200)
        body = _json.loads(resp.data)
        self.assertIn('<svg', body['diagram_svg'])
        flags = [f['has_svg'] for f in body['frames']]
        self.assertEqual(flags, [True, False])

    def test_backfill_frame_snapshots(self):
        from core.models import PlaySequence

        play = self._make_full_play()
        seqs = PlaySequence.query.order_by(PlaySequence.sequence_number).all()
        target = [s for s in seqs if s.svg_snapshot is None][0]
        resp = self.client.post(
            f'/api/v1/plays/api/{play.id}/frame-snapshots',
            json={'snapshots': [
                {'id': target.id, 'svg': '<svg>backfilled</svg>'},
                {'id': 999999, 'svg': '<svg>ghost</svg>'},
                {'id': target.id, 'svg': None},
            ]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['saved'], 1)
        db.session.refresh(target)
        self.assertEqual(target.svg_snapshot, '<svg>backfilled</svg>')

    def test_backfill_frame_snapshots_rejects_bad_payloads(self):
        play = self._make_full_play()
        resp = self.client.post(
            f'/api/v1/plays/api/{play.id}/frame-snapshots', json={})
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(
            f'/api/v1/plays/api/999999/frame-snapshots',
            json={'snapshots': [{'id': 1, 'svg': '<svg/>'}]})
        self.assertEqual(resp.status_code, 404)

    def test_backfill_cross_team_404(self):
        from core.models import Organization as Org, Team as T

        org2 = Org(name="Other Org", slug="other-org-snap")
        db.session.add(org2)
        db.session.flush()
        team2 = T(name="Other Team", organization_id=org2.id, slug="other-team-snap")
        db.session.add(team2)
        db.session.flush()
        other = Play(name='Foreign Snap', play_type='Offense', team_id=team2.id)
        db.session.add(other)
        db.session.commit()
        resp = self.client.post(
            f'/api/v1/plays/api/{other.id}/frame-snapshots',
            json={'snapshots': [{'id': 1, 'svg': '<svg/>'}]})
        self.assertEqual(resp.status_code, 404)
