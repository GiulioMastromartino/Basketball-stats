"""Google Drive export sync: per-user OAuth, nested folders, resumable upload.

Each user links their own Google account; exported artefacts land in a nested
folder tree in *their* Drive::

    <root>/<Team name>/<doc-type folder>/<file>.pdf

Design notes worth keeping in mind when editing:

* **No PDF is ever persisted on the server.** Callers pass bytes already in
  memory (e.g. from WeasyPrint) and we hand them straight to Drive.
* **Drive failures must never break a download.** Every public entry point here
  is non-raising for the auto-upload path; problems are recorded on the
  connection row and surfaced in the settings UI instead.
* **Tokens are encrypted at rest** with Fernet, keyed on
  ``GOOGLE_DRIVE_TOKEN_KEY``. That key is deliberately separate from
  ``SECRET_KEY``. If it is unset the whole feature is disabled — we never fall
  back to plaintext storage.
* **Only the ``drive.file`` scope** is ever requested, so the app can touch
  files it created and nothing else in the user's Drive.
"""

from __future__ import annotations

import json
import re
import secrets
import time
import unicodedata
from datetime import datetime, timedelta

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core.models import db, GoogleDriveConnection, GoogleDriveDocPref
from core.services import drive_sync_types

# drive.file only. Adding a broader scope here would change the app's Google
# risk classification from non-sensitive to restricted, which triggers
# verification review and an annual security audit.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

FOLDER_MIME = "application/vnd.google-apps.folder"
PDF_MIME = "application/pdf"

STATE_MAX_AGE = 600          # seconds; consent round trip should be quick
TOKEN_REFRESH_SKEW = timedelta(seconds=60)
DEFAULT_RETRIES = 3
_RETRYABLE = ("ratelimitexceeded", "userratelimitexceeded", "backenderror",
              "internalerror", "serviceunavailable")


class DriveSyncError(Exception):
    """Raised only by operations the user explicitly asked for.

    Auto-upload callers must use :func:`enqueue_or_upload`, which swallows
    failures; explicit "Save to Drive" actions may surface this.
    """


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

def is_enabled() -> bool:
    """True when Drive sync is fully configured.

    All three secrets are required. A missing token key in particular must not
    degrade to plaintext token storage.
    """
    cfg = current_app.config
    return bool(
        cfg.get("GOOGLE_DRIVE_CLIENT_ID")
        and cfg.get("GOOGLE_DRIVE_CLIENT_SECRET")
        and cfg.get("GOOGLE_DRIVE_TOKEN_KEY")
        and cfg.get("GOOGLE_DRIVE_REDIRECT_URI")
    )


def _require_enabled() -> None:
    if not is_enabled():
        raise DriveSyncError("Google Drive sync is not configured on this server.")


def _root_folder_name() -> str:
    return current_app.config.get("GOOGLE_DRIVE_ROOT_FOLDER") or "HoopsLab"


def redirect_uri() -> str:
    """Configured redirect URI.

    Read from config, never from the incoming request: in production TLS
    terminates at the Tailscale Funnel, so a request-derived URI would drift
    from what is registered on the OAuth client.
    """
    return current_app.config["GOOGLE_DRIVE_REDIRECT_URI"]


# ---------------------------------------------------------------------------
# Token encryption
# ---------------------------------------------------------------------------

def _fernet():
    from cryptography.fernet import Fernet

    key = current_app.config.get("GOOGLE_DRIVE_TOKEN_KEY")
    if not key:
        raise DriveSyncError("GOOGLE_DRIVE_TOKEN_KEY is not configured.")
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    if not plaintext:
        return None
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str):
    if not ciphertext:
        return None
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        # Wrong key, or the row predates a key rotation. Surface as a re-link
        # rather than crashing: the user can re-consent in one click.
        current_app.logger.warning(
            "Google Drive token could not be decrypted; re-link required."
        )
        return None


# ---------------------------------------------------------------------------
# Signed OAuth state
# ---------------------------------------------------------------------------

def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="gdrive-oauth")


def build_state(user_id: int) -> str:
    """Signed, expiring state token carrying the initiating user id.

    Deliberately not stored in the session: the callback must stay safe even
    if the session cookie is lost across the Google redirect.
    """
    return _serializer().dumps({"uid": int(user_id), "n": secrets.token_urlsafe(16)})


