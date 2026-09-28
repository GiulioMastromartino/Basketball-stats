"""Tests for per-user Google Drive export sync.

No test here touches the real Drive API. The Drive client is faked at the
``drive_service._get_service`` boundary, mirroring how WeasyPrint is mocked in
tests/conftest.py. ``FakeDriveService`` models folder find-or-create, file
create/update, and fault injection so the behaviour that actually matters
(idempotent re-export, failure isolation, folder caching) is exercised.
"""

import contextlib
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

from cryptography.fernet import Fernet
from googleapiclient.errors import HttpError
from itsdangerous import URLSafeTimedSerializer

from web import create_app, db
from core.models import (
    User, Organization, Team, OrganizationMembership, TeamAssignment,
    TrainingSession, GoogleDriveConnection, GoogleDriveDocPref,
)
from core.services import drive_service, drive_sync_types

FOLDER_MIME = drive_service.FOLDER_MIME


# ---------------------------------------------------------------------------
# Fake Drive client
# ---------------------------------------------------------------------------

class _Exec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


def _parse_q(q):
    """Pull (name, parent) out of a Drive ``q=`` string.

    Good enough for the shapes drive_service generates; a mismatch here would
    show up as folders not being reused, which the tests assert against.
    """
    name = None
    parent = None
    parts = q.split(" and ")
    for p in parts:
        p = p.strip()
        if p.startswith("name ="):
            name = p.split("'")[1].replace("\\'", "'").replace("\\\\", "\\")
        elif p.endswith("in parents"):
            parent = p.split("'")[1].replace("\\'", "'")
    return name, parent


class _FakeFiles:
    def __init__(self, svc):
        self.svc = svc

    def list(self, q=None, **kwargs):
        name, parent = _parse_q(q)
        self.svc.list_calls.append(q)
        if self.svc.list_404:
            # Models a cached folder id that no longer exists. Only the first
            # call fails, so the service's re-resolve attempt can succeed.
            self.svc.list_404 = False
            raise HttpError(
                mock.Mock(status=404, reason="notFound"), b"not found"
            )
        matches = [
            {"id": fid} for fid, meta in self.svc.folder_records.items()
            if meta["name"] == name and meta["parents"] == parent
        ]
        return _Exec({"files": matches})

    def create(self, body=None, media_body=None, **kwargs):
        self.svc.create_calls.append(body)
        if body.get("mimeType") == FOLDER_MIME:
            parent = (body.get("parents") or [None])[0]
            # A folder whose parent was deleted cannot be created either.
            if parent is not None and parent not in self.svc.folder_records:
                raise HttpError(
                    mock.Mock(status=404, reason="notFound"), b"not found"
                )
            # Folder creates carry no media; only count real file uploads.
            fid = f"id{self.svc.next_id}"
            self.svc.next_id += 1
            self.svc.folder_records[fid] = {
                "name": body["name"],
                "parents": parent,
            }
            return _Exec({"id": fid})

        parent = (body.get("parents") or [None])[0]
        # Models the real failure when our cached folder ids are stale: the
        # create lands in a folder that no longer exists.
        if parent is not None and parent not in self.svc.folder_records:
            raise HttpError(
                mock.Mock(status=404, reason="notFound"), b"not found"
            )
        if media_body is not None:
            self.svc.media_bodies.append(media_body)
        fid = f"id{self.svc.next_id}"
        self.svc.next_id += 1
        self.svc.file_records[fid] = {
            "name": body.get("name"),
            "parents": parent,
        }
        return _Exec({"id": fid})

    def update(self, fileId=None, media_body=None, **kwargs):
        self.svc.update_calls.append(fileId)
        # An update to a file that no longer exists (or whose folder was
        # deleted) 404s, just like the real API.
        if fileId in self.svc.update_404 or fileId not in self.svc.file_records:
            raise HttpError(
                mock.Mock(status=404, reason="notFound"), b"not found"
            )
        if media_body is not None:
            self.svc.media_bodies.append(media_body)
        return _Exec({"id": fileId})


class FakeDriveService:
    """Records every Drive interaction so tests can assert on the call pattern."""

    def __init__(self):
        self.folder_records = {}
        self.file_records = {}
        self.list_calls = []
        self.create_calls = []
        self.update_calls = []
        self.media_bodies = []
        self.update_404 = set()
        self.list_404 = False
        self.next_id = 1

    def files(self):
        return _FakeFiles(self)

    def reset_folders(self):
        """Forget the folder tree, as if the user deleted it in Drive.

        Deleting a folder destroys its contents, so file ids go stale too.
        """
        self.folder_records = {}
        self.file_records = {}
        self.list_404 = True


    # -- helpers for assertions -------------------------------------------
    def created_folder_names(self):
        return [b["name"] for b in self.create_calls if b.get("mimeType") == FOLDER_MIME]

    def created_file_names(self):
        return [b["name"] for b in self.create_calls if b.get("mimeType") != FOLDER_MIME]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

