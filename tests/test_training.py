import json
import unittest
from web import create_app, db
from core.models import (
    User, Organization, Team, OrganizationMembership, TeamAssignment, Play,
    Player, TrainingSession, TrainingSegment, TrainingAttendance,
    TrainingSegmentTemplate,
)


def make_ctx(testcase, username="training_test_user"):
    app = create_app('testing')
    app.config['WTF_CSRF_ENABLED'] = False
    client = app.test_client()
    ctx = app.app_context()
    ctx.push()
    db.create_all()

    org = Organization(name="Test Org", slug="test-org")
    db.session.add(org)
    db.session.flush()
    team = Team(name="Test Team", organization_id=org.id, slug="test-team")
    db.session.add(team)
    db.session.flush()

    # Editor user (no OTP required), like tests/test_plays.py
    user = User(username=username, email=f'{username}@example.com', organization_id=org.id)
    user.set_password('password')
    db.session.add(user)
    db.session.flush()
    db.session.add(OrganizationMembership(
        user_id=user.id, organization_id=org.id, is_gm=False))
    db.session.add(TeamAssignment(user_id=user.id, team_id=team.id))
    db.session.commit()

    with client.session_transaction() as sess:
        sess['current_team_id'] = team.id

    login_resp = client.post('/auth/login', data={
        'username': username, 'password': 'password'}, follow_redirects=True)
    if b'Welcome back' not in login_resp.data and b'Dashboard' not in login_resp.data:
        raise RuntimeError(f"Login failed. Status: {login_resp.status_code}")
    testcase.team_id = team.id
    return app, client, ctx