def verify_state(state: str):
    """Return the user id encoded in ``state``, or None if it is not valid.

    Callers must additionally compare the returned id against the currently
    authenticated user before consuming the code.
    """
    if not state:
        return None
    try:
        data = _serializer().loads(state, max_age=STATE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Connection CRUD
# ---------------------------------------------------------------------------

def get_connection(user_id: int):
    return GoogleDriveConnection.query.filter_by(user_id=user_id).first()


def is_connected(user_id: int) -> bool:
    conn = get_connection(user_id)
    return bool(conn and conn.is_active)


def set_doc_pref(user_id: int, doc_type: str, enabled: bool) -> None:
    if not drive_sync_types.is_valid_doc_type(doc_type):
        raise DriveSyncError(f"Unknown document type: {doc_type!r}")
    pref = GoogleDriveDocPref.query.filter_by(
        user_id=user_id, doc_type=doc_type
    ).first()
    if pref is None:
        pref = GoogleDriveDocPref(user_id=user_id, doc_type=doc_type)
        db.session.add(pref)
    pref.enabled = bool(enabled)
    db.session.commit()


def save_prefs(user_id: int, auto_upload: bool, doc_types: dict) -> None:
    """Persist the master switch and per-type toggles in one transaction.

    Unavailable types are ignored: they are not wired up yet, and a
    hand-crafted POST must not be able to enable them.
    """
    conn = get_connection(user_id)
    if conn is None:
        raise DriveSyncError("Google Drive is not connected.")
    conn.auto_upload = bool(auto_upload)
    for key, enabled in (doc_types or {}).items():
        if not drive_sync_types.is_available(key):
            continue
        pref = GoogleDriveDocPref.query.filter_by(
            user_id=user_id, doc_type=key
        ).first()
        if pref is None:
            pref = GoogleDriveDocPref(user_id=user_id, doc_type=key)
            db.session.add(pref)
        pref.enabled = bool(enabled)
    db.session.commit()


def get_doc_prefs(user_id: int) -> dict:
    """Map of doc_type -> enabled for every registered type."""
    rows = GoogleDriveDocPref.query.filter_by(user_id=user_id).all()
    stored = {r.doc_type: r.enabled for r in rows}
    return {
        spec["key"]: bool(stored.get(spec["key"], False))
        for spec in drive_sync_types.list_types(include_unavailable=True)
    }


def auto_upload_enabled(user_id: int, doc_type: str) -> bool:
    """True only when linked, master switch on, and this doc type opted in."""
    if not is_enabled():
        return False
    conn = get_connection(user_id)
    if not conn or not conn.is_active or not conn.auto_upload:
        return False
    if not drive_sync_types.is_available(doc_type):
        return False
    pref = GoogleDriveDocPref.query.filter_by(
        user_id=user_id, doc_type=doc_type
    ).first()
    return bool(pref and pref.enabled)


def build_auth_url(state: str) -> str:
    from urllib.parse import urlencode

    params = {
        "client_id": current_app.config["GOOGLE_DRIVE_CLIENT_ID"],
        # redirect_uri is required, and must be byte-identical to the value
        # registered on the OAuth client.
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",
        # Required to obtain a refresh token when a user re-links an account
        # that has already granted access (otherwise Google returns none).
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def connect(user_id: int, code: str):
    """Exchange an authorization code and store the connection.

    Creates the level-1 root folder eagerly so a bad grant fails here, at link
    time, rather than silently on someone's first export.
    """
    _require_enabled()
    from google.oauth2.credentials import Credentials

    cfg = current_app.config
    creds = Credentials(
        token=None,
        refresh_token=None,
        token_uri=TOKEN_ENDPOINT,
        client_id=cfg["GOOGLE_DRIVE_CLIENT_ID"],
        client_secret=cfg["GOOGLE_DRIVE_CLIENT_SECRET"],
    )
    try:
        creds.fetch_token(
            code=code, redirect_uri=redirect_uri(),
            client_secret=cfg["GOOGLE_DRIVE_CLIENT_SECRET"],
        )
    except Exception as exc:
        current_app.logger.warning("Google Drive token exchange failed: %s", exc)
        raise DriveSyncError("Google rejected the authorization code.") from exc

    if not creds.refresh_token:
        # Should not happen with prompt=consent, but a user who previously
        # revoked the grant can produce exactly this.
        raise DriveSyncError(
            "Google did not return a refresh token. Revoke the app's access in "
            "your Google account and try linking again."
        )

    google_email = None
    try:
        from googleapiclient.discovery import build

        probe = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = probe.userinfo().get().execute()
        google_email = info.get("email")
    except Exception:
        # Display-only nicety; never block linking on it.
        google_email = None

    expires_at = None
    if creds.expiry:
        expires_at = creds.expiry.replace(tzinfo=None)

    conn = get_connection(user_id)
    if conn is None:
        conn = GoogleDriveConnection(user_id=user_id)
        db.session.add(conn)
    conn.refresh_token_enc = encrypt_token(creds.refresh_token)
    conn.access_token_enc = encrypt_token(creds.token) if creds.token else None
    conn.token_uri = TOKEN_ENDPOINT
    conn.scopes = " ".join(SCOPES)
    conn.expires_at = expires_at
    conn.google_email = google_email
    conn.status = GoogleDriveConnection.STATUS_ACTIVE
    conn.last_error = None
    # Re-linking means re-resolving folders: the old tree may be gone.
    conn.folder_cache = None
    conn.root_folder_id = None
    db.session.flush()

    try:
        service = _build_service(creds)
        conn.root_folder_id = _find_or_create_folder(
            service, _root_folder_name(), parent_id=None
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.warning("Google Drive root folder creation failed: %s", exc)
        raise DriveSyncError("Could not create the folder in your Drive.") from exc

    db.session.commit()
    return conn


def disconnect(user_id: int) -> None:
    """Remove the connection. Files already in the user's Drive are left alone."""
    conn = get_connection(user_id)
    if conn is None:
        return
    GoogleDriveDocPref.query.filter_by(user_id=user_id).delete()
    db.session.delete(conn)
    db.session.commit()


def mark_needs_reauth(user_id: int, reason: str) -> None:
    conn = get_connection(user_id)
    if conn is None:
        return
    conn.status = GoogleDriveConnection.STATUS_NEEDS_REAUTH
    conn.last_error = reason
    conn.access_token_enc = None
    conn.expires_at = None
    db.session.commit()


def _record_error(user_id: int, message: str) -> None:
    conn = get_connection(user_id)
    if conn is None:
        return
    conn.last_error = message[:1000]
    db.session.commit()


# ---------------------------------------------------------------------------
# Credentials + client
# ---------------------------------------------------------------------------

def _credentials_from_row(conn):
    from google.oauth2.credentials import Credentials

    refresh_token = decrypt_token(conn.refresh_token_enc)
    if not refresh_token:
        return None
    cfg = current_app.config
    access_token = decrypt_token(conn.access_token_enc)
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=conn.token_uri or TOKEN_ENDPOINT,
        client_id=cfg["GOOGLE_DRIVE_CLIENT_ID"],
        client_secret=cfg["GOOGLE_DRIVE_CLIENT_SECRET"],
        scopes=(conn.scopes or " ".join(SCOPES)).split(),
    )


def _refresh_credentials(user_id: int):
    """Return fresh credentials, refreshing proactively and on demand.

    Raises :class:`DriveSyncError` when the grant is unrecoverable so the
    caller can mark the connection for re-linking.
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request

    conn = get_connection(user_id)
    if conn is None or not conn.is_active:
        raise DriveSyncError("Google Drive is not connected.")

    creds = _credentials_from_row(conn)
    if creds is None:
        mark_needs_reauth(user_id, "Stored credentials could not be decrypted.")
        raise DriveSyncError("Stored credentials could not be decrypted.")

    # Proactive refresh: access tokens live ~1h. Avoids a wasted round trip
    # and, more importantly, an avoidable 401 on a user's export.
    stale = (
        conn.expires_at is not None
        and conn.expires_at <= datetime.utcnow() + TOKEN_REFRESH_SKEW
    )
    if creds.expired or stale or not creds.token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            mark_needs_reauth(user_id, f"Google rejected the saved grant: {exc}")
            raise DriveSyncError(
                "Google rejected the saved grant. Please re-link your account."
            ) from exc
        except Exception as exc:
            raise DriveSyncError(f"Token refresh failed: {exc}") from exc
        conn.access_token_enc = encrypt_token(creds.token) if creds.token else None
        conn.expires_at = (
            creds.expiry.replace(tzinfo=None) if creds.expiry else None
        )
        db.session.commit()
    return creds


def _build_service(creds):
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    cfg = current_app.config
    timeout = max(
        int(cfg.get("GOOGLE_DRIVE_CONNECT_TIMEOUT", 30)),
        int(cfg.get("GOOGLE_DRIVE_IO_TIMEOUT", 120)),
    )
    # The timeout goes on the underlying httplib2 handle, not on AuthorizedHttp
    # (which takes no timeout kwarg in google-auth-httplib2 0.4.x). A hung
    # Drive call must not pin a gunicorn worker indefinitely.
    # AuthorizedHttp also refreshes and retries once on a 401 for us, which
    # covers the reactive-refresh case on top of the proactive one in
    # _refresh_credentials.
    http = AuthorizedHttp(creds, http=httplib2.Http(timeout=timeout))
    return build("drive", "v3", http=http, cache_discovery=False)


def _get_service(user_id: int):
    return _build_service(_refresh_credentials(user_id))


def _is_retryable(exc) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in (429, 500, 502, 503, 504):
        return True
    reason = str(exc).lower()
    return any(token in reason for token in _RETRYABLE)


def _with_retry(fn, attempts: int = DEFAULT_RETRIES):
    """Call ``fn`` with exponential backoff on rate-limit/transient errors."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if i == attempts - 1 or not _is_retryable(exc):
                raise
            time.sleep(2 ** i * 0.5)
    raise last


# ---------------------------------------------------------------------------
# Folder resolution
# ---------------------------------------------------------------------------

_ILLEGAL_FOLDER_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_folder_segment(name: str, fallback: str = "Team") -> str:
    """Make a team name safe as a single Drive folder segment.

    Unlike ``werkzeug.utils.secure_filename`` (used for the HTTP download
    header at web/routes/training.py) this keeps unicode intact — Drive handles
    it fine and mangling "Férnandez U18" to "Fernandez-U18" would be a
    regression for the user's own folder tree.
    """
    if not name:
        return fallback
    cleaned = _ILLEGAL_FOLDER_CHARS.sub("-", str(name)).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Strip bidi/control characters that can make a folder name unreadable.
    cleaned = "".join(
        ch for ch in cleaned
        if ch.isprintable() and unicodedata.category(ch) not in ("Cf", "Cc")
    )
    # A name made only of separators ("///") collapses to nothing useful, so
    # fall back rather than creating a folder called "---".
    cleaned = cleaned.strip("-").strip()
    return cleaned[:100] or fallback


def sanitize_filename(name: str, fallback: str = "export.pdf") -> str:
    """Make a file name safe while preserving unicode and the .pdf suffix."""
    cleaned = sanitize_folder_segment(name, fallback=fallback)
    if not cleaned.lower().endswith(".pdf"):
        cleaned = f"{cleaned}.pdf"
    return cleaned[:150]


def _escape_query(value: str) -> str:
    """Escape a literal for a Drive ``q=`` search string."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_or_create_folder(service, name: str, parent_id):
    """Find a child folder by name, creating it when absent.

    Each level is resolved strictly one at a time because the Drive ``q=``
    expression is scoped to a single parent.
    """
    if parent_id is None:
        query = (
            f"name = '{_escape_query(name)}' and "
            f"mimeType = '{FOLDER_MIME}' and trashed = false"
        )
    else:
        query = (
            f"name = '{_escape_query(name)}' and "
            f"'{_escape_query(parent_id)}' in parents and "
            f"mimeType = '{FOLDER_MIME}' and trashed = false"
        )

    found = _with_retry(
        lambda: service.files().list(
            q=query, spaces="drive",
            fields="files(id, name)", pageSize=10, supportsAllDrives=True,
        ).execute()
    )
    files = found.get("files") or []
    if files:
        return files[0]["id"]

    body = {
        "name": name,
        "mimeType": FOLDER_MIME,
        # No parents => My Drive root. Only the leaf level gets a parent.
    }
    if parent_id is not None:
        body["parents"] = [parent_id]
    created = _with_retry(
        lambda: service.files().create(
            body=body, fields="id", supportsAllDrives=True,
        ).execute()
    )
    return created["id"]


def _load_folder_cache(conn) -> dict:
    if not conn.folder_cache:
        return {}
    try:
        data = json.loads(conn.folder_cache)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_folder_path(user_id: int, doc_type: str, team_id, team_name: str) -> str:
    """Find-or-create ``<root>/<team>/<leaf>`` and return the leaf folder id.

    Results are cached per (doc_type, team_id) on the connection row so a
    repeated upload does not pay for two ``files().list()`` round trips.
    """
    spec = drive_sync_types.get_spec(doc_type)
    if not spec:
        raise DriveSyncError(f"Unknown document type: {doc_type!r}")

    conn = get_connection(user_id)
    if conn is None or not conn.is_active:
        raise DriveSyncError("Google Drive is not connected.")

    cache_key = f"{doc_type}:{team_id}"
    cache = _load_folder_cache(conn)

    if cache.get(cache_key) and conn.root_folder_id:
        return cache[cache_key]

    service = _get_service(user_id)
    root_id = conn.root_folder_id
    if not root_id:
        root_id = _find_or_create_folder(service, _root_folder_name(), parent_id=None)
        conn.root_folder_id = root_id

    team_id_drive = _find_or_create_folder(
        service, sanitize_folder_segment(team_name), parent_id=root_id
    )
    leaf_id = _find_or_create_folder(
        service, spec["folder"], parent_id=team_id_drive
    )

    cache[cache_key] = leaf_id
    conn.folder_cache = json.dumps(cache)
    db.session.commit()
    return leaf_id


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def _media_body(data: bytes, filename: str):
    from googleapiclient.http import MediaInMemoryUpload

    return MediaInMemoryUpload(
        data, mimetype=PDF_MIME, resumable=True, chunksize=256 * 1024
    )


def upload_pdf(user_id: int, folder_id: str, filename: str, data: bytes,
               remote_file_id=None) -> str:
    """Create or update a PDF in ``folder_id`` and return its Drive file id.

    When ``remote_file_id`` is known this overwrites in place, so re-exporting
    a training session after an edit does not leave a duplicate behind. If the
    user deleted the file from Drive, the 404 falls back to a fresh create.
    """
    from googleapiclient.errors import HttpError

    service = _get_service(user_id)
    filename = sanitize_filename(filename)

    if remote_file_id:
        try:
            updated = _with_retry(
                lambda: service.files().update(
                    fileId=remote_file_id,
                    media_body=_media_body(data, filename),
                    fields="id", supportsAllDrives=True,
                ).execute()
            )
            return updated["id"]
        except HttpError as exc:
            if getattr(getattr(exc, "resp", None), "status", None) == 404:
                current_app.logger.info(
                    "Drive file %s vanished; recreating.", remote_file_id
                )
            else:
                raise

    created = _with_retry(
        lambda: service.files().create(
            body={"name": filename, "mimeType": PDF_MIME, "parents": [folder_id]},
            media_body=_media_body(data, filename),
            fields="id", supportsAllDrives=True,
        ).execute()
    )
    return created["id"]


def _apply_sync_record(record, file_id: str, team_name: str) -> None:
    if record is None:
        return
    record.drive_file_id = file_id
    record.drive_synced_at = datetime.utcnow()
    record.drive_team_name = (team_name or "")[:100] or None
    db.session.commit()


def enqueue_or_upload(user_id: int, doc_type: str, team, filename: str,
                      data: bytes, record=None, force: bool = False):
    """Best-effort sync used by the auto-upload hook.

    Never raises: a Drive problem must not turn a working PDF download into a
    500. Returns the Drive file id on success, ``None`` otherwise.

    ``force=True`` backs the explicit "Save to Drive" button, which works even
    when auto-upload is off, but still never raises.
    """
    if not is_enabled():
        return None
    if not force and not auto_upload_enabled(user_id, doc_type):
        return None
    if not drive_sync_types.is_available(doc_type):
        return None
    if team is None:
        return None

    conn = get_connection(user_id)
    if conn is None or not conn.is_active:
        return None

    team_id = getattr(team, "id", None)
    team_name = getattr(team, "name", "") or ""
    remote_file_id = getattr(record, "drive_file_id", None) if record else None

    try:
        folder_id = resolve_folder_path(user_id, doc_type, team_id, team_name)
        file_id = upload_pdf(
            user_id, folder_id, filename, data, remote_file_id=remote_file_id
        )
        _apply_sync_record(record, file_id, team_name)
        conn.last_error = None
        db.session.commit()
        current_app.logger.info(
            "Drive sync ok user=%s type=%s team=%s file=%s",
            user_id, doc_type, team_id, file_id,
        )
        return file_id
    except DriveSyncError as exc:
        if "re-link" in str(exc).lower() or "rejected" in str(exc).lower():
            # Already recorded by _refresh_credentials / mark_needs_reauth.
            current_app.logger.warning("Drive sync needs re-auth: %s", exc)
        else:
            _record_error(user_id, str(exc))
        return None
    except Exception as exc:
        # Includes rate limits, quota errors, network faults. Swallowed on
        # purpose: see module docstring.
        current_app.logger.warning("Drive sync failed user=%s: %s", user_id, exc)
        _record_error(user_id, str(exc))
        return None