class DriveTestCase(unittest.TestCase):
    DRIVE_ON = True

    def setUp(self):
        self.app = create_app("testing")
        self.app.config["WTF_CSRF_ENABLED"] = False
        if self.DRIVE_ON:
            self.app.config.update(
                GOOGLE_DRIVE_CLIENT_ID="test-client-id",
                GOOGLE_DRIVE_CLIENT_SECRET="test-secret",
                GOOGLE_DRIVE_TOKEN_KEY=Fernet.generate_key().decode(),
                GOOGLE_DRIVE_REDIRECT_URI=(
                    "http://localhost:8080/integrations/google/callback"
                ),
                GOOGLE_DRIVE_ROOT_FOLDER="HoopsLab",
            )
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        org = Organization(name="Test Org", slug="test-org")
        db.session.add(org)
        db.session.flush()
        self.team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(self.team)
        db.session.flush()

        self.user = User(
            username="drive_user", email="drive_user@example.com",
            organization_id=org.id,
        )
        self.user.set_password("password")
        db.session.add(self.user)
        db.session.flush()
        # GM so the admin settings page (where the Drive block lives) is
        # reachable; admin_panel is behind admin_view_required.
        db.session.add(OrganizationMembership(
            user_id=self.user.id, organization_id=org.id, is_gm=True))
        db.session.add(TeamAssignment(user_id=self.user.id, team_id=self.team.id))
        db.session.commit()

        self.client = self.app.test_client()
        # Inject the Flask-Login session directly rather than posting the login
        # form: GM accounts are forced through an OTP step, and this mirrors
        # the admin_client fixture in tests/conftest.py.
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(self.user.id)
            sess["_fresh"] = True
            sess["current_team_id"] = self.team.id
            sess["current_team_name"] = self.team.name

        # Stub the renderer at the name training.py actually uses. Patching
        # "weasyprint.HTML" has no effect there because the module did
        # `from weasyprint import HTML` at import time.
        pdf = mock.MagicMock()
        pdf.write_pdf.return_value = b"%PDF-1.4 fake"
        self._html_patch = mock.patch(
            "web.routes.training.HTML", return_value=pdf
        )
        self._html_patch.start()
        self.addCleanup(self._html_patch.stop)
        self.pdf_mock = pdf

        self.drive = FakeDriveService()
        # Keep a handle on the created mock so individual tests can change
        # its behaviour (e.g. simulate an outage) via self.get_service.
        self.get_service = mock.MagicMock(side_effect=lambda uid: self.drive)
        self._svc_patch = mock.patch.object(
            drive_service, "_get_service", self.get_service
        )
        self._svc_patch.start()
        self.addCleanup(self._svc_patch.stop)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # -- helpers -----------------------------------------------------------
    def make_connection(self, active=True, auto_upload=False):
        conn = GoogleDriveConnection(
            user_id=self.user.id,
            refresh_token_enc=drive_service.encrypt_token("refresh-abc"),
            access_token_enc=drive_service.encrypt_token("access-abc"),
            token_uri=drive_service.TOKEN_ENDPOINT,
            scopes=" ".join(drive_service.SCOPES),
            # Left unset so the level-1 root folder is exercised too.
            root_folder_id=None,
            status=(GoogleDriveConnection.STATUS_ACTIVE if active
                    else GoogleDriveConnection.STATUS_NEEDS_REAUTH),
            auto_upload=auto_upload,
        )
        db.session.add(conn)
        db.session.commit()
        return conn

    def enable_prefs(self, auto_upload=True, **doc_types):
        conn = self.make_connection(auto_upload=auto_upload)
        for key, enabled in doc_types.items():
            db.session.add(GoogleDriveDocPref(
                user_id=self.user.id, doc_type=key, enabled=enabled))
        db.session.commit()
        return conn

    def make_session(self, title="Thursday Scrimmage", date="2026-09-22"):
        ts = TrainingSession(
            team_id=self.team.id, title=title, session_date=date,
            start_time="18:00", location="Main gym", focus="Offense",
        )
        db.session.add(ts)
        db.session.commit()
        return ts

    def _login_as(self, user):
        """Switch the test client to act as ``user``."""
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True
            sess["current_team_id"] = self.team.id
            sess["current_team_name"] = self.team.name
        # Flask-Login caches the loaded user on flask.g, which lives on the
        # app context this test holds open for its whole lifetime. Without
        # this, the next request would keep seeing the previous user even
        # though the session now says otherwise.
        from flask import g

        g.pop("_login_user", None)

    def demote_to_coach(self):
        """Strip GM rights, leaving a plain coach on the team.

        Drive linking is a per-user action, so the UI must not be gated behind
        admin_view_required (GM or auditor).
        """
        from core.models import OrganizationMembership

        OrganizationMembership.query.filter_by(
            user_id=self.user.id, is_gm=True
        ).update({"is_gm": False})
        db.session.commit()
        db.session.refresh(self.user)
        return self.user


# ---------------------------------------------------------------------------
# Config gating
# ---------------------------------------------------------------------------

class TestFeatureFlag(DriveTestCase):
    DRIVE_ON = False

    def test_disabled_without_secrets(self):
        self.assertFalse(drive_service.is_enabled())

    def test_routes_404_when_unconfigured(self):
        # The surface is hidden rather than showing a button that cannot work.
        for path in ("/integrations/google/start", "/integrations/google/prefs"):
            resp = self.client.get(path) if path.endswith("start") \
                else self.client.post(path)
            self.assertEqual(resp.status_code, 404, path)

    def test_settings_block_hidden(self):
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'id="saveDriveForm"', resp.data)
        settings = self.client.get("/integrations/google")
        self.assertEqual(settings.status_code, 200)
        self.assertIn(b"not configured on this server", settings.data)

    def test_missing_token_key_never_falls_back_to_plaintext(self):
        # Token key absent => feature off, even with client id/secret present.
        self.app.config.update(
            GOOGLE_DRIVE_CLIENT_ID="x", GOOGLE_DRIVE_CLIENT_SECRET="y",
            GOOGLE_DRIVE_REDIRECT_URI="http://localhost/cb",
        )
        self.assertFalse(drive_service.is_enabled())


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestSanitizers(unittest.TestCase):
    def test_folder_segment_preserves_unicode(self):
        self.assertEqual(
            drive_service.sanitize_folder_segment("Fernández U18"),
            "Fernández U18",
        )

    def test_folder_segment_strips_path_separators(self):
        # A "/" would otherwise create a phantom path segment in Drive.
        self.assertNotIn("/", drive_service.sanitize_folder_segment("A/B"))
        self.assertNotIn("\\", drive_service.sanitize_folder_segment("A\\B"))

    def test_folder_segment_strips_control_and_bidi_chars(self):
        out = drive_service.sanitize_folder_segment("Evil\u202eTeam")
        self.assertNotIn("\u202e", out)

    def test_folder_segment_fallback(self):
        self.assertEqual(drive_service.sanitize_folder_segment("", fallback="T"), "T")
        self.assertEqual(drive_service.sanitize_folder_segment("///", fallback="T"), "T")

    def test_filename_keeps_single_pdf_suffix(self):
        self.assertEqual(
            drive_service.sanitize_filename("Training_2026-09-22_Drill"),
            "Training_2026-09-22_Drill.pdf",
        )
        self.assertEqual(
            drive_service.sanitize_filename("Drill.pdf"), "Drill.pdf"
        )


