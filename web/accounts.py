"""Multi-account sign-in: remember several logins in one browser, switch freely.

Why this is not just "more users in the session"
-------------------------------------------------
Flask's session cookie already carries one ``_user_id`` and expires with
``PERMANENT_SESSION_LIFETIME`` (one hour). Stuffing several identities into
that cookie would force the cookie to live as long as the *slowest* identity,
so the short-lived active session would silently become a month-long one.

So the two lifetimes are kept apart:

* ``session``  -- the *active* identity. Unchanged: 1 hour, HttpOnly, signed.
* ``hs_accounts`` -- a second, long-lived cookie holding opaque tokens for
  every identity this browser remembers. 30 days.

Switching therefore costs one cookie write plus one indexed DB lookup, and
never re-runs the login flow.

The ``hs_accounts`` cookie is deliberately NOT signed. It is a bearer
reference, not an assertion: every value in it is a 256-bit random token
whose SHA-256 must exist and be unrevoked in ``account_tokens`` before it
grants anything. A tampered cookie can only ever *remove* an account, never
forge one, so signing would add no integrity while making the tokens
readable base64 in the browser anyway.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from flask import current_app, g, has_request_context, request
from core.models import AccountToken, User, db

# Cookie carrying the remembered identities for this browser.
ACCOUNTS_COOKIE = "hs_accounts"

# Cap the list so a shared machine cannot accumulate unbounded tokens.
MAX_REMEMBERED_ACCOUNTS = 8

# Fallback when the configured cookie lifetime is missing or malformed. Kept
# as a constant (rather than raising) because this runs in an
# ``after_request`` hook, where an exception would 500 every response.
DEFAULT_COOKIE_MAX_AGE = 2592000  # 30 days


def _cookie_max_age() -> int:
    """Configured ``hs_accounts`` lifetime, defensively parsed.

    ``config`` already normalises the env var with ``_env_int``, but the app
    config value can still be overridden with a stray string at runtime
    (tests, shells). Never let that 500 the response.
    """
    try:
        return int(current_app.config.get(
            "ACCOUNT_SWITCH_COOKIE_MAX_AGE", DEFAULT_COOKIE_MAX_AGE))
    except (TypeError, ValueError):
        return DEFAULT_COOKIE_MAX_AGE

# How stale ``last_used_at`` may get before we bother writing it again, so
# browsing does not turn into a DB write per request.
_LAST_USED_REFRESH = timedelta(hours=1)


def hash_token(raw: str) -> str:
    """Stable hash of a raw account token (never store the raw value)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _accounting_disabled() -> bool:
    return bool(current_app.config.get("LOGIN_DISABLED"))


# ---------------------------------------------------------------------------
# Cookie plumbing
#
# Mutations record the desired cookie value on ``g``; ``flush_account_cookie``
# (wired as an ``after_request`` hook) writes it. Doing it this way means a
# route can forget an account and still return a redirect, which a
# ``before_request`` hook could not do.
# ---------------------------------------------------------------------------

def _read_cookie() -> list[str]:
    raw = request.cookies.get(ACCOUNTS_COOKIE)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    # Only well-formed strings are meaningful; anything else is discarded.
    return [t for t in parsed if isinstance(t, str) and t]


def _write_cookie(tokens: list[str]) -> None:
    """Stage a cookie write for the end of the request."""
    g._hs_account_tokens = tokens
    # Any listing computed earlier this request is now stale; drop it so a
    # later read in the same request re-resolves against the new cookie.
    g.pop("_hs_remembered_accounts", None)


def flush_account_cookie(response):
    """``after_request`` hook: apply any staged account-cookie change."""
    if not has_request_context():
        return response
    tokens = g.pop("_hs_account_tokens", None)
    if tokens is None:
        return response
    if _accounting_disabled():
        return response
    if tokens:
        response.set_cookie(
            ACCOUNTS_COOKIE,
            json.dumps(tokens),
            max_age=_cookie_max_age(),
            httponly=True,
            secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
            samesite="Lax",
            path="/",
        )
    else:
        response.delete_cookie(ACCOUNTS_COOKIE, path="/")
    return response


def _cookie_tokens() -> list[str]:
    """Current token list, honouring anything staged earlier this request."""
    staged = g.get("_hs_account_tokens", None)
    if staged is not None:
        return staged
    return _read_cookie()


# ---------------------------------------------------------------------------
# Minting and revoking
# ---------------------------------------------------------------------------

