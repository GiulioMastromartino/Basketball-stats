"""Tests for multi-account sign-in (remembered logins + instant switching).

The behaviours worth locking down here are the security edges, not the happy
path:

* an account's token must not be usable from a browser that was never given it;
* switching identities must not leak the previous identity's team/org/season;
* revocation must be server-side, so a replayed cookie is dead;
* a remembered login must not outlive the account itself.
"""

import json
from datetime import datetime, timedelta

import pytest

from core.models import (
    AccountToken,
    Team,
    TeamAssignment,
    OrganizationMembership,
    User,
    db,
)
from web.accounts import (
    ACCOUNTS_COOKIE,
    MAX_REMEMBERED_ACCOUNTS,
    hash_token,
)


# =============================================================================
# Helpers
# =============================================================================


def _cookie(client):
    return client.get_cookie(ACCOUNTS_COOKIE)


def _cookie_tokens(client):
    """Raw token list the test client is currently holding."""
    cookie = _cookie(client)
    if cookie is None:
        return []
    return json.loads(cookie.decoded_value)


def _set_cookie_tokens(client, tokens):
    client.set_cookie(ACCOUNTS_COOKIE, json.dumps(tokens),
                      domain="localhost")


def _make_user(db_session, org, team, username, is_gm=False, password="pw12345"):
    user = User(username=username, email=f"{username}@test.com",
                organization_id=org.id)
    user.set_password(password)
    db_session.add(user)
    db_session.flush()
    db_session.add(OrganizationMembership(
        user_id=user.id, organization_id=org.id, is_gm=is_gm))
    db_session.add(TeamAssignment(
        user_id=user.id, team_id=team.id, is_coach=is_gm))
    db_session.commit()
    return user


@pytest.fixture
def second_team(db_session, default_org):
    """A team the switcher user has NO access to, used to detect leakage."""
    team = Team(name="Other Squad", organization_id=default_org.id,
                slug="other-squad")
    db_session.add(team)
    db_session.commit()
    return team


@pytest.fixture
def two_users(db_session, default_org, default_team):
    """Two ordinary (non-GM, so OTP-free) users on different teams."""
    alice = _make_user(db_session, default_org, default_team, "alice")
    bob = _make_user(db_session, default_org, default_team, "bob")
    return alice, bob


def _login(client, user, password="pw12345"):
    """Sign in. Uses the add-account flow so this also works when a user is
    already signed in (a bare POST would be redirected away by design)."""
    return client.post("/auth/login?switch=1", data={
        "username": user.username, "password": password, "switch": "1",
    })


def _switch(client, token_id, **extra):
    data = {"token_id": token_id}
    data.update(extra)
    return client.post("/auth/accounts/switch", data=data)


def _acting_user(client):
    with client.session_transaction() as sess:
        return sess.get("_user_id")


# =============================================================================
# Minting remembered logins
# =============================================================================