class TestDocTypeRegistry(unittest.TestCase):
    def test_trainings_is_available(self):
        self.assertTrue(drive_sync_types.is_available("trainings"))
        self.assertEqual(drive_sync_types.folder_for("trainings"), "Trainings")

    def test_future_types_declared_but_unavailable(self):
        for key in ("games", "reports", "playbooks"):
            self.assertTrue(drive_sync_types.is_valid_doc_type(key))
            self.assertFalse(drive_sync_types.is_available(key))

    def test_unknown_type_rejected(self):
        self.assertFalse(drive_sync_types.is_valid_doc_type("nope"))
        self.assertIsNone(drive_sync_types.folder_for("nope"))

    def test_list_types_can_include_unavailable(self):
        keys = [t["key"] for t in drive_sync_types.list_types(
            include_unavailable=True)]
        self.assertIn("trainings", keys)
        self.assertIn("games", keys)


# ---------------------------------------------------------------------------
# State signing
# ---------------------------------------------------------------------------

class TestStateToken(DriveTestCase):
    def test_roundtrip(self):
        state = drive_service.build_state(self.user.id)
        self.assertEqual(drive_service.verify_state(state), self.user.id)

    def test_tampered_state_rejected(self):
        state = drive_service.build_state(self.user.id)
        self.assertIsNone(drive_service.verify_state(state[:-2] + "xy"))

    def test_garbage_state_rejected(self):
        self.assertIsNone(drive_service.verify_state("not-a-token"))
        self.assertIsNone(drive_service.verify_state(""))
        self.assertIsNone(drive_service.verify_state(None))

    def test_expired_state_rejected(self):
        ser = URLSafeTimedSerializer(
            self.app.config["SECRET_KEY"], salt="gdrive-oauth")
        state = ser.dumps({"uid": self.user.id, "n": "x"})
        with mock.patch.object(drive_service, "STATE_MAX_AGE", -1):
            self.assertIsNone(drive_service.verify_state(state))

    def test_state_signed_with_other_key_rejected(self):
        other = URLSafeTimedSerializer("a-different-secret", salt="gdrive-oauth")
        state = other.dumps({"uid": self.user.id, "n": "x"})
        self.assertIsNone(drive_service.verify_state(state))


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------

class TestTokenEncryption(DriveTestCase):
    def test_roundtrip(self):
        blob = drive_service.encrypt_token("secret-token")
        self.assertNotIn("secret-token", blob)
        self.assertEqual(drive_service.decrypt_token(blob), "secret-token")

    def test_empty_values_pass_through(self):
        self.assertIsNone(drive_service.encrypt_token(""))
        self.assertIsNone(drive_service.encrypt_token(None))
        self.assertIsNone(drive_service.decrypt_token(None))

    def test_wrong_key_yields_none_not_exception(self):
        blob = drive_service.encrypt_token("secret-token")
        other = Fernet(Fernet.generate_key())
        self.app.config["GOOGLE_DRIVE_TOKEN_KEY"] = other.generate_key().decode()
        # Must not raise: the user can re-link in one click.
        self.assertIsNone(drive_service.decrypt_token(blob))


# ---------------------------------------------------------------------------
# OAuth callback
# ---------------------------------------------------------------------------

class TestCallback(DriveTestCase):
    def test_valid_state_stores_connection_and_creates_root(self):
        state = drive_service.build_state(self.user.id)
        with mock.patch.object(drive_service, "connect") as connect:
            resp = self.client.get(
                f"/integrations/google/callback?code=abc&state={state}")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(connect.called)
        self.assertEqual(connect.call_args[0][0], self.user.id)
        self.assertEqual(connect.call_args[0][1], "abc")

    def test_state_for_different_user_rejected(self):
        other = User(username="other", email="other@example.com",
                     organization_id=self.user.organization_id)
        other.set_password("password")
        db.session.add(other)
        db.session.commit()
        state = drive_service.build_state(other.id)

        with mock.patch.object(drive_service, "connect") as connect:
            resp = self.client.get(
                f"/integrations/google/callback?code=abc&state={state}")
        self.assertEqual(resp.status_code, 302)
        # Signature is valid, but it was minted for another account.
        self.assertFalse(connect.called)

    def test_forged_state_rejected(self):
        with mock.patch.object(drive_service, "connect") as connect:
            resp = self.client.get(
                "/integrations/google/callback?code=abc&state=forged")
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(connect.called)

    def test_missing_code_rejected(self):
        state = drive_service.build_state(self.user.id)
        with mock.patch.object(drive_service, "connect") as connect:
            self.client.get(
                f"/integrations/google/callback?state={state}")
        self.assertFalse(connect.called)

    def test_user_declined_error_param(self):
        with mock.patch.object(drive_service, "connect") as connect:
            self.client.get(
                "/integrations/google/callback?error=access_denied&state=x")
        self.assertFalse(connect.called)

    def test_connect_failure_flashes_and_does_not_raise(self):
        state = drive_service.build_state(self.user.id)
        with mock.patch.object(
            drive_service, "connect",
            side_effect=drive_service.DriveSyncError("boom"),
        ):
            resp = self.client.get(
                f"/integrations/google/callback?code=abc&state={state}",
                follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"boom", resp.data)

    def test_auth_url_uses_drive_file_scope_and_offline_access(self):
        url = drive_service.build_auth_url("STATE")
        self.assertIn("accounts.google.com", url)
        self.assertIn("access_type=offline", url)
        self.assertIn("prompt=consent", url)
        self.assertIn("drive.file", url)
        # Only drive.file — a broader scope would change the app's Google risk
        # classification and trigger verification review.
        self.assertNotIn("auth%2Fdrive%3B", url.replace("auth/drive;", "auth%2Fdrive%3B"))

    def test_auth_url_redirect_uri_comes_from_config(self):
        url = drive_service.build_auth_url("STATE")
        self.assertIn("localhost%3A8080", url)

    def test_start_redirects_to_google(self):
        resp = self.client.get("/integrations/google/start")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("accounts.google.com", resp.headers["Location"])