def _device_hint() -> str | None:
    if not has_request_context():
        return None
    ua = (request.user_agent.string or "").strip()
    return ua[:120] or None


def mint_account_token(user: User) -> str:
    """Create a fresh remembered-login token for ``user`` and return it raw.

    The caller is responsible for adding the raw value to the cookie; the
    database only ever sees the hash.
    """
    raw = secrets.token_urlsafe(32)
    db.session.add(
        AccountToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            device_hint=_device_hint(),
        )
    )
    db.session.commit()
    return raw


def remember_account(user: User) -> str | None:
    """Ensure this browser holds a live token for ``user``; return the raw one.

    Idempotent: re-logging into an account already remembered reuses its
    existing token instead of piling up duplicates.
    """
    if _accounting_disabled():
        return None
    tokens = _cookie_tokens()
    hashes = {hash_token(t) for t in tokens}

    existing = (
        AccountToken.query.filter(
            AccountToken.user_id == user.id,
            AccountToken.revoked_at.is_(None),
            AccountToken.token_hash.in_(hashes),
        ).first()
        if hashes
        else None
    )
    if existing:
        _touch(existing)
        return next(t for t in tokens if hash_token(t) == existing.token_hash)

    # Drop entries that no longer resolve (revoked, deleted or deactivated
    # user) BEFORE the cap check: otherwise a cookie full of stale tokens
    # would evict the one live login and force its owner to re-authenticate
    # for no reason. Login-only path, so per-token resolution is fine.
    tokens = [t for t in tokens if resolve_token(t) is not None]
    hashes = {hash_token(t) for t in tokens}

    if len(tokens) >= MAX_REMEMBERED_ACCOUNTS:
        # Drop the oldest remembered login to make room rather than growing
        # the cookie without bound. ``id`` breaks ties when several rows
        # share a timestamp, so eviction is deterministic.
        oldest = (
            AccountToken.query.filter(
                AccountToken.token_hash.in_(list(hashes)),
                AccountToken.revoked_at.is_(None),
            )
            .order_by(AccountToken.last_used_at.asc(), AccountToken.id.asc())
            .first()
        )
        if oldest:
            oldest.revoked_at = datetime.utcnow()
            db.session.commit()
            tokens = [t for t in tokens if hash_token(t) != oldest.token_hash]

    raw = mint_account_token(user)
    tokens.append(raw)
    _write_cookie(tokens)
    return raw


def _touch(record: AccountToken) -> None:
    """Refresh ``last_used_at``, throttled to avoid a write per request."""
    now = datetime.utcnow()
    if record.last_used_at and now - record.last_used_at < _LAST_USED_REFRESH:
        return
    record.last_used_at = now
    db.session.commit()



def forget_all_accounts() -> int:
    """Revoke every login this browser remembers. Returns how many."""
    tokens = _cookie_tokens()
    if not tokens:
        _write_cookie([])
        return 0
    revoked = (
        AccountToken.query.filter(
            AccountToken.token_hash.in_([hash_token(t) for t in tokens]),
            AccountToken.revoked_at.is_(None),
        ).all()
    )
    now = datetime.utcnow()
    for record in revoked:
        record.revoked_at = now
    db.session.commit()
    _write_cookie([])
    return len(revoked)


def resolve_token(raw: str) -> tuple[AccountToken, User] | None:
    """Map a raw cookie token to its live (record, user) pair, or None."""
    if not raw:
        return None
    record = (
        AccountToken.query.filter_by(token_hash=hash_token(raw))
        .filter(AccountToken.revoked_at.is_(None))
        .first()
    )
    if record is None:
        return None
    # An inactive or deleted user must not stay switchable.
    user = db.session.get(User, record.user_id)
    if user is None or not user.is_active:
        return None
    return record, user



def _remembered_hashes() -> set[str]:
    return {hash_token(t) for t in _cookie_tokens()}


def remembered_record(token_id) -> AccountToken | None:
    """The live token row ``token_id`` refers to, if THIS browser holds it.

    This is the authorisation check for switching and removing accounts. The
    forms submit the row id rather than the token itself, so the raw secret
    never leaves the HttpOnly cookie -- possession of a valid row id is
    useless without the matching cookie entry.
    """
    if token_id is None:
        return None
    try:
        token_id = int(token_id)
    except (TypeError, ValueError):
        return None
    record = db.session.get(AccountToken, token_id)
    if record is None or record.revoked_at is not None:
        return None
    if record.token_hash not in _remembered_hashes():
        return None
    user = db.session.get(User, record.user_id)
    if user is None or not user.is_active:
        return None
    return record