class TestTraining(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.app_context = make_ctx(self)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _create_session(self, title="Thursday Scrimmage", date="2026-09-22"):
        resp = self.client.post('/trainings/new', data={
            'title': title, 'session_date': date, 'start_time': '18:00',
            'location': 'Main gym', 'focus': 'Offense', 'notes': 'Goals',
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        ts = TrainingSession.query.filter_by(title=title).first()
        self.assertIsNotNone(ts)
        return ts

    def test_session_lifecycle(self):
        # list empty
        resp = self.client.get('/trainings/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'No training sessions yet', resp.data)

        # create
        ts = self._create_session()
        self.assertEqual(ts.location, 'Main gym')
        self.assertEqual(ts.focus, 'Offense')

        # list shows it
        resp = self.client.get('/trainings/')
        self.assertIn(b'Thursday Scrimmage', resp.data)

        # detail
        resp = self.client.get(f'/trainings/{ts.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Main gym', resp.data)

        # validation
        resp = self.client.post('/trainings/new', data={
            'title': '', 'session_date': ''}, follow_redirects=True)
        self.assertIn(b'Title and date are required', resp.data)

        # edit
        resp = self.client.post(f'/trainings/{ts.id}/edit', data={
            'title': 'Wednesday Practice', 'session_date': '2026-09-23',
            'start_time': '', 'location': '', 'focus': '', 'notes': '',
        }, follow_redirects=True)
        self.assertIn(b'Wednesday Practice', resp.data)

        # delete requires GM (admin_required): non-GM is redirected away
        # and the session survives
        resp = self.client.post(f'/trainings/{ts.id}/delete', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIsNotNone(TrainingSession.query.get(ts.id))

    def test_team_isolation(self):
        ts = self._create_session()
        other_org = Organization(name="Other Org", slug="other-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team")
        db.session.add(other_team)
        db.session.flush()
        # Assign the user to the other team so the session switch is
        # honored; the original session's object must still be invisible.
        from core.models import User as _User
        user = _User.query.filter_by(username="training_test_user").first()
        if user is not None:
            db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
            db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        # consume the queued "scheduled" flash from setup first
        self.client.get('/trainings/')
        resp = self.client.get(f'/trainings/{ts.id}')
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get('/trainings/')
        self.assertNotIn(b'Thursday Scrimmage', resp.data)

    def test_segments_with_linked_play(self):
        ts = self._create_session()
        play = Play(name='Horns Twist', play_type='Offense', team_id=self.team_id)
        db.session.add(play)
        db.session.commit()

        resp = self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Shell drill', 'duration_min': '15',
            'play_id': str(play.id), 'notes': 'Closeouts',
        }, follow_redirects=True)
        self.assertIn(b'Shell drill', resp.data)
        self.assertIn(b'Horns Twist', resp.data)
        seg = TrainingSegment.query.filter_by(session_id=ts.id).first()
        self.assertEqual(seg.play_id, play.id)
        self.assertEqual(seg.position, 1)

        # invalid play id is ignored, not fatal
        resp = self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Warm-up', 'duration_min': '', 'play_id': '9999', 'notes': '',
        }, follow_redirects=True)
        self.assertIn(b'Warm-up', resp.data)
        seg2 = TrainingSegment.query.filter_by(title='Warm-up').first()
        self.assertIsNone(seg2.play_id)
        self.assertEqual(seg2.position, 2)

        # delete segment
        resp = self.client.post(f'/trainings/segments/{seg.id}/delete', follow_redirects=True)
        self.assertIsNone(TrainingSegment.query.get(seg.id))

    def test_attendance_flow(self):
        ts = self._create_session()
        p1 = Player(name='Alice', team_id=self.team_id, active=True)
        p2 = Player(name='Bob', team_id=self.team_id, active=True)
        p3 = Player(name='Cara', team_id=self.team_id, active=False)
        db.session.add_all([p1, p2, p3])
        db.session.commit()

        # seed loads only active players
        resp = self.client.post(
            f'/trainings/{ts.id}/attendance/seed', follow_redirects=True)
        self.assertIn(b'Alice', resp.data)
        self.assertIn(b'Bob', resp.data)
        self.assertNotIn(b'Cara', resp.data)
        self.assertEqual(TrainingAttendance.query.filter_by(session_id=ts.id).count(), 2)

        # re-seed is idempotent
        self.client.post(f'/trainings/{ts.id}/attendance/seed', follow_redirects=True)
        self.assertEqual(TrainingAttendance.query.filter_by(session_id=ts.id).count(), 2)

        # status change
        att = TrainingAttendance.query.filter_by(player_id=p1.id).first()
        self.assertEqual(att.status, 'present')
        resp = self.client.post(f'/trainings/attendance/{att.id}/status',
                                data={'status': 'absent'}, follow_redirects=True)
        self.assertEqual(TrainingAttendance.query.get(att.id).status, 'absent')

        # invalid status rejected
        resp = self.client.post(f'/trainings/attendance/{att.id}/status',
                                data={'status': 'maybe'}, follow_redirects=True)
        self.assertIn(b'Unknown status', resp.data)
        self.assertEqual(TrainingAttendance.query.get(att.id).status, 'absent')

    def test_export_session_pdf(self):
        ts = self._create_session()
        diagram_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" '
            'width="800" height="500" preserveAspectRatio="xMidYMid meet">'
            '<rect width="800" height="500" fill="#e8c89b"/>'
            '<rect x="150" y="15" width="500" height="470" fill="none" stroke="#ffffff" stroke-width="3"/>'
            '<path d="M 200 400 L 400 250 L 600 400" fill="none" stroke="#ff0000" stroke-width="3"/>'
            '<circle cx="400" cy="250" r="10" fill="#0000ff"/>'
            '<line x1="150" y1="485" x2="650" y2="485" stroke="#ffffff" stroke-width="3"/>'
            '</svg>'
        )
        play = Play(name='Horns Twist', play_type='Offense', team_id=self.team_id,
                    diagram_svg=diagram_svg)
        db.session.add(play)
        p1 = Player(name='Alice', team_id=self.team_id, active=True)
        db.session.add_all([p1])
        db.session.commit()
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Shell drill', 'duration_min': '15',
            'play_id': str(play.id), 'notes': 'Closeouts',
        }, follow_redirects=True)
        # a segment without a linked play renders no diagram
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Warm-up jog', 'duration_min': '10',
            'play_id': '', 'notes': '',
        }, follow_redirects=True)
        self.client.post(f'/trainings/{ts.id}/attendance/seed', follow_redirects=True)
        att = TrainingAttendance.query.filter_by(player_id=p1.id).first()
        self.client.post(f'/trainings/attendance/{att.id}/status',
                         data={'status': 'excused'}, follow_redirects=True)

        resp = self.client.get(f'/trainings/{ts.id}/pdf')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'application/pdf')
        self.assertTrue(resp.data.startswith(b'%PDF'))
        self.assertIn(b'Training_', resp.headers.get('Content-Disposition', '').encode())
        # diagram embedded: PDF with the drill diagram is larger than without
        play.diagram_svg = None
        db.session.commit()
        resp_no_diagram = self.client.get(f'/trainings/{ts.id}/pdf')
        self.assertEqual(resp_no_diagram.status_code, 200)
        self.assertGreater(len(resp.data), len(resp_no_diagram.data))

        # team isolation: another team cannot export
        other_org = Organization(name="Other Org", slug="other-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team")
        db.session.add(other_team)
        db.session.flush()
        user = User.query.filter_by(username="training_test_user").first()
        db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        resp = self.client.get(f'/trainings/{ts.id}/pdf')
        self.assertEqual(resp.status_code, 404)

    def _add_segment(self, session_id, title, duration="10"):
        resp = self.client.post(f'/trainings/{session_id}/segments/add', data={
            'title': title, 'duration_min': duration,
            'play_id': '', 'notes': '',
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        return TrainingSegment.query.filter_by(
            session_id=session_id, title=title).first()

    def _agenda_titles(self, session_id):
        segs = (TrainingSegment.query.filter_by(session_id=session_id)
                .order_by(TrainingSegment.position).all())
        return [s.title for s in segs]

    def test_reorder_segments(self):
        ts = self._create_session()
        a = self._add_segment(ts.id, "Warm-up")
        b = self._add_segment(ts.id, "Shell drill")
        c = self._add_segment(ts.id, "Scrimmage")
        self.assertEqual(self._agenda_titles(ts.id), ["Warm-up", "Shell drill", "Scrimmage"])

        # move middle up
        resp = self.client.post(f'/trainings/segments/{b.id}/move',
                                data={'direction': 'up'}, follow_redirects=True)
        self.assertIn(b'moved up', resp.data)
        self.assertEqual(self._agenda_titles(ts.id), ["Shell drill", "Warm-up", "Scrimmage"])

        # move it back down
        resp = self.client.post(f'/trainings/segments/{b.id}/move',
                                data={'direction': 'down'}, follow_redirects=True)
        self.assertIn(b'moved down', resp.data)
        self.assertEqual(self._agenda_titles(ts.id), ["Warm-up", "Shell drill", "Scrimmage"])

        # boundary moves are no-ops but still redirect cleanly
        resp = self.client.post(f'/trainings/segments/{a.id}/move',
                                data={'direction': 'up'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._agenda_titles(ts.id), ["Warm-up", "Shell drill", "Scrimmage"])
        resp = self.client.post(f'/trainings/segments/{c.id}/move',
                                data={'direction': 'down'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._agenda_titles(ts.id), ["Warm-up", "Shell drill", "Scrimmage"])

        # invalid direction rejected
        resp = self.client.post(f'/trainings/segments/{a.id}/move',
                                data={'direction': 'sideways'}, follow_redirects=True)
        self.assertIn(b'Unknown direction', resp.data)
        self.assertEqual(self._agenda_titles(ts.id), ["Warm-up", "Shell drill", "Scrimmage"])

        # team isolation
        other_org = Organization(name="Other Org", slug="other-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team")
        db.session.add(other_team)
        db.session.flush()
        user = User.query.filter_by(username="training_test_user").first()
        db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        resp = self.client.post(f'/trainings/segments/{a.id}/move',
                                data={'direction': 'down'}, follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

    def test_edit_segment(self):
        ts = self._create_session()
        play = Play(name='Horns Twist', play_type='Offense', team_id=self.team_id)
        db.session.add(play)
        db.session.commit()
        seg = self._add_segment(ts.id, "Shell drill")

        # edit title, duration, notes, category; library template follows
        resp = self.client.post(f'/trainings/segments/{seg.id}/edit', data={
            'title': 'Shell drill v2', 'duration_min': '20',
            'play_id': str(play.id), 'notes': 'Closeouts!', 'category': 'Defense',
        }, follow_redirects=True)
        self.assertIn(b'Shell drill v2', resp.data)
        seg = TrainingSegment.query.get(seg.id)
        self.assertEqual(seg.title, 'Shell drill v2')
        self.assertEqual(seg.duration_min, 20)
        self.assertEqual(seg.play_id, play.id)
        self.assertEqual(seg.notes, 'Closeouts!')
        tpl = TrainingSegmentTemplate.query.filter_by(
            team_id=self.team_id, title='Shell drill v2').first()
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl.duration_min, 20)
        self.assertIsNone(TrainingSegmentTemplate.query.filter_by(
            team_id=self.team_id, title='Shell drill').first())

        # validation: empty title and bad duration rejected
        resp = self.client.post(f'/trainings/segments/{seg.id}/edit', data={
            'title': '', 'duration_min': '', 'play_id': '', 'notes': '',
        }, follow_redirects=True)
        self.assertIn(b'Segment title is required', resp.data)
        resp = self.client.post(f'/trainings/segments/{seg.id}/edit', data={
            'title': 'Shell drill v2', 'duration_min': '999',
            'play_id': '', 'notes': '',
        }, follow_redirects=True)
        self.assertIn(b'Duration must be 1-480 minutes', resp.data)
        self.assertEqual(TrainingSegment.query.get(seg.id).duration_min, 20)

        # team isolation
        other_org = Organization(name="Other Org", slug="other-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team")
        db.session.add(other_team)
        db.session.flush()
        user = User.query.filter_by(username="training_test_user").first()
        db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        resp = self.client.post(f'/trainings/segments/{seg.id}/edit', data={
            'title': 'Hacked', 'duration_min': '',
            'play_id': '', 'notes': '',
        }, follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

    def _upload_session(self, content, filename='Training_session.json'):
        import io

        payload = content if isinstance(content, bytes) else content.encode('utf-8')
        return self.client.post('/trainings/import', data={
            'session_file': (io.BytesIO(payload), filename),
        }, content_type='multipart/form-data', follow_redirects=True)

    def test_export_session_file(self):
        import json

        ts = self._create_session()
        play = Play(name='Horns File Play', play_type='Offense', team_id=self.team_id)
        p1 = Player(name='Alice', team_id=self.team_id, active=True)
        db.session.add_all([play, p1])
        db.session.commit()
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Shell drill', 'duration_min': '15',
            'play_id': str(play.id), 'notes': 'Closeouts',
        }, follow_redirects=True)
        self.client.post(f'/trainings/{ts.id}/attendance/seed', follow_redirects=True)

        resp = self.client.get(f'/trainings/{ts.id}/export')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp.content_type)
        self.assertIn('.json', resp.headers.get('Content-Disposition', ''))
        body = json.loads(resp.data)
        self.assertEqual(body['kind'], 'training_session')
        self.assertEqual(body['session']['title'], 'Thursday Scrimmage')
        self.assertEqual(body['session']['session_date'], '2026-09-22')
        self.assertEqual(body['session']['segments'][0]['title'], 'Shell drill')
        self.assertEqual(body['session']['segments'][0]['play'], 'Horns File Play')
        self.assertEqual(body['session']['attendance'][0]['player'], 'Alice')

        # cross-team export is hidden
        other_org = Organization(name="Other Org", slug="other-org-file")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team-file")
        db.session.add(other_team)
        db.session.flush()
        user = User.query.filter_by(username="training_test_user").first()
        db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        resp = self.client.get(f'/trainings/{ts.id}/export')
        self.assertEqual(resp.status_code, 404)

    def test_import_session_round_trip(self):
        import json

        ts = self._create_session()
        play = Play(name='Horns Import Play', play_type='Offense', team_id=self.team_id)
        p1 = Player(name='Alice', team_id=self.team_id, active=True)
        p2 = Player(name='Bob', team_id=self.team_id, active=True)
        db.session.add_all([play, p1, p2])
        db.session.commit()
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Shell drill', 'duration_min': '15',
            'play_id': str(play.id), 'notes': 'Closeouts',
        }, follow_redirects=True)
        self.client.post(f'/trainings/{ts.id}/attendance/seed', follow_redirects=True)
        exported = self.client.get(f'/trainings/{ts.id}/export').data

        # same-team import: play re-links by name, attendance matched by name
        resp = self._upload_session(exported)
        self.assertIn(b'imported (1 segments, 2 attendance)', resp.data)
        self.assertNotIn(b'not found', resp.data)
        same = TrainingSession.query.filter(
            TrainingSession.team_id == self.team_id,
            TrainingSession.id != ts.id).first()
        self.assertIsNotNone(same)
        seg = TrainingSegment.query.filter_by(session_id=same.id).first()
        self.assertEqual(seg.play_id, play.id)
        statuses = sorted(
            a.status for a in TrainingAttendance.query.filter_by(session_id=same.id).all())
        self.assertEqual(statuses, ['present', 'present'])

        # import into a second team: play re-links by name only if present
        other_org = Organization(name="Other Org", slug="other-org-imp")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team-imp")
        db.session.add(other_team)
        db.session.flush()
        user = User.query.filter_by(username="training_test_user").first()
        db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
        db.session.add(Player(name='Zoe', team_id=other_team.id, active=True))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        resp = self._upload_session(exported)
        self.assertIn(b'imported (1 segments, 0 attendance)', resp.data)
        self.assertIn(b'Players not found: Alice, Bob', resp.data)
        self.assertIn(b'Plays not found: Horns Import Play', resp.data)
        imported = TrainingSession.query.filter_by(
            team_id=other_team.id, title='Thursday Scrimmage').first()
        self.assertIsNotNone(imported)
        seg = TrainingSegment.query.filter_by(session_id=imported.id).first()
        self.assertEqual(seg.title, 'Shell drill')
        self.assertEqual(seg.position, 1)
        self.assertIsNone(seg.play_id)
        atts = TrainingAttendance.query.filter_by(session_id=imported.id).all()
        self.assertEqual(atts, [])

    def test_import_session_rejects_bad_files(self):
        resp = self._upload_session(b'not json')
        self.assertIn(b'not valid JSON', resp.data)
        resp = self._upload_session('{"session": {"title": "", "session_date": "bad"}}')
        self.assertIn(b'Invalid session file', resp.data)
        resp = self._upload_session(b'{}', filename='session.txt')
        self.assertIn(b'must be a .json export', resp.data)
        resp = self.client.post('/trainings/import', data={},
                                content_type='multipart/form-data',
                                follow_redirects=True)
        self.assertIn(b'Select a session file', resp.data)
        self.assertEqual(TrainingSession.query.count(), 0)

    def test_import_session_auditor_blocked(self):
        user = User.query.filter_by(username="training_test_user").first()
        user.is_auditor = True
        db.session.commit()
        resp = self.client.post('/trainings/import', data={},
                                content_type='multipart/form-data',
                                follow_redirects=True)
        self.assertIn(b'read-only', resp.data)
        self.assertEqual(TrainingSession.query.count(), 0)

    def test_export_session_pdf_storyboard(self):
        from web.routes.training import STORYBOARD_MAX_PHASES
        from core.models import PlaySequence

        ts = self._create_session()
        play = Play(name='Storyboard Play', play_type='Offense', team_id=self.team_id,
                    diagram_svg='<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        db.session.add(play)
        db.session.flush()
        for i in range(STORYBOARD_MAX_PHASES + 1):
            db.session.add(PlaySequence(
                play_id=play.id, sequence_number=i + 1,
                element_data={'objects': []}, caption=f'Phase {i + 1}',
                svg_snapshot='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500" width="800" height="500"><rect width="800" height="500" fill="#e8c89b"/></svg>'))
        db.session.commit()
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Motion drill', 'duration_min': '15',
            'play_id': str(play.id), 'notes': '',
        }, follow_redirects=True)

        # full-court drill exercises the 4-per-page storyboard branch
        full = Play(name='Full Court Drill', play_type='Offense', team_id=self.team_id,
                    court_type='full',
                    diagram_svg='<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        db.session.add(full)
        db.session.flush()
        for i in range(5):
            db.session.add(PlaySequence(
                play_id=full.id, sequence_number=i + 1,
                element_data={'objects': []}, caption=f'Phase {i + 1}',
                svg_snapshot='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 1000" width="800" height="1000"><rect width="800" height="1000" fill="#e8c89b"/></svg>'))
        db.session.commit()
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Full court drill', 'duration_min': '20',
            'play_id': str(full.id), 'notes': '',
        }, follow_redirects=True)

        resp = self.client.get(f'/trainings/{ts.id}/pdf')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'application/pdf')
        self.assertTrue(resp.data.startswith(b'%PDF'))

    def test_post_training_notes(self):
        import json

        ts = self._create_session()
        resp = self.client.post(f'/trainings/{ts.id}/edit', data={
            'title': ts.title, 'session_date': ts.session_date,
            'start_time': '', 'location': '', 'focus': '', 'notes': '',
            'post_notes': 'Great intensity, shooting was off.',
        }, follow_redirects=True)
        self.assertIn(b'Post-Training Notes', resp.data)
        self.assertIn(b'Great intensity', resp.data)
        self.assertEqual(TrainingSession.query.get(ts.id).post_notes,
                         'Great intensity, shooting was off.')

        # export file carries them, import restores them
        exported = self.client.get(f'/trainings/{ts.id}/export').data
        self.assertEqual(json.loads(exported)['session']['post_notes'],
                         'Great intensity, shooting was off.')
        db.session.delete(ts)
        db.session.commit()
        resp = self._upload_session(exported)
        self.assertIn(b'Great intensity', resp.data)
        restored = TrainingSession.query.filter_by(title='Thursday Scrimmage').first()
        self.assertEqual(restored.post_notes, 'Great intensity, shooting was off.')

        # clearing works too
        resp = self.client.post(f'/trainings/{restored.id}/edit', data={
            'title': restored.title, 'session_date': restored.session_date,
            'start_time': '', 'location': '', 'focus': '', 'notes': '',
            'post_notes': '',
        }, follow_redirects=True)
        self.assertIn(b'No debrief yet', resp.data)
        self.assertIsNone(TrainingSession.query.get(restored.id).post_notes)

    def test_segment_templates(self):
        ts = self._create_session()
        ts2 = self._create_session(title="Friday Practice", date="2026-09-23")

        # Adding a segment auto-saves it into the team library
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Shell drill', 'duration_min': '15',
            'play_id': '', 'notes': 'Closeouts', 'category': 'Defense',
        }, follow_redirects=True)
        tpl = TrainingSegmentTemplate.query.filter_by(
            team_id=self.team_id, title='Shell drill').first()
        self.assertIsNotNone(tpl)
        self.assertEqual(tpl.duration_min, 15)
        self.assertEqual(tpl.notes, 'Closeouts')
        self.assertEqual(tpl.category, 'Defense')
        self.assertEqual(tpl.usage_count, 1)

        # Re-adding the same title updates rather than duplicating
        self.client.post(f'/trainings/{ts.id}/segments/add', data={
            'title': 'Shell drill', 'duration_min': '20',
            'play_id': '', 'notes': '',
        }, follow_redirects=True)
        self.assertEqual(
            TrainingSegmentTemplate.query.filter_by(
                team_id=self.team_id, title='Shell drill').count(), 1)
        tpl = TrainingSegmentTemplate.query.filter_by(
            team_id=self.team_id, title='Shell drill').first()
        self.assertEqual(tpl.duration_min, 20)
        self.assertEqual(tpl.usage_count, 2)

        # Apply the template to another session
        resp = self.client.post(
            f'/trainings/{ts2.id}/templates/{tpl.id}/apply', follow_redirects=True)
        self.assertIn(b'Shell drill', resp.data)
        seg = TrainingSegment.query.filter_by(
            session_id=ts2.id, title='Shell drill').first()
        self.assertIsNotNone(seg)
        self.assertEqual(seg.duration_min, 20)
        self.assertEqual(seg.position, 1)

        # Library is shown on the session page
        resp = self.client.get(f'/trainings/{ts2.id}')
        self.assertIn(b'From library', resp.data)

        # regression: no nested <form> tags — nested quick-add forms once
        # closed the add-segment form early and broke its Add button
        from html.parser import HTMLParser

        class _FormDepth(HTMLParser):
            def __init__(self):
                super().__init__()
                self.depth = 0
                self.max_depth = 0

            def handle_starttag(self, tag, attrs):
                if tag == 'form':
                    self.depth += 1
                    self.max_depth = max(self.max_depth, self.depth)

            def handle_endtag(self, tag):
                if tag == 'form':
                    self.depth -= 1

        parser = _FormDepth()
        parser.feed(resp.data.decode('utf-8'))
        self.assertEqual(parser.max_depth, 1)
        self.assertIn(b'id="addSegmentForm"', resp.data)

        # Team isolation: hidden + not applicable from another team
        other_org = Organization(name="Other Org", slug="other-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id, slug="other-team")
        db.session.add(other_team)
        db.session.flush()
        user = User.query.filter_by(username="training_test_user").first()
        db.session.add(TeamAssignment(user_id=user.id, team_id=other_team.id))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = other_team.id
        resp = self.client.post(
            f'/trainings/{ts2.id}/templates/{tpl.id}/apply', follow_redirects=False)
        self.assertEqual(resp.status_code, 404)

        # Delete the template
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = self.team_id
        resp = self.client.post(
            f'/trainings/templates/{tpl.id}/delete', follow_redirects=True)
        self.assertIn(b'removed from library', resp.data)
        self.assertIsNone(TrainingSegmentTemplate.query.get(tpl.id))


class TestPlayCourtType(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.app_context = make_ctx(self, username="court_test_user")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def _save_play(self, name, court):
        payload = {
            'play_id': None,
            'metadata': {'name': name, 'play_type': 'Offense', 'court_type': court},
            'canvas_json': {'objects': []},
            'diagram_svg': '<svg></svg>',
            'frames': [],
        }
        resp = self.client.post('/api/v1/plays/api/save-canvas',
                                data=json.dumps(payload),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200, resp.data[:300])
        return json.loads(resp.data)

    def test_save_and_load_full_court(self):
        data = self._save_play('Full Court Press Break', 'full')
        play = Play.query.filter_by(name='Full Court Press Break').first()
        self.assertEqual(play.court_type, 'full')

        resp = self.client.get(f"/api/v1/plays/api/load-canvas/{play.id}")
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        self.assertEqual(body['metadata']['court_type'], 'full')

        # detail renders full-court badge + tall canvas
        resp = self.client.get(f'/plays/{play.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Full court', resp.data)
        self.assertIn(b'height="1000"', resp.data)

    def test_invalid_court_defaults_half(self):
        self._save_play('Half Court Set', 'arena')
        play = Play.query.filter_by(name='Half Court Set').first()
        self.assertEqual(play.court_type, 'half')
        resp = self.client.get(f'/plays/{play.id}')
        self.assertIn(b'Half court', resp.data)
        self.assertIn(b'height="500"', resp.data)

    def test_court_type_update(self):
        data = self._save_play('Switchable', 'half')
        payload = {
            'play_id': data['play_id'],
            'metadata': {'name': 'Switchable', 'play_type': 'Offense', 'court_type': 'full'},
            'canvas_json': {'objects': []},
            'diagram_svg': '<svg></svg>',
            'frames': [],
        }
        resp = self.client.post('/api/v1/plays/api/save-canvas',
                                data=json.dumps(payload),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        play = Play.query.filter_by(name='Switchable').first()
        self.assertEqual(play.court_type, 'full')


if __name__ == '__main__':
    unittest.main()