# ---------------------------------------------------------------------------
# Disconnect & prefs
# ---------------------------------------------------------------------------

class TestDisconnectAndPrefs(DriveTestCase):
    def test_disconnect_removes_connection_and_prefs(self):
        self.enable_prefs(trainings=True)
        resp = self.client.post("/integrations/google/disconnect")
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(drive_service.get_connection(self.user.id))
        self.assertEqual(
            GoogleDriveDocPref.query.filter_by(user_id=self.user.id).count(), 0)

    def test_disconnect_is_post_only(self):
        self.enable_prefs()
        resp = self.client.get("/integrations/google/disconnect")
        self.assertEqual(resp.status_code, 405)
        self.assertIsNotNone(drive_service.get_connection(self.user.id))

    def test_prefs_save_master_switch_and_types(self):
        self.make_connection()
        resp = self.client.post("/integrations/google/prefs", data={
            "auto_upload": "on", "doc_type_trainings": "on",
        })
        self.assertEqual(resp.status_code, 302)
        conn = drive_service.get_connection(self.user.id)
        self.assertTrue(conn.auto_upload)
        self.assertTrue(drive_service.get_doc_prefs(self.user.id)["trainings"])

    def test_prefs_cannot_enable_unavailable_type(self):
        self.make_connection()
        # A hand-crafted POST must not switch on an unimplemented type.
        self.client.post("/integrations/google/prefs", data={
            "auto_upload": "on", "doc_type_games": "on",
        })
        prefs = drive_service.get_doc_prefs(self.user.id)
        self.assertFalse(prefs["games"])

    def test_prefs_require_connection(self):
        resp = self.client.post("/integrations/google/prefs", data={
            "auto_upload": "on", "doc_type_trainings": "on"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(GoogleDriveDocPref.query.count(), 0)

    def test_settings_shows_connect_when_disconnected(self):
        resp = self.client.get("/integrations/google")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Connect Google Drive", resp.data)

    def test_settings_shows_disconnect_when_connected(self):
        self.make_connection()
        resp = self.client.get("/integrations/google")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Disconnect Google Drive", resp.data)
        self.assertNotIn(b">Connect Google Drive", resp.data)

    def test_settings_reachable_by_a_plain_coach(self):
        # The whole point is per-user linking, so a non-GM coach must be able
        # to reach the page. admin_panel is behind admin_view_required.
        self.demote_to_coach()
        self.assertFalse(self.user.is_gm)
        denied = self.client.get("/admin/settings")
        self.assertEqual(denied.status_code, 302)  # blocked from admin panel
        allowed = self.client.get("/integrations/google")
        self.assertEqual(allowed.status_code, 200)
        self.assertIn(b"Connect Google Drive", allowed.data)

    def test_coach_can_complete_the_link_flow(self):
        self.demote_to_coach()
        state = drive_service.build_state(self.user.id)
        with mock.patch.object(drive_service, "connect") as connect:
            resp = self.client.get(
                f"/integrations/google/callback?code=abc&state={state}")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(connect.called)
        # Must not bounce the coach to a page they cannot see.
        self.assertIn("/integrations/google", resp.headers["Location"])


# ---------------------------------------------------------------------------
# Auto-upload gating — the "must never break downloads" contract
# ---------------------------------------------------------------------------

class TestAutoUploadGating(DriveTestCase):
    def test_no_connection_makes_no_drive_calls(self):
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.startswith(b"%PDF"))
        self.assertEqual(self.drive.create_calls, [])
        self.assertEqual(self.drive.list_calls, [])

    def test_toggle_off_makes_no_drive_calls(self):
        self.enable_prefs(auto_upload=False, trainings=True)
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.startswith(b"%PDF"))
        self.assertEqual(self.drive.create_calls, [])

    def test_not_connected_user_makes_no_drive_calls(self):
        # Linked but flagged for re-auth: skip rather than fail the download.
        self.enable_prefs(auto_upload=True, trainings=True)
        conn = drive_service.get_connection(self.user.id)
        conn.status = GoogleDriveConnection.STATUS_NEEDS_REAUTH
        db.session.commit()
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.drive.create_calls, [])

    def test_drive_failure_does_not_break_download(self):
        # Highest-severity defect this feature could ship.
        self.enable_prefs(auto_upload=True, trainings=True)
        self.get_service.side_effect = RuntimeError("drive is down")
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        # Highest-severity contract: a Drive outage must not corrupt or
        # replace the PDF the user asked to download.
        self.assertEqual(resp.data, b"%PDF-1.4 fake")
        self.assertIsNone(drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id))

    def test_drive_failure_records_last_error(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        self.get_service.side_effect = RuntimeError("drive is down")
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        conn = drive_service.get_connection(self.user.id)
        self.assertIn("drive is down", conn.last_error)

    def test_upload_happens_when_enabled(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.drive.created_file_names()), 1)
        state = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        self.assertIsNotNone(state.drive_file_id)
        self.assertIsNotNone(state.synced_at)