def _raw_token_for_hash(token_hash: str) -> str | None:
    for raw in _cookie_tokens():
        if hash_token(raw) == token_hash:
            return raw
    return None


def forget_record(record: AccountToken) -> None:
    """Revoke a token row and strip its raw value from the cookie."""
    raw = _raw_token_for_hash(record.token_hash)
    record.revoked_at = datetime.utcnow()
    db.session.commit()
    if raw is not None:
        _write_cookie([t for t in _cookie_tokens() if t != raw])


def list_remembered_accounts() -> list[dict]:
    """Every live login this browser holds, in cookie order.

    Stale entries (revoked, deleted user, deactivated) are pruned from the
    cookie as a side effect so a revoked token cannot linger client-side.

    Resolved in two batched queries (token rows, then users) no matter how
    many tokens the cookie holds, and cached on ``g`` so the context
    processor, the menu, and the logout path share one resolution per
    request instead of re-querying.
    """
    cached = g.get("_hs_remembered_accounts", None)
    if cached is not None:
        return cached

    tokens = _cookie_tokens()
    if not tokens:
        g._hs_remembered_accounts = []
        return []

    token_hashes = [hash_token(t) for t in tokens]
    records = (
        AccountToken.query.filter(
            AccountToken.token_hash.in_(token_hashes),
            AccountToken.revoked_at.is_(None),
        ).all()
    )
    by_hash = {r.token_hash: r for r in records}
    users = (
        {
            u.id: u
            for u in User.query.filter(
                User.id.in_([r.user_id for r in records])
            ).all()
        }
        if records
        else {}
    )

    accounts: list[dict] = []
    live_tokens: list[str] = []
    seen: set[int] = set()
    for raw, token_hash in zip(tokens, token_hashes):
        record = by_hash.get(token_hash)
        if record is None:
            continue
        user = users.get(record.user_id)
        if user is None or not user.is_active:
            continue
        live_tokens.append(raw)
        # One entry per account even if the cookie somehow holds two tokens
        # for the same user.
        if user.id in seen:
            continue
        seen.add(user.id)
        accounts.append(
            {
                "user": user,
                "record": record,
                "token_id": record.id,
                "device_hint": record.device_hint,
                "last_used_at": record.last_used_at,
            }
        )

    if len(live_tokens) != len(tokens):
        _write_cookie(live_tokens)

    # Refresh activity timestamps, but keep this off the hot path.
    now = datetime.utcnow()
    stale = [
        a["record"]
        for a in accounts
        if not a["record"].last_used_at
        or now - a["record"].last_used_at >= _LAST_USED_REFRESH
    ]
    if stale:
        for record in stale:
            record.last_used_at = now
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    g._hs_remembered_accounts = accounts
    return accounts


def switchable_accounts() -> list[dict]:
    """Template-facing view of the account menu, active account first."""
    from flask_login import current_user

    accounts = list_remembered_accounts()
    current_id = getattr(current_user, "id", None)
    for account in accounts:
        account["is_current"] = account["user"].id == current_id
    accounts.sort(key=lambda a: (not a["is_current"], a["user"].username.lower()))
    return accounts



def purge_user_tokens(user_id: int) -> int:
    """Delete every remembered-login row for a user being removed.

    Called from the admin delete-user action. ``AccountToken.user`` already
    cascades, so this is belt-and-braces for callers that delete the token
    rows explicitly (and makes the intent legible at the call site).
    Token rows have no children, so a bulk delete is safe here.
    """
    deleted = (
        AccountToken.query.filter_by(user_id=user_id)
        .delete(synchronize_session=False)
    )
    if deleted:
        db.session.commit()
    return deleted


def purge_expired_tokens() -> int:
    """Housekeeping: delete token rows revoked or unused for too long."""
    cutoff = datetime.utcnow() - timedelta(days=90)
    deleted = (
        AccountToken.query.filter(
            db.or_(
                AccountToken.revoked_at.isnot(None),
                AccountToken.last_used_at < cutoff,
            )
        ).delete(synchronize_session=False)
    )
    if deleted:
        db.session.commit()
    return deleted


def remembered_record_id_for(user_id: int) -> int | None:
    """Token row id backing the currently active user, if this browser has it."""
    for account in list_remembered_accounts():
        if account["user"].id == user_id:
            return account["record"].id
    return None

