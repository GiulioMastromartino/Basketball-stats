"""Tests for per-user Google Drive export sync.

No test here touches the real Drive API. The Drive client is faked at the
``drive_service._get_service`` boundary, mirroring how WeasyPrint is mocked in
tests/conftest.py. ``FakeDriveService`` models folder find-or-create, file
create/update, and fault injection so the behaviour that actually matters
(idempotent re-export, failure isolation, folder caching) is exercised.
"""

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
        matches = [
            {"id": fid} for fid, meta in self.svc.folder_records.items()
            if meta["name"] == name and meta["parents"] == parent
        ]
        return _Exec({"files": matches})

    def create(self, body=None, media_body=None, **kwargs):
        self.svc.create_calls.append(body)
        # Folder creates carry no media; only count real file uploads.
        if media_body is not None:
            self.svc.media_bodies.append(media_body)
        fid = f"id{self.svc.next_id}"
        self.svc.next_id += 1
        if body.get("mimeType") == FOLDER_MIME:
            self.svc.folder_records[fid] = {
                "name": body["name"],
                "parents": (body.get("parents") or [None])[0],
            }
        else:
            self.svc.file_records[fid] = {
                "name": body.get("name"),
                "parents": (body.get("parents") or [None])[0],
            }
        return _Exec({"id": fid})

    def update(self, fileId=None, media_body=None, **kwargs):
        self.svc.update_calls.append(fileId)
        if fileId in self.svc.update_404:
            raise HttpError(
                mock.Mock(status=404, reason="notFound"), b"not found"
            )
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
        self.next_id = 1

    def files(self):
        return _FakeFiles(self)

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
        admin = self.client.get("/admin/settings")
        self.assertIn(b"not configured on this server", admin.data)

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
        resp = self.client.get("/admin/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Connect Google Drive", resp.data)

    def test_settings_shows_disconnect_when_connected(self):
        self.make_connection()
        resp = self.client.get("/admin/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Disconnect", resp.data)
        self.assertNotIn(b"Connect Google Drive", resp.data)


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
        self.assertIsNone(ts.drive_file_id)

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
        self.assertIsNotNone(ts.drive_file_id)
        self.assertIsNotNone(ts.drive_synced_at)


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
        first_id = ts.drive_file_id
        self.assertEqual(len(self.drive.create_calls), 4)  # 3 folders + 1 file

        self.client.get(f"/trainings/{ts.id}/pdf")
        # No new file created; the existing one was updated.
        self.assertEqual(len(self.drive.created_file_names()), 1)
        self.assertEqual(self.drive.update_calls, [first_id])
        self.assertEqual(ts.drive_file_id, first_id)

    def test_team_name_snapshot_recorded(self):
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        self.assertEqual(ts.drive_team_name, "Test Team")

    def test_deleted_drive_file_is_recreated(self):
        # If the user deleted the file, a 404 must fall back to create rather
        # than fail forever.
        self.enable_prefs(auto_upload=True, trainings=True)
        ts = self.make_session()
        self.client.get(f"/trainings/{ts.id}/pdf")
        self.drive.update_404.add(ts.drive_file_id)
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
        self.assertIsNotNone(ts.drive_file_id)

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