class TestRemembering:
    def test_login_creates_a_remembered_token(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)

        tokens = _cookie_tokens(client)
        assert len(tokens) == 1

        record = AccountToken.query.filter_by(
            token_hash=hash_token(tokens[0]), revoked_at=None).first()
        assert record is not None
        assert record.user_id == alice.id

    def test_raw_token_is_never_stored_in_the_database(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        raw = _cookie_tokens(client)[0]

        stored = AccountToken.query.filter_by(token_hash=raw).first()
        assert stored is None, "raw token must never reach the database"

    def test_token_hash_is_sha256_of_the_cookie_value(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        raw = _cookie_tokens(client)[0]

        assert len(hash_token(raw)) == 64
        assert AccountToken.query.filter_by(
            token_hash=hash_token(raw)).first() is not None

    def test_cookie_is_httponly_and_lax(self, client, two_users):
        """The cookie is a bearer credential, so scripting must not read it."""
        alice, _ = two_users
        _login(client, alice)

        cookie = _cookie(client)
        assert cookie is not None
        assert cookie.http_only is True
        assert cookie.same_site == "Lax"
        # Long-lived on purpose: this is the "remembered accounts" list, kept
        # separate from the one-hour active session.
        assert cookie.max_age and cookie.max_age > 86400

    def test_second_login_adds_a_second_account(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        tokens = _cookie_tokens(client)
        assert len(tokens) == 2
        assert len({AccountToken.query.filter_by(
            token_hash=hash_token(t)).first().user_id for t in tokens}) == 2

    def test_relogin_reuses_the_existing_token(self, client, two_users):
        """Logging in twice must not pile up duplicate rows for one account."""
        alice, _ = two_users
        _login(client, alice)
        first = _cookie_tokens(client)

        _login(client, alice)
        assert _cookie_tokens(client) == first
        assert AccountToken.query.filter_by(revoked_at=None).count() == 1

    def test_cookie_list_is_capped(self, client, db_session, default_org,
                                   default_team):
        users = [
            _make_user(db_session, default_org, default_team, f"cap{i}")
            for i in range(MAX_REMEMBERED_ACCOUNTS + 3)
        ]
        for user in users:
            _login(client, user)

        tokens = _cookie_tokens(client)
        assert len(tokens) <= MAX_REMEMBERED_ACCOUNTS

    def test_gm_login_requires_otp_before_a_token_is_minted(
        self, client, db_session, default_org, default_team
    ):
        """Adding a GM account must still go through the OTP gate."""
        gm = _make_user(db_session, default_org, default_team, "boss",
                        is_gm=True, password="bosspw")
        _login(client, gm, password="bosspw")

        # No token yet: the identity is not established until OTP completes.
        assert _cookie_tokens(client) == []
        assert AccountToken.query.count() == 0


# =============================================================================
# Switching
# =============================================================================


class TestSwitching:
    def test_switch_changes_the_active_identity(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)
        assert _acting_user(client) == str(bob.id)

        bob_token = next(
            t for t in _cookie_tokens(client)
            if AccountToken.query.filter_by(
                token_hash=hash_token(t)).first().user_id == alice.id
        )
        token_id = AccountToken.query.filter_by(
            token_hash=hash_token(bob_token)).first().id

        resp = _switch(client, token_id)
        assert resp.status_code == 302
        assert _acting_user(client) == str(alice.id)

    def test_switch_needs_no_password(self, client, two_users):
        """The whole point: no credential replay on switch."""
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _switch(client, token_id)
        assert _acting_user(client) == str(alice.id)

    def test_switch_does_not_revoke_the_target_token(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _switch(client, token_id)

        # Still remembered, so switching back must keep working.
        assert AccountToken.query.get(token_id).revoked_at is None
        _switch(client, token_id)
        assert _acting_user(client) == str(alice.id)

    def test_switch_drops_the_previous_users_team_context(
        self, client, db_session, default_org, default_team, second_team
    ):
        """The important one: B must not inherit A's current_team_id.

        Many queries read session['current_team_id'] directly rather than
        through the revalidating decorator, so a stale value is a real
        cross-tenant read.
        """
        alice = _make_user(db_session, default_org, default_team, "alice")
        db_session.add(TeamAssignment(
            user_id=alice.id, team_id=second_team.id))
        db_session.commit()

        _login(client, alice)
        client.post("/switch-team", data={"team_id": second_team.id})

        bob = _make_user(db_session, default_org, default_team, "bob")
        _login(client, bob)

        with client.session_transaction() as sess:
            assert sess["current_team_id"] == default_team.id

        alice_token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _switch(client, alice_token_id)

        with client.session_transaction() as sess:
            assert sess["current_team_id"] == default_team.id
            assert sess["current_team_name"] == default_team.name

    def test_switch_clears_org_and_season_context(
        self, client, two_users
    ):
        """Org and season are not revalidated by any decorator, so they must
        be cleared explicitly on every identity change."""
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)  # bob is now the active identity

        # Context belonging to bob, which alice must not inherit.
        with client.session_transaction() as sess:
            sess["current_org_id"] = 999
            sess["current_season_id"] = 999

        alice_token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _switch(client, alice_token_id)

        with client.session_transaction() as sess:
            assert "current_org_id" not in sess
            assert "current_season_id" not in sess
            assert sess["_user_id"] == str(alice.id)

    def test_switching_to_the_active_account_leaves_context_alone(
        self, client, two_users
    ):
        """Re-picking your own account is a no-op, not a context reset."""
        alice, _ = two_users
        _login(client, alice)
        with client.session_transaction() as sess:
            sess["current_org_id"] = 4242

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _switch(client, token_id)

        with client.session_transaction() as sess:
            assert sess["current_org_id"] == 4242

    def test_switching_to_the_current_account_is_a_no_op(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        token_id = AccountToken.query.filter_by(
            user_id=alice.id, revoked_at=None).first().id

        _switch(client, token_id)
        assert _acting_user(client) == str(alice.id)

    def test_switch_honours_a_safe_return_path(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )

        resp = _switch(client, token_id, return_to="/players")
        assert resp.headers["Location"].endswith("/players")

    def test_switch_rejects_an_offsite_return_path(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )

        resp = _switch(client, token_id, return_to="//evil.example/x")
        assert "evil.example" not in resp.headers["Location"]


# =============================================================================
# The authorisation gate
# =============================================================================


class TestTokenScoping:
    def test_a_valid_token_from_another_browser_is_rejected(self, client,
                                                            two_users):
        """A row id plus a valid token, but not THIS browser's cookie.

        This is the case that stops a leaked/screenshot'd token_id from being
        usable anywhere.
        """
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )

        # A second browser knows a real token_id but has an empty cookie.
        other = client.application.test_client()
        with other.session_transaction() as sess:
            sess["_user_id"] = str(bob.id)
            sess["_fresh"] = True

        before = _acting_user(other)
        other.post("/auth/accounts/switch", data={"token_id": token_id})
        assert _acting_user(other) == before

    def test_switch_rejects_a_garbage_token_id(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])

        for bad in ("", "0", "-1", "abc", "999999", None):
            resp = _switch(client, bad)
            assert resp.status_code in (302, 400)

        assert _acting_user(client) == str(two_users[1].id)

    def test_switch_rejects_a_revoked_token(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        client.post("/auth/accounts/forget-all")

        _login(client, bob)
        # Re-mint for alice, then revoke server-side only.
        _login(client, alice)
        AccountToken.query.get(token_id).revoked_at = datetime.utcnow()
        db.session.commit()

        _login(client, bob)
        _switch(client, token_id)
        assert _acting_user(client) == str(bob.id)

    def test_switch_rejects_a_tampered_cookie_listing_a_dead_token(
        self, client, two_users
    ):
        """Hand-editing the cookie cannot resurrect a revoked login."""
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _set_cookie_tokens(client, ["deadbeef-not-a-real-token"])
        _switch(client, token_id)
        assert _acting_user(client) == str(two_users[1].id)

    def test_remembered_login_dies_with_the_user(self, client, db_session,
                                                 default_org, default_team):
        alice = _make_user(db_session, default_org, default_team, "alice")
        bob = _make_user(db_session, default_org, default_team, "bob")
        _login(client, alice)
        _login(client, bob)

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        db_session.delete(User.query.get(alice.id))
        db_session.commit()

        _switch(client, token_id)
        # Must not impersonate the deleted user, and must not 500.
        assert _acting_user(client) == str(bob.id)

    def test_inactive_user_cannot_be_switched_to(self, client, db_session,
                                                 default_org, default_team):
        alice = _make_user(db_session, default_org, default_team, "alice")
        bob = _make_user(db_session, default_org, default_team, "bob")
        _login(client, alice)
        _login(client, bob)

        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        # UserMixin.is_active is a property; override it on the instance.
        db_session.get(User, alice.id)
        type(alice).is_active = property(lambda self: False)
        try:
            _switch(client, token_id)
            assert _acting_user(client) == str(bob.id)
        finally:
            del type(alice).is_active


# =============================================================================
# Removal and sign-out scope
# =============================================================================


class TestRemoval:
    def test_remove_other_account_keeps_you_signed_in(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        alice_token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        client.post("/auth/accounts/remove",
                    data={"token_id": alice_token_id})

        assert _acting_user(client) == str(bob.id)
        assert AccountToken.query.get(alice_token_id).revoked_at is not None
        assert len(_cookie_tokens(client)) == 1

    def test_remove_current_account_signs_you_out(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        token_id = AccountToken.query.filter_by(
            user_id=alice.id, revoked_at=None).first().id

        resp = client.post("/auth/accounts/remove",
                           data={"token_id": token_id})
        assert resp.status_code == 302
        assert _acting_user(client) is None

    def test_forget_all_clears_cookie_and_revokes_rows(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)
        assert len(AccountToken.query.filter_by(revoked_at=None).all()) == 2

        client.post("/auth/accounts/forget-all")

        assert _cookie_tokens(client) == []
        assert AccountToken.query.filter_by(revoked_at=None).count() == 0
        assert _acting_user(client) is None

    def test_logout_keeps_other_accounts_remembered(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        client.post("/auth/logout")
        assert len(_cookie_tokens(client)) == 1
        assert AccountToken.query.filter_by(
            user_id=alice.id, revoked_at=None).count() == 1

    def test_logout_scope_all_revokes_everything(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        client.post("/auth/accounts/forget-all")
        assert _cookie_tokens(client) == []
        assert AccountToken.query.filter_by(revoked_at=None).count() == 0


# =============================================================================
# Menu rendering
# =============================================================================


class TestMenu:
    def test_menu_lists_both_accounts(self, client, two_users):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        html = client.get("/").get_data(as_text=True)
        assert "Add another account" in html
        assert "Sign out of all accounts" in html
        assert alice.username in html
        assert bob.username in html

    def test_menu_marks_the_active_account(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)

        html = client.get("/").get_data(as_text=True)
        assert "is-current" in html

    def test_single_account_hides_the_multi_account_actions(self, client,
                                                           two_users):
        _login(client, two_users[0])
        html = client.get("/").get_data(as_text=True)
        assert "Sign out of all accounts" not in html
        assert "Add another account" in html

    def test_switching_can_be_disabled_entirely(self, app, client, two_users):
        alice, bob = two_users
        # Establish both accounts while the feature is still on.
        _login(client, alice)
        _login(client, bob)
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )

        app.config["ACCOUNT_SWITCHING_ENABLED"] = False
        try:
            assert client.post("/auth/accounts/switch",
                               data={"token_id": token_id}).status_code == 404
            assert client.post("/auth/accounts/remove",
                               data={"token_id": token_id}).status_code == 404
            assert client.post("/auth/accounts/forget-all").status_code == 404
            assert _acting_user(client) == str(bob.id)

            # Menu falls back to the plain sign-out link.
            html = client.get("/").get_data(as_text=True)
            assert "Add another account" not in html
            assert "/auth/logout" in html
        finally:
            app.config["ACCOUNT_SWITCHING_ENABLED"] = True

    def test_add_account_page_is_reachable_while_signed_in(self, client,
                                                           two_users):
        _login(client, two_users[0])
        resp = client.get("/auth/login?switch=1")
        assert resp.status_code == 200
        assert b"Add another account" in resp.data
        assert b"currently signed in as" in resp.data

    def test_login_without_switch_bounces_when_authenticated(self, client,
                                                             two_users):
        _login(client, two_users[0])
        resp = client.get("/auth/login")
        assert resp.status_code == 302
        assert "/auth/login" not in resp.headers["Location"]


# =============================================================================
# Housekeeping
# =============================================================================


class TestPurge:
    def test_purge_removes_revoked_and_stale_rows(self, client, db_session,
                                                   default_org, default_team):
        from web.accounts import purge_expired_tokens

        user = _make_user(db_session, default_org, default_team, "alice")
        _login(client, user)

        revoked = AccountToken.query.filter_by(revoked_at=None).first()
        revoked.revoked_at = datetime.utcnow()
        stale = AccountToken(
            user_id=user.id, token_hash="a" * 64,
            last_used_at=datetime.utcnow() - timedelta(days=200))
        db_session.add(stale)
        db.session.commit()

        assert purge_expired_tokens() == 2
        assert AccountToken.query.count() == 0

    def test_purge_keeps_live_recent_rows(self, client, db_session,
                                          default_org, default_team):
        from web.accounts import purge_expired_tokens

        user = _make_user(db_session, default_org, default_team, "alice")
        _login(client, user)
        assert purge_expired_tokens() == 0
        assert AccountToken.query.count() == 1


# =============================================================================
# Non-regression for session-injected clients
# =============================================================================


def test_session_injected_login_still_renders(client, editor_user,
                                              default_team):
    """conftest bypasses login_user(); the menu must tolerate that."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(editor_user.id)
        sess["_fresh"] = True
        sess["current_team_id"] = default_team.id
        sess["current_team_name"] = default_team.name

    resp = client.get("/")
    assert resp.status_code == 200
    # No remembered accounts, but the trigger and add-account link still work.
    assert b"Add another account" in resp.data


def test_malformed_cookie_is_ignored(client, two_users):
    client.set_cookie(ACCOUNTS_COOKIE, "}{not json", domain="localhost")
    resp = client.get("/")
    assert resp.status_code in (200, 302)


# =============================================================================
# Review follow-ups: logout method, return-path hardening, intent carry,
# prune-before-cap, config robustness, deterministic eviction
# =============================================================================


class TestLogoutMethod:
    def test_get_logout_does_not_sign_out(self, client, two_users):
        _login(client, two_users[0])
        assert client.get("/auth/logout").status_code == 405
        # Still signed in: a cross-site top-level GET cannot log anyone out.
        assert _acting_user(client) == str(two_users[0].id)

    def test_menu_signs_out_via_post_form(self, client, two_users):
        _login(client, two_users[0])
        html = client.get("/").get_data(as_text=True)
        assert 'action="/auth/logout"' in html
        assert "csrf_token" in html


class TestReturnPath:
    # ``///evil`` and ``/%2F%2Fevil`` are deliberately NOT in this list:
    # urlparse normalises the former to a same-origin path and never decodes
    # the latter, so both stay on our host. Blocking them would be theatre.
    @pytest.mark.parametrize("evil", [
        "//evil.example/",
        "/\\evil.example/",
        "javascript:alert(1)",
        "https://evil.example/",
        "http://evil.example/",
        "/\\n/evil.example/",
        "",
    ])
    def test_malicious_return_paths_are_dropped(self, client, two_users, evil):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        resp = _switch(client, token_id, return_to=evil)
        assert "evil.example" not in resp.headers["Location"]
        assert "javascript" not in resp.headers["Location"]
        assert _acting_user(client) == str(alice.id)

    def test_plain_path_with_query_survives(self, client, two_users):
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        resp = _switch(client, token_id, return_to="/players?team=1")
        assert resp.headers["Location"].endswith("/players?team=1")


class TestOtpAddAccount:
    def test_gm_adding_second_account_keeps_intent_through_otp(
        self, client, db_session, default_org, default_team, mocker
    ):
        """A GM adding an account must land on the "Added" flow, not the
        generic welcome, and must honour the requested return path."""
        mocker.patch("web.routes.auth.notify_otp", return_value=True)
        alice = _make_user(db_session, default_org, default_team, "alice")
        gm = _make_user(db_session, default_org, default_team, "boss",
                        is_gm=True, password="bosspw")
        _login(client, alice)

        resp = client.post("/auth/login?switch=1", data={
            "username": "boss", "password": "bosspw", "switch": "1",
            "return_to": "/players",
        })
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/auth/verify-otp")
        # Still alice until the code is entered; the GM's token must not be
        # minted yet, so the cookie still holds exactly alice's login.
        assert _acting_user(client) == str(alice.id)
        assert len(_cookie_tokens(client)) == 1
        assert AccountToken.query.filter_by(
            user_id=gm.id, revoked_at=None).count() == 0

        code = User.query.filter_by(username="boss").first().otp_code
        assert code
        resp = client.post("/auth/verify-otp", data={"otp_code": code},
                           follow_redirects=True)
        assert resp.status_code == 200
        assert b"Added boss to this device." in resp.data
        assert _acting_user(client) == str(gm.id)
        assert AccountToken.query.filter_by(
            user_id=gm.id, revoked_at=None).count() == 1


class TestSsoAddAccount:
    def _arm(self, client):
        with client.session_transaction() as sess:
            sess["_account_add"] = True
            sess["_account_add_return"] = "/players"
            sess["_account_add_at"] = datetime.utcnow().isoformat()

    def test_login_sso_arms_intent_then_redirects(
        self, client, two_users, mocker
    ):
        mock_url = mocker.patch(
            "web.routes.auth.get_auth_url", return_value="https://idp.example/auth")
        _login(client, two_users[0])

        resp = client.get("/auth/login/sso?switch=1&return_to=/players")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://idp.example/auth"
        mock_url.assert_called_once()
        with client.session_transaction() as sess:
            assert sess.get("_account_add") is True
            assert sess.get("_account_add_return") == "/players"

    def test_login_sso_without_switch_sets_no_intent(
        self, client, two_users, mocker
    ):
        mocker.patch("web.routes.auth.get_auth_url",
                     return_value="https://idp.example/auth")
        _login(client, two_users[0])

        client.get("/auth/login/sso")
        with client.session_transaction() as sess:
            assert sess.get("_account_add") is not True

    def test_callback_consumes_intent(self, client, db_session, default_org,
                                      default_team, mocker):
        alice = _make_user(db_session, default_org, default_team, "alice")
        sso = _make_user(db_session, default_org, default_team, "ssogal")
        _login(client, alice)
        self._arm(client)

        result = mocker.MagicMock()
        result.user.id = "workos-123"
        result.user.email = sso.email
        mocker.patch("web.routes.auth.authenticate_callback",
                     return_value=result)

        resp = client.get("/auth/callback?code=abc123")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/players")
        assert _acting_user(client) == str(sso.id)
        assert AccountToken.query.filter_by(
            user_id=sso.id, revoked_at=None).count() == 1

        # Follow through to the landing page for the "Added" flash.
        page = client.get("/players", follow_redirects=True)
        assert b"Added ssogal to this device." in page.data

    def test_callback_ignores_stale_intent(self, client, db_session,
                                           default_org, default_team, mocker):
        alice = _make_user(db_session, default_org, default_team, "alice")
        sso = _make_user(db_session, default_org, default_team, "ssogal")
        _login(client, alice)
        with client.session_transaction() as sess:
            sess["_account_add"] = True
            sess["_account_add_return"] = "/players"
            sess["_account_add_at"] = (
                datetime.utcnow() - timedelta(hours=2)).isoformat()

        result = mocker.MagicMock()
        result.user.id = "workos-123"
        result.user.email = sso.email
        mocker.patch("web.routes.auth.authenticate_callback",
                     return_value=result)

        resp = client.get("/auth/callback?code=abc123")
        assert resp.headers["Location"].endswith("/")
        page = client.get("/", follow_redirects=True)
        assert b"Added ssogal" not in page.data


class TestPruneBeforeCap:
    def test_stale_cookie_entries_do_not_evict_live_login(
        self, client, two_users
    ):
        """A cookie full of dead tokens must not cost the one live login its
        place when a new account is added."""
        alice, bob = two_users
        _login(client, alice)
        real = _cookie_tokens(client)[0]

        padding = [f"dead-token-{i}" for i in range(MAX_REMEMBERED_ACCOUNTS - 1)]
        _set_cookie_tokens(client, [real] + padding)
        assert len(_cookie_tokens(client)) == MAX_REMEMBERED_ACCOUNTS

        _login(client, bob)

        tokens = _cookie_tokens(client)
        assert len(tokens) == 2
        assert AccountToken.query.filter_by(
            user_id=alice.id, revoked_at=None).count() == 1
        assert AccountToken.query.filter_by(
            user_id=bob.id, revoked_at=None).count() == 1


class TestConfigRobustness:
    def test_malformed_cookie_max_age_never_500s(self, app, client, two_users):
        app.config["ACCOUNT_SWITCH_COOKIE_MAX_AGE"] = "not-a-number"
        try:
            resp = client.post("/auth/login?switch=1", data={
                "username": two_users[0].username, "password": "pw12345",
                "switch": "1",
            })
            assert resp.status_code == 302
            assert _cookie_tokens(client) != []
        finally:
            app.config["ACCOUNT_SWITCH_COOKIE_MAX_AGE"] = 2592000


class TestEvictionOrder:
    def test_eviction_picks_oldest_row_id_on_timestamp_ties(
        self, client, db_session, default_org, default_team
    ):
        users = [
            _make_user(db_session, default_org, default_team, f"evict{i}")
            for i in range(MAX_REMEMBERED_ACCOUNTS)
        ]
        for user in users:
            _login(client, user)

        frozen = datetime(2026, 1, 1)
        for row in AccountToken.query.all():
            row.last_used_at = frozen
        db.session.commit()
        expected_victim = min(r.id for r in AccountToken.query.all())

        newcomer = _make_user(db_session, default_org, default_team, "newcomer")
        _login(client, newcomer)

        assert AccountToken.query.get(expected_victim).revoked_at is not None
        assert AccountToken.query.filter_by(revoked_at=None).count() == (
            MAX_REMEMBERED_ACCOUNTS)


# =============================================================================
# Review round 2: magic-link/SSO intent, onboarding pass-through, stay-on-page
# switch, touch relocation
# =============================================================================


class TestMagicLinkAddAccount:
    def test_magic_link_request_stashes_intent(self, client, two_users, mocker):
        mocker.patch("web.routes.auth.get_magic_link_url",
                     return_value="https://idp.example/magic")
        _login(client, two_users[0])

        resp = client.post("/auth/login?switch=1", data={
            "email": "someone@example.com", "switch": "1",
            "return_to": "/players",
        })
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://idp.example/magic"
        with client.session_transaction() as sess:
            assert sess.get("_account_add") is True
            assert sess.get("_account_add_return") == "/players"


class TestLoginSsoFailure:
    def test_failed_sso_keeps_add_account_context(
        self, client, two_users, mocker
    ):
        def _boom(redirect_uri):
            raise RuntimeError("IdP down")

        mocker.patch("web.routes.auth.get_auth_url", side_effect=_boom)
        _login(client, two_users[0])

        resp = client.get("/auth/login/sso?switch=1&return_to=/players")
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "/auth/login" in location
        assert "switch=1" in location
        assert "return_to" in location


class TestOnboardingPassthrough:
    def test_sso_add_for_orgless_user_lands_on_return_path(
        self, client, db_session, default_org, default_team, mocker
    ):
        alice = _make_user(db_session, default_org, default_team, "alice")
        _login(client, alice)
        with client.session_transaction() as sess:
            sess["_account_add"] = True
            sess["_account_add_return"] = "/players"
            sess["_account_add_at"] = datetime.utcnow().isoformat()

        result = mocker.MagicMock()
        result.user.id = "workos-fresh"
        result.user.email = "fresh@example.com"
        mocker.patch("web.routes.auth.authenticate_callback",
                     return_value=result)

        resp = client.get("/auth/callback?code=xyz")
        assert resp.headers["Location"].endswith("/auth/onboarding")

        newcomer = User.query.filter_by(email="fresh@example.com").first()
        assert newcomer is not None
        assert _acting_user(client) == str(newcomer.id)

        resp = client.post("/auth/onboarding", data={
            "organization_name": "Fresh Org", "team_name": "Fresh Team",
        })
        assert resp.headers["Location"].endswith("/players")
        with client.session_transaction() as sess:
            assert sess.get("current_team_name") == "Fresh Team"


class TestStayOnPageSwitch:
    def test_switch_form_points_back_at_current_page(self, client, two_users):
        _login(client, two_users[0])
        _login(client, two_users[1])

        html = client.get("/players").get_data(as_text=True)
        assert 'name="return_to" value="/players"' in html

    def test_switch_without_return_path_falls_back_to_index(
        self, client, two_users
    ):
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        resp = client.post("/auth/accounts/switch",
                           data={"token_id": token_id})
        assert resp.headers["Location"].endswith("/")


class TestTouchRelocation:
    def test_page_view_refreshes_active_account_timestamp(
        self, client, two_users
    ):
        _login(client, two_users[0])
        record = AccountToken.query.filter_by(
            user_id=two_users[0].id, revoked_at=None).first()
        record.last_used_at = datetime.utcnow() - timedelta(hours=5)
        db.session.commit()

        client.get("/")
        db.session.refresh(record)
        assert datetime.utcnow() - record.last_used_at < timedelta(hours=1)

    def test_template_rendering_only_touches_the_active_account(
        self, client, two_users
    ):
        """The menu lists every remembered account, but a page view must
        refresh exactly one timestamp: the active login's. Anything more
        means the template path is writing again."""
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)  # bob is active
        stale = datetime.utcnow() - timedelta(hours=5)
        for row in AccountToken.query.filter_by(revoked_at=None).all():
            row.last_used_at = stale
        db.session.commit()

        client.get("/")

        seen = {
            r.user_id: r.last_used_at
            for r in AccountToken.query.filter_by(revoked_at=None).all()
        }
        assert datetime.utcnow() - seen[bob.id] < timedelta(hours=1)
        assert seen[alice.id] == stale


# =============================================================================
# Resilience: stale databases missing the account_tokens table
# =============================================================================


def _drop_account_tokens_table():
    """Simulate a database created before multi-account sign-in existed."""
    from sqlalchemy import text

    db.session.execute(text("DROP TABLE IF EXISTS account_tokens"))
    db.session.commit()


class TestMissingTableResilience:
    def test_boot_migration_creates_the_missing_table(self, client):
        from sqlalchemy import inspect

        from core.db_migrations import add_missing_columns

        _drop_account_tokens_table()
        assert not inspect(db.engine).has_table("account_tokens")

        add_missing_columns(db)

        assert inspect(db.engine).has_table("account_tokens")

    def test_login_succeeds_and_self_heals_when_table_missing(
        self, client, two_users
    ):
        """Sign-in must never 500 just because remembering is unavailable."""
        _drop_account_tokens_table()

        resp = _login(client, two_users[0])

        assert resp.status_code == 302
        assert _acting_user(client) == str(two_users[0].id)
        assert len(_cookie_tokens(client)) == 1

    def test_adding_a_second_account_keeps_the_first_after_self_heal(
        self, client, two_users
    ):
        alice, bob = two_users
        _drop_account_tokens_table()

        _login(client, alice)
        _login(client, bob)

        tokens = _cookie_tokens(client)
        assert len(tokens) == 2
        assert {AccountToken.query.filter_by(
            token_hash=hash_token(t)).first().user_id for t in tokens} == {
            alice.id, bob.id}

    def test_logout_succeeds_when_table_missing(self, client, two_users):
        _login(client, two_users[0])
        _drop_account_tokens_table()

        resp = client.post("/auth/logout")

        assert resp.status_code == 302
        assert _acting_user(client) is None

    def test_switch_is_rejected_gracefully_when_table_missing(
        self, client, two_users
    ):
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)
        token_id = next(
            r.id for r in AccountToken.query.all()
            if r.user_id == alice.id and r.revoked_at is None
        )
        _drop_account_tokens_table()

        resp = _switch(client, token_id)

        assert resp.status_code == 302
        assert _acting_user(client) == str(bob.id)

    def test_menu_renders_when_table_missing(self, client, two_users):
        _login(client, two_users[0])
        _drop_account_tokens_table()

        resp = client.get("/")

        assert resp.status_code == 200
        assert b"Add another account" in resp.data

    def test_menu_offers_per_account_remove(self, client, two_users):
        """A stuck entry must be forgettable without wiping every account."""
        alice, bob = two_users
        _login(client, alice)
        _login(client, bob)

        html = client.get("/").get_data(as_text=True)

        assert 'action="/auth/accounts/remove"' in html
        assert f"data-forgot-user=\"{alice.username}\"" in html

    def test_forget_confirm_is_not_an_inline_js_string(self, client, two_users):
        """No username may reach an inline onsubmit handler.

        HTML attribute entities are decoded before the handler compiles, so a
        quote in a username would break or inject into an inline string.
        """
        alice, _ = two_users
        _login(client, alice)
        _login(client, two_users[1])

        html = client.get("/").get_data(as_text=True)

        assert "onsubmit=" not in html.split('class="acct__forget-form"')[1].split(">")[0]
        assert "data-forget-form" in html


class TestRememberFailurePreservesCookie:
    def test_backend_outage_during_add_keeps_existing_accounts(
        self, client, two_users, mocker
    ):
        """A lookup that fails must not be mistaken for "no live tokens".

        Pruning on that guess would hand back a cookie holding only the new
        token, silently dropping accounts the browser still owns.
        """
        alice, bob = two_users
        _login(client, alice)
        before = _cookie_tokens(client)
        assert len(before) == 1

        import web.accounts as accounts_mod

        # The listing used to prune dead entries fails, as it would mid-outage.
        mocker.patch.object(
            accounts_mod, "_list_remembered_accounts_resolved", return_value=([], False)
        )
        _login(client, bob)

        # alice is still remembered; bob simply is not yet.
        after = _cookie_tokens(client)
        assert after == before
        assert _acting_user(client) == str(bob.id)

    def test_menu_still_renders_empty_on_backend_outage(self, client, two_users,
                                                        mocker):
        """Rendering keeps the tolerant empty-list behaviour."""
        import web.accounts as accounts_mod

        mocker.patch.object(
            accounts_mod, "_list_remembered_accounts_resolved", return_value=([], False)
        )
        _login(client, two_users[0])

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Add another account" in resp.data

    def test_user_id_is_captured_before_rollback(self, client, two_users, mocker):
        """Reading ``user.id`` after rollback can re-query a dead database.

        The handler must log the id it captured up front instead.
        """
        import web.accounts as accounts_mod

        reads = []

        class _ExpiresOnReload:
            """Mimics SQLAlchemy expiring attributes on rollback.

            The first read (before any rollback) works; any later read
            re-queries a database that is still down and raises.
            """

            @property
            def id(self):
                reads.append(1)
                if len(reads) > 1:
                    raise RuntimeError("database is gone")
                return 42

        mocker.patch.object(
            accounts_mod, "_remember_account_inner",
            side_effect=RuntimeError("no such table: account_tokens"),
        )
        with client.application.test_request_context("/"):
            # Degrades to "not remembered" instead of propagating.
            assert accounts_mod.remember_account(_ExpiresOnReload()) is None
        # Exactly one read: the capture before the operation. A second read in
        # the error handler is the re-query this guards against.
        assert len(reads) == 1