# ---------------------------------------------------------------------------
# Folder taxonomy
# ---------------------------------------------------------------------------

class TestFolderTaxonomy(DriveTestCase):
    def test_nested_folders_created_once(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(
            self.drive.created_folder_names(),
            ["HoopsLab", "Test Team", "Trainings"],
        )

    def test_folders_reused_on_second_sync(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        first_lists = len(self.drive.list_calls)
        self.client.get(f"/trainings/{ts.id}/pdf")
        # Second sync hits the folder cache: no extra list calls at all.
        self.assertEqual(len(self.drive.list_calls), first_lists)
        self.assertEqual(
            self.drive.created_folder_names().count("Trainings"), 1)

    def test_team_name_with_slash_does_not_create_extra_folder(self):
        self.team.name = "Rivals / Juniors"
        db.session.commit()
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        names = self.drive.created_folder_names()
        self.assertIn("Rivals - Juniors", names)
        # Exactly three levels; the "/" must not become a fourth.
        self.assertEqual(len(names), 3)

    def test_unicode_team_name_preserved(self):
        self.team.name = "Fernández U18"
        db.session.commit()
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertIn("Fernández U18", self.drive.created_folder_names())

    def test_folder_cache_persisted_on_connection(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        conn = drive_service.get_connection(self.user.id)
        cache = json.loads(conn.folder_cache)
        self.assertIn(f"trainings:{self.team.id}", cache)

    def test_regenerated_filenames_are_drive_safe(self):
        ts = self.make_session(title="Pick & Roll: 60/40")
        self.enable_prefs(auto_upload=True, trainings=True)
        self.client.get(f"/trainings/{ts.id}/pdf")
        name = self.drive.created_file_names()[0]
        self.assertTrue(name.endswith(".pdf"))
        self.assertNotIn("/", name)
        self.assertNotIn(":", name)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

class TestReExportIsIdempotent(DriveTestCase):
    def test_second_export_updates_in_place(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        state = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        first_id = state.drive_file_id
        self.assertEqual(len(self.drive.create_calls), 4)  # 3 folders + 1 file

        self.client.get(f"/trainings/{ts.id}/pdf")
        # No new file created; the existing one was updated.
        self.assertEqual(len(self.drive.created_file_names()), 1)
        self.assertEqual(self.drive.update_calls, [first_id])
        self.assertEqual(state.drive_file_id, first_id)

    def test_team_name_snapshot_recorded(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        state = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        self.assertEqual(state.team_name, "Test Team")

    def test_deleted_drive_file_is_recreated(self):
        # If the user deleted the file, a 404 must fall back to create rather
        # than fail forever.
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        state = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        self.drive.update_404.add(state.drive_file_id)
        self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(len(self.drive.created_file_names()), 2)

    def test_media_uploaded_never_written_to_disk(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        # Bytes are handed straight to Drive: exactly one upload, carrying the
        # PDF itself. Nothing was staged on disk.
        self.assertEqual(len(self.drive.media_bodies), 1)
        media = self.drive.media_bodies[0]
        self.assertEqual(media.getbytes(0, media.size()), b"%PDF-1.4 fake")
        self.assertTrue(media.resumable)


# ---------------------------------------------------------------------------
# Explicit "Save to Drive"
# ---------------------------------------------------------------------------

class TestExplicitSaveToDrive(DriveTestCase):
    def test_works_with_auto_upload_off(self):
        # force=True bypasses the toggle; this is the button's whole purpose.
        self.make_connection(auto_upload=False)
        ts = self.make_session()
        resp = self.client.post(f"/trainings/{ts.id}/pdf/drive",
                                follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.drive.created_file_names()), 1)
        self.assertIsNotNone(drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id))

    def test_prompts_to_connect_when_not_linked(self):
        ts = self.make_session()
        resp = self.client.post(f"/trainings/{ts.id}/pdf/drive",
                                follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Connect Google Drive", resp.data)
        self.assertEqual(self.drive.create_calls, [])

    def test_is_post_only(self):
        self.make_connection()
        ts = self.make_session()
        self.assertEqual(
            self.client.get(f"/trainings/{ts.id}/pdf/drive").status_code, 405)

    def test_failure_flashes_error_and_redirects(self):
        self.make_connection()
        self.get_service.side_effect = RuntimeError("nope")
        ts = self.make_session()
        resp = self.client.post(f"/trainings/{ts.id}/pdf/drive",
                                follow_redirects=True)
        self.assertIn(b"Could not save to Google Drive", resp.data)

    def test_button_shown_only_when_linked(self):
        ts = self.make_session()
        # Assert on the form id, not the label: the string "Save to Drive"
        # also appears in the inline JS.
        self.assertNotIn(b'id="saveDriveForm"', self.client.get(
            f"/trainings/{ts.id}").data)
        self.make_connection()
        self.assertIn(b'id="saveDriveForm"', self.client.get(
            f"/trainings/{ts.id}").data)

    def test_drive_route_renders_the_pdf(self):
        # Both paths go through _build_session_pdf, so the Drive copy and the
        # download can never drift apart.
        self.make_connection()
        ts = self.make_session()
        self.client.post(f"/trainings/{ts.id}/pdf/drive")
        # Rendered exactly once, and the bytes handed straight to Drive.
        self.assertEqual(self.pdf_mock.write_pdf.call_count, 1)
        self.assertEqual(len(self.drive.media_bodies), 1)


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation(DriveTestCase):
    def test_drive_route_404s_for_other_teams_team(self):
        other_org = Organization(name="Other Org", slug="other-org")
        db.session.add(other_org)
        db.session.flush()
        other_team = Team(name="Other Team", organization_id=other_org.id,
                          slug="other-team")
        db.session.add(other_team)
        db.session.commit()
        foreign = TrainingSession(
            team_id=other_team.id, title="Secret", session_date="2026-01-01")
        db.session.add(foreign)
        db.session.commit()

        self.make_connection()
        self.assertEqual(
            self.client.get(f"/trainings/{foreign.id}/pdf").status_code, 404)
        self.assertEqual(
            self.client.post(f"/trainings/{foreign.id}/pdf/drive").status_code,
            404)
        self.assertEqual(self.drive.create_calls, [])

    def test_never_uses_another_users_connection(self):
        self.make_connection(auto_upload=True)
        db.session.add(GoogleDriveDocPref(
            user_id=self.user.id, doc_type="trainings", enabled=True))
        db.session.commit()

        other = User(username="u2", email="u2@example.com",
                     organization_id=self.user.organization_id)
        other.set_password("password")
        db.session.add(other)
        db.session.commit()

        # A second user's session with no connection of their own.
        with self.app.test_request_context():
            self.assertFalse(drive_service.auto_upload_enabled(other.id, "trainings"))
            self.assertTrue(
                drive_service.auto_upload_enabled(self.user.id, "trainings"))


# ---------------------------------------------------------------------------
# Credential lifecycle
# ---------------------------------------------------------------------------

class TestCredentialLifecycle(DriveTestCase):
    def test_undecryptable_token_marks_needs_reauth(self):
        conn = self.make_connection()
        conn.refresh_token_enc = "not-valid-ciphertext"
        conn.status = GoogleDriveConnection.STATUS_ACTIVE
        db.session.commit()

        with self.assertRaises(drive_service.DriveSyncError):
            drive_service._refresh_credentials(self.user.id)
        conn = drive_service.get_connection(self.user.id)
        self.assertEqual(conn.status,
                         GoogleDriveConnection.STATUS_NEEDS_REAUTH)

    def test_refresh_error_marks_needs_reauth(self):
        from google.auth.exceptions import RefreshError
        conn = self.make_connection()
        conn.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()
        with mock.patch(
            "google.oauth2.credentials.Credentials.refresh",
            side_effect=RefreshError("invalid_grant"),
        ):
            with self.assertRaises(drive_service.DriveSyncError):
                drive_service._refresh_credentials(self.user.id)
        self.assertEqual(
            drive_service.get_connection(self.user.id).status,
            GoogleDriveConnection.STATUS_NEEDS_REAUTH)

    def test_expired_token_is_refreshed_proactively(self):
        conn = self.make_connection()
        conn.expires_at = datetime.utcnow() + timedelta(seconds=5)
        db.session.commit()
        with mock.patch(
            "google.oauth2.credentials.Credentials.refresh"
        ) as refresh:
            drive_service._refresh_credentials(self.user.id)
        # Within the skew window, so refreshed before the call rather than
        # waiting for a 401.
        self.assertTrue(refresh.called)

    def test_fresh_token_is_not_refreshed(self):
        conn = self.make_connection()
        conn.expires_at = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        with mock.patch(
            "google.oauth2.credentials.Credentials.refresh"
        ) as refresh:
            drive_service._refresh_credentials(self.user.id)
        self.assertFalse(refresh.called)

    def test_inactive_connection_refused(self):
        conn = self.make_connection()
        conn.status = GoogleDriveConnection.STATUS_NEEDS_REAUTH
        db.session.commit()
        with self.assertRaises(drive_service.DriveSyncError):
            drive_service._refresh_credentials(self.user.id)

    def test_scope_is_drive_file_only(self):
        # Broadening this silently would trigger Google verification review.
        self.assertEqual(
            drive_service.SCOPES,
            ["https://www.googleapis.com/auth/drive.file"],
        )


# ---------------------------------------------------------------------------
# Token exchange (regression: Credentials has no fetch_token)
# ---------------------------------------------------------------------------

class TestTokenExchange(DriveTestCase):
    """The link flow must actually work.

    An earlier revision called ``Credentials.fetch_token``, which does not
    exist — every link attempt raised AttributeError. These tests drive the
    real code path with only the HTTP exchange faked.
    """

    def _fake_creds(self, refresh_token="rt-123", token="at-456"):
        creds = mock.MagicMock()
        creds.refresh_token = refresh_token
        creds.token = token
        creds.expiry = None
        return creds

    def _patch_flow(self, creds, fetch_side_effect=None):
        """Fake both halves of connect(): the token exchange and the client.

        A MagicMock credentials object cannot drive a real googleapiclient
        build (it fails universe-domain validation), so _build_service is
        stubbed alongside the flow.
        """
        flow = mock.MagicMock()
        flow.credentials = creds
        if fetch_side_effect is not None:
            flow.fetch_token.side_effect = fetch_side_effect
        stack = contextlib.ExitStack()
        stack.enter_context(
            mock.patch.object(drive_service, "_build_flow", return_value=flow))
        stack.enter_context(
            mock.patch.object(drive_service, "_build_service",
                              return_value=self.drive))
        self.addCleanup(stack.close)
        return flow

    def test_successful_exchange_stores_encrypted_connection(self):
        with self._patch_flow(self._fake_creds()):
            conn = drive_service.connect(self.user.id, "auth-code")
        self.assertIsNotNone(conn)
        row = drive_service.get_connection(self.user.id)
        self.assertEqual(row.status, GoogleDriveConnection.STATUS_ACTIVE)
        self.assertEqual(drive_service.decrypt_token(row.refresh_token_enc), "rt-123")
        # Token must never be readable straight out of the column.
        self.assertNotIn("rt-123", row.refresh_token_enc)
        self.assertEqual(row.scopes, " ".join(drive_service.SCOPES))

    def test_exchange_uses_the_flow_not_credentials_fetch_token(self):
        flow = self._patch_flow(self._fake_creds())
        drive_service.connect(self.user.id, "auth-code")
        flow.fetch_token.assert_called_once_with(code="auth-code")

    def test_credentials_class_really_lacks_fetch_token(self):
        # Guards the original bug directly, so a future refactor back to
        # Credentials.fetch_token fails here rather than in production.
        from google.oauth2.credentials import Credentials

        self.assertFalse(hasattr(Credentials, "fetch_token"))

    def test_rejected_code_raises_drive_sync_error(self):
        with self._patch_flow(self._fake_creds(),
                             fetch_side_effect=ValueError("bad code")):
            with self.assertRaises(drive_service.DriveSyncError):
                drive_service.connect(self.user.id, "bad")
        self.assertIsNone(drive_service.get_connection(self.user.id))

    def test_missing_refresh_token_reports_clearly(self):
        # Happens when a user revoked the grant and re-consents oddly.
        with self._patch_flow(self._fake_creds(refresh_token=None)):
            with self.assertRaises(drive_service.DriveSyncError) as ctx:
                drive_service.connect(self.user.id, "auth-code")
        self.assertIn("refresh token", str(ctx.exception).lower())
        self.assertIsNone(drive_service.get_connection(self.user.id))

    def test_flow_built_with_configured_client_and_redirect(self):
        flow = drive_service._build_flow()
        # from_client_config flattens the "web" section away.
        self.assertEqual(flow.client_config["client_id"],
                         self.app.config["GOOGLE_DRIVE_CLIENT_ID"])
        self.assertEqual(flow.client_config["client_secret"],
                         self.app.config["GOOGLE_DRIVE_CLIENT_SECRET"])
        self.assertEqual(flow.client_config["token_uri"],
                         drive_service.TOKEN_ENDPOINT)
        self.assertEqual(
            flow.client_config["redirect_uris"], [drive_service.redirect_uri()]
        )
        self.assertEqual(flow.redirect_uri, drive_service.redirect_uri())

    def test_relink_clears_folder_cache(self):
        conn = self.make_connection()
        conn.root_folder_id = "old-root"
        conn.folder_cache = json.dumps({"trainings:1": "old-leaf"})
        db.session.commit()
        with self._patch_flow(self._fake_creds()):
            drive_service.connect(self.user.id, "auth-code")
        conn = drive_service.get_connection(self.user.id)
        # Stale ids must not survive a re-link: the tree is resolved afresh.
        self.assertNotEqual(conn.root_folder_id, "old-root")
        cached = json.loads(conn.folder_cache or "{}")
        self.assertNotIn("old-leaf", cached.values())


# ---------------------------------------------------------------------------
# Per-user sync state (regression: two coaches must not fight over one row)
# ---------------------------------------------------------------------------

class TestPerUserSyncState(DriveTestCase):
    def _second_user(self):
        other = User(username="coach2", email="coach2@example.com",
                     organization_id=self.user.organization_id)
        other.set_password("password")
        db.session.add(other)
        db.session.flush()  # populate other.id for the assignment
        db.session.add(TeamAssignment(user_id=other.id, team_id=self.team.id))
        db.session.commit()
        return other

    def test_state_is_not_stored_on_the_shared_artefact(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertFalse(hasattr(ts, "drive_file_id"))
        state = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        self.assertIsNotNone(state)

    def test_two_coaches_get_independent_file_ids(self):
        other = self._second_user()
        for user_id in (self.user.id, other.id):
            db.session.add(GoogleDriveConnection(
                user_id=user_id,
                refresh_token_enc=drive_service.encrypt_token("rt"),
                token_uri=drive_service.TOKEN_ENDPOINT,
                status=GoogleDriveConnection.STATUS_ACTIVE,
                auto_upload=True,
            ))
            db.session.add(GoogleDriveDocPref(
                user_id=user_id, doc_type="trainings", enabled=True))
        db.session.commit()

        ts = self.make_session()
        # Each coach exports the same session, in their own session.
        self.client.get(f"/trainings/{ts.id}/pdf")
        self._login_as(other)
        self.client.get(f"/trainings/{ts.id}/pdf")

        a = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        b = drive_service.get_sync_state(
            other.id, "trainings", "training_session", ts.id)
        self.assertIsNotNone(a, "first coach has no sync state")
        self.assertIsNotNone(b, "second coach has no sync state")
        # Distinct rows, distinct file ids: each tracks the copy in
        # their own Drive. Two files exist in total.
        self.assertNotEqual(a.id, b.id)
        self.assertNotEqual(a.drive_file_id, b.drive_file_id)
        self.assertEqual(len(self.drive.created_file_names()), 2)

    def test_one_users_state_never_leaks_into_anothers_upload(self):
        other = self._second_user()
        db.session.add(GoogleDriveConnection(
            user_id=other.id,
            refresh_token_enc=drive_service.encrypt_token("rt"),
            token_uri=drive_service.TOKEN_ENDPOINT,
            status=GoogleDriveConnection.STATUS_ACTIVE,
            auto_upload=True,
        ))
        db.session.add(GoogleDriveDocPref(
            user_id=other.id, doc_type="trainings", enabled=True))
        db.session.commit()

        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        mine = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id).drive_file_id

        updates_before = len(self.drive.update_calls)
        # Coach 2 exports *as themselves*: must create their own copy,
        # never update mine.
        self._login_as(other)
        self.client.post(f"/trainings/{ts.id}/pdf/drive")
        self.assertEqual(len(self.drive.update_calls), updates_before)
        theirs = drive_service.get_sync_state(
            other.id, "trainings", "training_session", ts.id).drive_file_id
        self.assertIsNotNone(theirs)
        self.assertNotEqual(theirs, mine)


# ---------------------------------------------------------------------------
# Stale folder cache (regression: user deletes a folder in Drive)
# ---------------------------------------------------------------------------

class TestStaleFolderCache(DriveTestCase):
    def test_deleted_folder_cache_is_invalidated_and_rebuilt(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        conn = drive_service.get_connection(self.user.id)
        stale_root = conn.root_folder_id
        self.assertIsNotNone(conn.folder_cache)
        first_folders = list(self.drive.created_folder_names())

        # The user deletes the whole tree in Drive. The DB cache still points
        # at the old ids, so the next upload hits a deleted parent (404), and
        # the service must forget the path and rebuild it.
        self.drive.reset_folders()
        self.client.get(f"/trainings/{ts.id}/pdf")

        conn = drive_service.get_connection(self.user.id)
        self.assertNotEqual(conn.root_folder_id, stale_root)
        # The path was rebuilt from scratch.
        self.assertEqual(
            self.drive.created_folder_names()[len(first_folders):],
            ["HoopsLab", "Test Team", "Trainings"],
        )
        state = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id)
        self.assertIsNotNone(state.drive_file_id)

    def test_upload_succeeds_after_folder_deletion(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        before = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id).drive_file_id
        # reset_folders wipes the fake tree, as deleting a folder in Drive
        # destroys its contents too.
        self.drive.reset_folders()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        # A brand-new file in a rebuilt tree, not the deleted one and not a
        # silent failure. One failed create into the deleted folder is
        # expected on the way there — that is what triggers the rebuild.
        after = drive_service.get_sync_state(
            self.user.id, "trainings", "training_session", ts.id).drive_file_id
        self.assertIsNotNone(after)
        self.assertNotEqual(after, before)
        self.assertEqual(len(self.drive.file_records), 1)


# ---------------------------------------------------------------------------
# Total time budget (regression: gunicorn kills workers at 120s)
# ---------------------------------------------------------------------------

class TestTimeBudget(DriveTestCase):
    def test_default_budget_is_well_under_the_worker_timeout(self):
        # gunicorn_config.py: timeout = 120
        self.assertLess(drive_service._total_timeout(), 120)

    def test_deadline_aborts_before_any_drive_call(self):
        drive_service._start_budget(seconds=-1)
        self.addCleanup(drive_service._clear_budget)
        with self.assertRaises(drive_service.DriveTimeout):
            drive_service._check_deadline()

    def test_retry_helper_respects_the_deadline(self):
        drive_service._start_budget(seconds=-1)
        self.addCleanup(drive_service._clear_budget)
        called = []

        def op():
            called.append(1)
            raise drive_service.DriveTimeout("budget gone")

        with self.assertRaises(drive_service.DriveTimeout):
            drive_service._with_retry(op, attempts=3)
        self.assertEqual(called, [])  # never even attempted

    def test_budget_is_cleared_after_a_sync(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        # A leaked deadline would poison the next unrelated request.
        self.assertIsNone(drive_service._remaining_budget())

    def test_timeout_does_not_break_the_download(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        self.app.config["GOOGLE_DRIVE_TOTAL_TIMEOUT"] = "0"
        ts = self.make_session()
        resp = self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"%PDF-1.4 fake")

    def test_httplib2_timeout_is_capped_by_remaining_budget(self):
        self.app.config["GOOGLE_DRIVE_IO_TIMEOUT"] = "600"
        self.app.config["GOOGLE_DRIVE_CONNECT_TIMEOUT"] = "600"
        drive_service._start_budget(seconds=5)
        self.addCleanup(drive_service._clear_budget)
        creds = mock.MagicMock()
        with mock.patch("httplib2.Http") as http_cls, \
                mock.patch("google_auth_httplib2.AuthorizedHttp"), \
                mock.patch("googleapiclient.discovery.build"):
            drive_service._build_service(creds)
        self.assertLessEqual(http_cls.call_args.kwargs["timeout"], 5)


# ---------------------------------------------------------------------------
# Unicode filenames (regression: secure_filename mangled the Drive name)
# ---------------------------------------------------------------------------


    def test_budgets_are_isolated_between_threads(self):
        # gunicorn runs with threads = 2: two concurrent exports must not
        # share (or clear) each other's deadline.
        import threading

        drive_service._start_budget(seconds=60)
        seen = {}

        def other_thread():
            drive_service._start_budget(seconds=-1)
            try:
                seen["other"] = "expired"
                drive_service._check_deadline()
            except drive_service.DriveTimeout:
                seen["other"] = "expired"
            finally:
                drive_service._clear_budget()

        t = threading.Thread(target=other_thread)
        t.start()
        t.join()
        self.assertEqual(seen["other"], "expired")
        # The other thread's expiry and cleanup must not touch ours.
        drive_service._check_deadline()  # must not raise
        drive_service._clear_budget()

class TestUnicodeFilenames(DriveTestCase):
    def test_drive_name_keeps_non_ascii_title(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session(title="Pick & Roll — Fernàndez")
        self.client.get(f"/trainings/{ts.id}/pdf")
        name = self.drive.created_file_names()[0]
        self.assertIn("Fernàndez", name)

    def test_drive_name_built_from_raw_title_not_the_http_header_name(self):
        ts = self.make_session(title="Fernàndez")
        # The HTTP download name is ASCII-only by design...
        from web.routes.training import _drive_doc_name
        download_name = drive_service.sanitize_filename(
            f"Training_{ts.session_date}_{ts.title}")
        # ...but the Drive name must not be derived from it.
        self.assertEqual(_drive_doc_name(ts),
                         f"Training_{ts.session_date}_Fernàndez.pdf")
        self.assertNotEqual(_drive_doc_name(ts), download_name + ".pdf")
