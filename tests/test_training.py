import json
import unittest
from web import create_app, db
from core.models import (
    User, Organization, Team, OrganizationMembership, TeamAssignment, Play,
    Player, TrainingSession, TrainingSegment, TrainingAttendance,
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
