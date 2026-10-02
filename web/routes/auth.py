from datetime import datetime, timedelta
import logging
import os
import secrets
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
    session,
    current_app,
)
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email

from core.models import (
    User, SystemSetting, Organization, Team,
    OrganizationMembership, TeamAssignment, AdminAudit,
    db, bcrypt, Player, WhatsAppGroup, log_admin_action,
)
from core.services.notification_service import notify_otp
from core.services.email_service import send_invite_email
from core.services.workos_service import (
    get_auth_url,
    get_magic_link_url,
    authenticate_callback,
    create_workos_user,
    send_workos_invitation,
    get_logout_url,
)
from core.logger import get_logger
from web.accounts import (
    forget_all_accounts,
    forget_record,
    purge_user_tokens,
    remembered_record,
    remembered_record_id_for,
    remember_account,
)
from web.decorators import admin_required, gm_required, require_own_org

logger = get_logger("auth")

auth_bp = Blueprint("auth", __name__)

# Every piece of per-user state the session carries. These are all scoped to
# ONE identity, so any change of identity must drop them wholesale --
# otherwise account B would inherit account A's team, org and season.
USER_CONTEXT_KEYS = (
    "current_team_id",
    "current_team_name",
    "current_org_id",
    "current_season_id",
    "otp_user_id",
)


def _clear_user_context() -> None:
    for key in USER_CONTEXT_KEYS:
        session.pop(key, None)


def _apply_default_team_context(user) -> None:
    """Seed team context for a freshly authenticated user, if they have one."""
    if not user.organization_id:
        return
    teams = user.assigned_teams
    if teams:
        session["current_team_id"] = teams[0].id
        session["current_team_name"] = teams[0].name


def _establish_identity(user, remember: bool = True) -> None:
    """Move the session onto ``user``, discarding the previous identity's state.

    Every identity change in the app funnels through here: password login,
    WorkOS callback, OTP completion, and account switching. Centralising it
    matters because ``login_user`` on its own leaves ``current_team_id``
    pointing at the *previous* user's team, and plenty of queries read that
    key directly rather than through a decorator that would revalidate it.
    """
    logout_user()
    _clear_user_context()
    login_user(user, remember=remember)
    _apply_default_team_context(user)
    # Remembering is best-effort: a stale database or a transient outage
    # must never turn a successful authentication into a 500. The user is
    # already signed in at this point; without a remembered token they just
    # won't appear in the switcher until they sign in again.
    # Capture the id first: SQLAlchemy expires loaded attributes on rollback,
    # so reading ``user.id`` in the handler could re-query a database that is
    # still unavailable and raise a second time, 500-ing the sign-in.
    user_id = getattr(user, "id", None)
    try:
        remember_account(user)
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning("remember_account failed for user %s: %s", user_id, exc)


def _switching_enabled() -> bool:
    return bool(current_app.config.get("ACCOUNT_SWITCHING_ENABLED", True))


def _workos_configured() -> bool:
    """True when the WorkOS IdP is usable for this deployment.

    Shared by the sign-in page and the invite flow so the two cannot drift
    on what "WorkOS is available" means.
    """
    return bool(
        current_app.config.get("WORKOS_API_KEY")
        and current_app.config.get("WORKOS_CLIENT_ID")
    )


# Intent marker so the "add another account" flow survives round trips that
# cannot carry query strings: the OTP form posts to /verify-otp (not
# /login?switch=1), and the WorkOS IdP round trip returns to a fixed
# redirect URI. Stored in the session because only this browser may act on
# it, consumed exactly once, and ignored when stale.
_ACCOUNT_ADD_KEY = "_account_add"
_ACCOUNT_ADD_RETURN_KEY = "_account_add_return"
_ACCOUNT_ADD_AT_KEY = "_account_add_at"
_ACCOUNT_ADD_TTL = timedelta(minutes=30)


def _stash_account_add_intent(return_to: str | None) -> None:
    session[_ACCOUNT_ADD_KEY] = True
    session[_ACCOUNT_ADD_RETURN_KEY] = return_to
    session[_ACCOUNT_ADD_AT_KEY] = datetime.utcnow().isoformat()


def _pop_account_add_intent() -> tuple[bool, str | None]:
    """Consume a stashed add-account intent; (was_adding, return_path)."""
    if not session.pop(_ACCOUNT_ADD_KEY, False):
        session.pop(_ACCOUNT_ADD_RETURN_KEY, None)
        session.pop(_ACCOUNT_ADD_AT_KEY, None)
        return False, None
    try:
        armed_at = datetime.fromisoformat(
            session.pop(_ACCOUNT_ADD_AT_KEY, "") or "")
    except ValueError:
        armed_at = None
    return_to = session.pop(_ACCOUNT_ADD_RETURN_KEY, None)
    if armed_at is None or datetime.utcnow() - armed_at > _ACCOUNT_ADD_TTL:
        return False, None
    if return_to and _is_safe_return_path(return_to):
        return True, return_to
    return True, None


def _is_safe_return_path(raw: str | None) -> bool:
    """Same-origin check shared by the request-value and session-stashed paths."""
    from urllib.parse import urlparse

    if not raw or not isinstance(raw, str):
        return False
    raw = raw.strip()
    if not raw or "\\" in raw:
        return False
    parsed = urlparse(raw)
    if parsed.scheme or parsed.netloc:
        return False
    # Note: urlparse normalises a leading run of slashes (``///evil`` becomes
    # path ``/evil``) and never percent-decodes, so ``/%2F%2Fevil`` stays a
    # same-origin path. Both are therefore safe to allow.
    if not parsed.path.startswith("/"):
        return False
    return True


def _safe_return_path() -> str | None:
    """A relative path to come back to after adding an account, or None.

    Parsed with ``urllib.parse`` rather than prefix checks alone, so encoded
    tricks (``/%2F%2Fevil``, ``/\\evil``) and scheme-relative smuggling
    (``//evil``, ``/\\evil``) cannot slip through as a same-origin path.
    Only a plain path with no scheme, host, or backslash survives.
    """
    raw = (request.values.get("return_to") or "").strip()
    return raw if _is_safe_return_path(raw) else None


class EmptyForm(FlaskForm):
    """Empty form for CSRF protection"""

    submit = SubmitField("Sign In")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Sign in, or add another account to this browser.

    ``?switch=1`` keeps the form available to an already-authenticated user,
    which is what the account menu's "Add account" entry links to. Without it
    an authenticated visitor is bounced to the dashboard as before.
    """
    adding_account = (
        _switching_enabled() and (request.values.get("switch") == "1")
    )
    if current_user.is_authenticated and not adding_account:
        return redirect(url_for("main.index"))

    redirect_uri = current_app.config.get(
        "WORKOS_REDIRECT_URI", "http://localhost:5000/auth/callback"
    )
    workos_configured = _workos_configured()
    auth_url = "#"
    workos_error = None
    if workos_configured:
        try:
            auth_url = get_auth_url(redirect_uri)
        except Exception as e:
            current_app.logger.warning(f"WorkOS auth URL unavailable: {e}")
            workos_error = str(e)
    else:
        workos_error = "WorkOS not configured"

    def render(**overrides):
        ctx = {
            "auth_url": auth_url,
            "workos_configured": workos_configured,
            "workos_error": workos_error,
            "adding_account": adding_account,
            "return_to": _safe_return_path() or "",
        }
        ctx.update(overrides)
        return render_template("auth/login.html", **ctx)

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            user = User.query.filter_by(username=username).first()
            if user and user.password_hash and user.check_password(password):
                if user.is_manager:
                    # OTP is required when an identity is first established,
                    # and is not repeated when merely switching back to an
                    # account already remembered by this browser. The
                    # add-account intent cannot travel as a query string
                    # (the OTP form posts to /verify-otp), so stash it in
                    # the session for verify_otp to consume.
                    otp_code = f"{secrets.randbelow(1000000):06d}"
                    user.otp_code = otp_code
                    user.otp_expiry = datetime.utcnow() + timedelta(minutes=5)
                    db.session.commit()
                    session["otp_user_id"] = user.id
                    if adding_account:
                        _stash_account_add_intent(_safe_return_path())
                    notify_otp(
                        user.email, otp_code,
                        whatsapp_phone=getattr(user, "whatsapp_phone", None)
                    )
                    flash("Verification code sent. Please check your email.", "info")
                    return redirect(url_for("auth.verify_otp"))

                _establish_identity(user)

                if not user.organization_id:
                    flash("Welcome! Please set up your organization to get started.", "info")
                    return redirect(url_for("auth.onboarding"))

                if adding_account:
                    flash(f"Added {user.username} to this device.", "success")
                    return redirect(_safe_return_path() or url_for("main.index"))

                flash(f"Welcome back, {user.username}!", "success")
                return redirect(url_for("main.index"))

            flash("Invalid username or password", "danger")
            return render()

        email = request.form.get("email")
        if email:
            try:
                # The magic-link round trip returns to the fixed callback URI
                # like SSO, so stash the add-account intent for it too.
                if adding_account:
                    _stash_account_add_intent(_safe_return_path())
                magic_url = get_magic_link_url(email, redirect_uri)
                flash(f"Magic link sent to {email}. Check your inbox!", "info")
                return redirect(magic_url)
            except Exception as e:
                current_app.logger.warning(f"Magic link unavailable: {e}")
                flash("Magic link service unavailable. Try again later.", "danger")

    return render()


@auth_bp.route("/login/sso")
def login_sso():
    """Start WorkOS SSO, optionally in "add another account" mode.

    The IdP round trip returns to a fixed redirect URI that cannot carry
    ``?switch=1``, so the intent is stashed in the session for the callback
    to consume. Arming the flag is harmless on its own: it only changes the
    flash message and landing page after a *successful* authentication.
    """
    redirect_uri = current_app.config.get(
        "WORKOS_REDIRECT_URI", "http://localhost:5000/auth/callback"
    )
    try:
        auth_url = get_auth_url(redirect_uri)
    except Exception as e:
        current_app.logger.warning(f"WorkOS auth URL unavailable: {e}")
        flash("Single sign-on is unavailable. Try again later.", "danger")
        # Don't strand an add-account attempt on the plain sign-in page:
        # send it back with its context intact.
        if (
            _switching_enabled()
            and current_user.is_authenticated
            and request.args.get("switch") == "1"
        ):
            return_to = _safe_return_path()
            if return_to:
                return redirect(url_for(
                    "auth.login", switch=1, return_to=return_to))
            return redirect(url_for("auth.login", switch=1))
        return redirect(url_for("auth.login"))

    if (
        _switching_enabled()
        and current_user.is_authenticated
        and request.args.get("switch") == "1"
    ):
        _stash_account_add_intent(_safe_return_path())
    return redirect(auth_url)


@auth_bp.route("/callback")
def callback():
    """Handle WorkOS authentication callback"""
    code = request.args.get("code")

    if not code:
        flash("Authentication failed. No authorization code received.", "danger")
        return redirect(url_for("auth.login"))

    try:
        result = authenticate_callback(code)
        workos_user = result.user

        user = User.query.filter_by(workos_id=workos_user.id).first()

        if not user:
            user = User.query.filter_by(email=workos_user.email).first()

            if user:
                user.workos_id = workos_user.id
                user.email_verified = True
            else:
                username = workos_user.email.split("@")[0]
                base_username = username
                counter = 1
                while User.query.filter_by(username=username).first():
                    username = f"{base_username}{counter}"
                    counter += 1

                user = User(
                    workos_id=workos_user.id,
                    email=workos_user.email,
                    username=username,
                    email_verified=True,
                    password_hash=None,
                )
                db.session.add(user)
                db.session.flush()

            db.session.commit()

        _establish_identity(user)

        # Consume before any redirect so a stale flag can never leak into a
        # later login. When onboarding intervenes the intent is re-stashed
        # below so it survives that detour too.
        was_adding, return_to = _pop_account_add_intent()

        # If user has no organization, redirect to onboarding
        if not user.organization_id:
            current_app.logger.info(
                "New WorkOS user has no org_id, redirecting to onboarding",
                extra={"extra_fields": {"user_id": user.id, "email": user.email}},
            )
            if was_adding:
                _stash_account_add_intent(return_to)
            flash("Welcome! Please set up your organization to get started.", "info")
            return redirect(url_for("auth.onboarding"))

        # The add-account intent only survives via the session (the IdP round
        # trip cannot carry query strings); an absent or stale flag means an
        # ordinary sign-in.
        if was_adding:
            flash(f"Added {user.username} to this device.", "success")
            return redirect(return_to or url_for("main.index"))

        flash(f"Welcome, {user.username}!", "success")
        return redirect(url_for("main.index"))

    except Exception as e:
        msg = f"WorkOS authentication callback error: {e}"
        logger.error(msg, exc_info=True)
        flash(msg, "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    """First-time setup: create or join an organization."""
    if current_app.config.get("LOGIN_DISABLED"):
        return redirect(url_for("main.index"))
    if current_user.organization_id:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        org_name = request.form.get("organization_name", "").strip()
        team_name = request.form.get("team_name", "").strip()

        if not org_name or not team_name:
            flash("Organization name and team name are required.", "danger")
            return render_template("auth/onboarding.html")

        org_slug = org_name.lower().replace(" ", "-")
        org = Organization(name=org_name, slug=org_slug)
        db.session.add(org)
        db.session.flush()

        team_slug = team_name.lower().replace(" ", "-")
        team = Team(name=team_name, organization_id=org.id, slug=team_slug)
        db.session.add(team)
        db.session.flush()

        current_user.organization_id = org.id

        membership = OrganizationMembership(
            user_id=current_user.id, organization_id=org.id, is_gm=True
        )
        db.session.add(membership)

        ta = TeamAssignment(
            user_id=current_user.id, team_id=team.id, is_coach=True
        )
        db.session.add(ta)
        db.session.commit()

        session["current_team_id"] = team.id
        session["current_team_name"] = team.name

        # An add-account flow that detoured through onboarding lands where
        # the user originally was, rather than always on the dashboard.
        _, return_to = _pop_account_add_intent()
        flash(f"Welcome to {org_name}! You are now a GM and coach.", "success")
        return redirect(return_to or url_for("main.index"))

    return render_template("auth/onboarding.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Sign out of the current account only.

    POST-only with CSRF: a GET logout is triggerable by any cross-site
    top-level link (``SameSite=Lax`` still sends cookies there), which turns
    "click this link" into a forced sign-out. Other logins remembered on
    this device survive; use ``POST /auth/accounts/forget-all`` for a full
    device wipe.
    """
    user_id = current_user.id
    record_id = remembered_record_id_for(user_id)
    record = remembered_record(record_id) if record_id else None
    if record is not None:
        forget_record(record)
        message = "Signed out. Other accounts on this device are still remembered."
    else:
        message = "You have been logged out."

    logout_user()
    _clear_user_context()
    flash(message, "info")
    return redirect(url_for("main.landing"))


# ---------------------------------------------------------------------------
# Multi-account switching
#
# The forms post ``token_id`` (an ``account_tokens`` row id), never the token
# itself: the raw value lives only in an HttpOnly cookie, so a leaked page or
# a stray form field cannot expose it. ``remembered_record`` is the single
# gate -- a row id is worthless unless this browser's cookie also carries the
# matching token.
# ---------------------------------------------------------------------------


@auth_bp.route("/accounts/switch", methods=["POST"])
@login_required
def switch_account():
    """Make a remembered account the active one, without re-authenticating.

    Re-authenticating is deliberately skipped: a live token for this browser
    is proof enough that the login -- including its OTP step, if the account
    is a GM -- already happened when the token was minted.
    """
    if not _switching_enabled():
        abort(404)

    record = remembered_record(request.form.get("token_id"))
    if record is None:
        flash("That account is not available on this device.", "danger")
        return redirect(url_for("main.index"))

    user = record.user
    if user.id == current_user.id:
        return redirect(_safe_return_path() or url_for("main.index"))

    _establish_identity(user)

    flash(f"Now signed in as {user.username}.", "success")
    return redirect(_safe_return_path() or url_for("main.index"))


@auth_bp.route("/accounts/remove", methods=["POST"])
@login_required
def remove_account():
    """Forget one remembered account, revoking its token for good.

    Removing the account you are currently signed into signs you out of it,
    matching how removing the active account from a browser's account list
    behaves elsewhere.
    """
    if not _switching_enabled():
        abort(404)

    record = remembered_record(request.form.get("token_id"))
    if record is None:
        flash("That account is not remembered on this device.", "warning")
        return redirect(url_for("main.index"))

    target = record.user
    is_current = target.id == current_user.id
    forget_record(record)

    if is_current:
        logout_user()
        _clear_user_context()
        flash(f"Removed {target.username} from this device and signed out.", "info")
        return redirect(url_for("main.landing"))

    flash(f"Removed {target.username} from this device.", "success")
    return redirect(_safe_return_path() or url_for("main.index"))


@auth_bp.route("/accounts/forget-all", methods=["POST"])
@login_required
def forget_all_accounts_route():
    """Revoke every remembered login for this browser and sign out."""
    if not _switching_enabled():
        abort(404)

    count = forget_all_accounts()
    logout_user()
    _clear_user_context()
    flash(
        f"Signed out of all accounts ({count} removed)." if count
        else "Signed out of all accounts.",
        "info",
    )
    return redirect(url_for("main.landing"))


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    """Verify OTP for admin users."""
    user_id = session.get("otp_user_id")
    if not user_id:
        flash("Verification session expired. Please log in again.", "danger")
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id)
    if not user:
        session.pop("otp_user_id", None)
        flash("User not found. Please log in again.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = (request.form.get("otp_code") or "").strip()
        if not user.otp_code or not user.otp_expiry:
            flash("Verification code expired. Please log in again.", "danger")
            return redirect(url_for("auth.login"))

        if datetime.utcnow() > user.otp_expiry:
            flash("Verification code expired. Please log in again.", "danger")
            return redirect(url_for("auth.login"))

        if code != user.otp_code:
            flash("Invalid verification code.", "danger")
            return render_template("auth/verify_otp.html")

        user.otp_code = None
        user.otp_expiry = None
        db.session.commit()
        session.pop("otp_user_id", None)
        was_adding, return_to = _pop_account_add_intent()
        _establish_identity(user)

        if not user.organization_id:
            if was_adding:
                _stash_account_add_intent(return_to)
            flash("Welcome! Please set up your organization to get started.", "info")
            return redirect(url_for("auth.onboarding"))

        if was_adding:
            flash(f"Added {user.username} to this device.", "success")
            return redirect(return_to or url_for("main.index"))

        flash(f"Welcome back, {user.username}!", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/verify_otp.html")


@auth_bp.route("/settings/update", methods=["POST"])
@login_required
@gm_required
def update_settings():
    """Update system settings"""
    try:
        notify_game = request.form.get("notify_game_added") == "on"
        attach_pdf = request.form.get("attach_game_pdf") == "on"

        SystemSetting.set_value(
            "notify_game_added",
            "true" if notify_game else "false",
            "Send email when game added",
        )
        SystemSetting.set_value(
            "attach_game_pdf",
            "true" if attach_pdf else "false",
            "Attach PDF to game email",
        )

        send_player_reports = request.form.get("send_player_reports") == "on"
        SystemSetting.set_value(
            "send_player_reports",
            "true" if send_player_reports else "false",
            "Send player performance reports",
        )

        flash("System settings updated.", "success")
    except Exception as e:
        flash(f"Error updating settings: {e}", "danger")

    return redirect(url_for("main.admin_panel", section="settings"))


@auth_bp.route("/users/create", methods=["GET", "POST"])
@login_required
@gm_required
def create_user():
    """GM-only user creation via WorkOS"""
    org_id = current_user.organization_id
    team_id = session.get("current_team_id")

    if not org_id:
        flash("You must belong to an organization to create users.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))

    if request.method == "POST":
        email = request.form.get("email")

        if not email:
            flash("Email is required.", "danger")
            return render_template("auth/create_user.html")

        if User.query.filter_by(email=email).first():
            flash("A user with this email already exists.", "warning")
            return render_template("auth/create_user.html")

        try:
            workos_user = create_workos_user(email=email)

            username = email.split("@")[0]
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            new_user = User(
                workos_id=workos_user.id,
                email=email,
                username=username,
                email_verified=False,
                password_hash=None,
                organization_id=org_id,
            )
            db.session.add(new_user)
            db.session.flush()

            # Add org membership as non-GM
            membership = OrganizationMembership(
                user_id=new_user.id, organization_id=org_id, is_gm=False
            )
            db.session.add(membership)

            # Assign to current team as non-coach
            if team_id:
                ta = TeamAssignment(
                    user_id=new_user.id, team_id=team_id, is_coach=False
                )
                db.session.add(ta)

            db.session.commit()

            flash(f"User {email} created. An invitation has been sent.", "success")
            return redirect(url_for("main.admin_panel", section="users"))

        except Exception as e:
            current_app.logger.error(f"Failed to create WorkOS user: {e}")
            flash(f"Failed to create user: {str(e)}", "danger")
            return render_template("auth/create_user.html")

    return render_template("auth/create_user.html")


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@gm_required
def delete_user(user_id):
    """Delete a user account"""
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))

    user = User.query.get_or_404(user_id)
    denied = require_own_org(user.organization_id)
    if denied:
        return denied
    username = user.username
    # Auxiliary cleanup must never block the primary action: if the Drive
    # purge fails, log it and delete the account anyway. Single commit after
    # both deletes so a later failure cannot leave the Drive rows gone while
    # the user row survives.
    from core.services import drive_service

    try:
        drive_service.purge_user_rows(user_id)
    except Exception as exc:
        logger.warning(
            "Drive purge failed for deleted user %s: %s", user_id, exc,
        )
    # Remembered logins must go with the account; a surviving token row
    # would keep the deleted user switchable.
    try:
        purge_user_tokens(user_id)
    except Exception as exc:
        logger.warning(
            "Account token purge failed for deleted user %s: %s", user_id, exc,
        )
    # Memberships and team assignments have non-nullable user_id, so they
    # have to be removed explicitly rather than left for the ORM to null out.
    # This is deliberately belt-and-braces alongside the delete-orphan
    # cascades on the model: the bulk delete avoids loading every child row
    # into the session, and the cascade still covers any path that deletes
    # a User object directly.
    OrganizationMembership.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    TeamAssignment.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    db.session.delete(user)
    db.session.commit()
    log_admin_action(current_user, "user.delete", f"deleted user {username}",
                     target_type="user", target_id=user_id)
    flash(f"User {username} deleted.", "success")
    return redirect(url_for("main.admin_panel", section="users"))


@auth_bp.route("/users/<int:user_id>/membership", methods=["POST"])
@login_required
@gm_required
def manage_membership(user_id):
    """Manage a user's GM status and coaching assignments."""
    if user_id == current_user.id:
        flash("You cannot modify your own membership.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))

    user = User.query.get_or_404(user_id)
    org_id = current_user.organization_id
    team_id = session.get("current_team_id")

    if not org_id or user.organization_id != org_id:
        flash("User is not in your organization.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))

    is_gm = request.form.get("is_gm") == "on"
    is_coach = request.form.get("is_coach") == "on"

    membership = OrganizationMembership.query.filter_by(
        user_id=user.id, organization_id=org_id
    ).first()
    if membership:
        membership.is_gm = is_gm
    else:
        membership = OrganizationMembership(
            user_id=user.id, organization_id=org_id, is_gm=is_gm
        )
        db.session.add(membership)

    if team_id:
        ta = TeamAssignment.query.filter_by(
            user_id=user.id, team_id=team_id
        ).first()
        if ta:
            ta.is_coach = is_coach
        else:
            ta = TeamAssignment(
                user_id=user.id, team_id=team_id, is_coach=is_coach
            )
            db.session.add(ta)

    db.session.commit()
    log_admin_action(current_user, "membership.update",
                     f"updated membership for {user.username} (gm={is_gm}, coach={is_coach})",
                     target_type="user", target_id=user.id)
    flash(f"Membership for {user.username} updated.", "success")
    return redirect(url_for("main.admin_panel", section="users"))


@auth_bp.route("/users/invite", methods=["POST"])
@login_required
@gm_required
def invite_user():
    """Invite flow (GM plan idea 3): create user + assignments in one POST.

    Invited users are SSO-only (``password_hash=None``, like ``create_user``):
    no throwaway password is generated, because one that nobody receives is
    worse than none.

    Delivery, in order of preference:
    1. WorkOS emails the invitation itself (``send_workos_invitation``),
       landing the invitee directly on WorkOS sign-in.
    2. We email a direct WorkOS login link (magic link, else the SSO entry
       point) when the invitation call failed but WorkOS is reachable.

    This route REQUIRES WorkOS. Without it the account would be created with
    no password and no route to obtain one — local sign-in checks
    ``user.password_hash`` and this app has no password-reset or activation
    flow — so the invitee could never authenticate. Rather than mint a dead
    account, the invite is refused up front.
    """
    org_id = current_user.organization_id
    if not org_id:
        flash("You must belong to an organization to invite users.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip()
    if not username or not email:
        flash("Username and email are required.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))
    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash("A user with this username or email already exists.", "warning")
        return redirect(url_for("main.admin_panel", section="users"))

    # Refuse before creating anything: an account we cannot deliver a login
    # for is a locked-out user, and there is no self-service recovery.
    if not _workos_configured():
        flash(
            "Inviting needs WorkOS single sign-on configured, because invitees "
            "sign in without a password. Set WORKOS_API_KEY and "
            "WORKOS_CLIENT_ID, then try again — no account was created.",
            "danger",
        )
        return redirect(url_for("main.admin_panel", section="users"))

    is_gm = request.form.get("is_gm") == "on"
    is_coach = request.form.get("is_coach") == "on"
    raw_team_ids = request.form.getlist("team_ids")
    try:
        team_ids = [int(t) for t in raw_team_ids if str(t).strip()]
    except (TypeError, ValueError):
        team_ids = []
    teams = Team.query.filter(
        Team.id.in_(team_ids), Team.organization_id == org_id).all() if team_ids else []

    # Preferred path: provision the WorkOS user, then ask WorkOS to email the
    # invitation. Creating a user does NOT invite them, so the two calls are
    # separate, and ``workos_invite_sent`` is only set once the invitation
    # itself succeeded. ``workos_id`` is the USER id, never the invitation's.
    #
    # If the user is created but the invitation fails, we deliberately KEEP
    # ``workos_id``. Deleting the WorkOS user to "compensate" would be
    # destructive and could destroy a real account (the address may already
    # exist in WorkOS, e.g. a re-invite of someone who signed in via SSO).
    # The half-provisioned state is benign and self-healing: the fallback
    # emails a login link, and ``/auth/callback`` resolves the local user by
    # ``workos_id`` and otherwise by email, binding the two on first sign-in.
    workos_id = None
    workos_invite_sent = False
    try:
        workos_user = create_workos_user(email=email)
        workos_id = getattr(workos_user, "id", None)
        send_workos_invitation(email=email)
        workos_invite_sent = True
    except Exception as exc:
        current_app.logger.warning(f"WorkOS invite failed for {email}: {exc}")

    new_user = User(username=username, email=email, organization_id=org_id,
                    workos_id=workos_id, password_hash=None)
    db.session.add(new_user)
    db.session.flush()
    db.session.add(OrganizationMembership(
        user_id=new_user.id, organization_id=org_id, is_gm=is_gm))
    for team in teams:
        db.session.add(TeamAssignment(
            user_id=new_user.id, team_id=team.id, is_coach=is_coach))
    db.session.commit()
    log_admin_action(
        current_user, "user.invite",
        f"invited {username} ({email}) to {len(teams)} team(s)"
        + (", GM" if is_gm else ""),
        target_type="user", target_id=new_user.id)

    if workos_invite_sent:
        flash(f"Invited {username} — WorkOS sign-in invitation sent to {email}.",
              "success")
        return redirect(url_for("main.admin_panel", section="users"))

    # Fallback: WorkOS is configured (we returned early otherwise) but the
    # invitation call failed, so email the invitee a login link ourselves. A
    # per-address magic link is the most direct ("click to sign in"); failing
    # that, the SSO entry point — both are genuine WorkOS sign-in routes, so
    # unlike the password form this link can actually authenticate them.
    redirect_uri = current_app.config.get(
        "WORKOS_REDIRECT_URI", "http://localhost:5000/auth/callback"
    )
    login_url = None
    try:
        login_url = get_magic_link_url(email, redirect_uri)
    except Exception as exc:
        current_app.logger.warning(f"Magic-link URL failed for {email}: {exc}")
    if not login_url:
        login_url = url_for("auth.login_sso", _external=True)

    org = Organization.query.get(org_id)
    # ``org`` can only be None if the org was deleted between the check at
    # the top of this view and here; the invite is already committed, so the
    # email just goes out without the org line.
    email_ok = False
    try:
        email_ok = bool(send_invite_email(
            email, username, login_url,
            org_name=getattr(org, "name", None)))
    except Exception as exc:
        current_app.logger.warning(f"Invite email failed for {email}: {exc}")

    if email_ok:
        flash(f"Invited {username} — sign-in link emailed to {email}.",
              "success")
    else:
        logger.warning(
            "Invite email undeliverable for %s; GM must share the link manually",
            email,
        )
        flash(f"Invited {username} — but the invite email could not be sent. "
              f"Copy this sign-in link and send it to them yourself: {login_url}",
              "warning")
    return redirect(url_for("main.admin_panel", section="users"))


@auth_bp.route("/users/<int:user_id>/auditor", methods=["POST"])
@login_required
@gm_required
def toggle_auditor(user_id):
    """Grant/revoke the read-only auditor role (GM plan idea 5)."""
    if user_id == current_user.id:
        flash("You cannot modify your own role.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))
    user = User.query.get_or_404(user_id)
    if user.organization_id != current_user.organization_id:
        flash("User is not in your organization.", "danger")
        return redirect(url_for("main.admin_panel", section="users"))
    user.is_auditor = request.form.get("is_auditor") == "on"
    db.session.commit()
    log_admin_action(current_user, "user.auditor",
                     f"set auditor={user.is_auditor} for {user.username}",
                     target_type="user", target_id=user.id)
    flash(f"Auditor role for {user.username} updated.", "success")
    return redirect(url_for("main.admin_panel", section="users"))


@auth_bp.route("/users/<int:user_id>/teams", methods=["POST"])
@login_required
def toggle_team_assignment(user_id):
    """Assign/remove a user to/from a team (JSON). Used by double-click UI.

    GM-only, except per-team GMs may manage their own team (GM plan idea 1).
    Optional ``role`` in {coach, team_gm} toggles that flag instead of
    membership. Auditors are read-only.
    """
    if getattr(current_user, "is_auditor", False) and not current_app.config.get("LOGIN_DISABLED"):
        return jsonify({"ok": False, "error": "Auditors have read-only access."}), 403
    if user_id == current_user.id:
        return jsonify({"ok": False, "error": "You cannot modify your own teams."}), 400

    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    try:
        team_id = int(data.get("team_id"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Valid team_id required."}), 400
    assigned = bool(data.get("assigned", True))
    role = (data.get("role") or "").strip()

    team = Team.query.get_or_404(team_id)
    if (
        not current_app.config.get("LOGIN_DISABLED")
        and (
            user.organization_id != team.organization_id
            or (
                current_user.organization_id
                and team.organization_id != current_user.organization_id
            )
        )
    ):
        return jsonify({"ok": False, "error": "Team is in another organization."}), 403

    allowed = current_app.config.get("LOGIN_DISABLED") or bool(
        getattr(current_user, "is_gm", False))
    if not allowed and not current_user.can_manage_team(team.id):
        return jsonify({"ok": False, "error": "Not allowed for this team."}), 403

    if role in ("coach", "team_gm"):
        if role == "team_gm" and not allowed:
            # Only an org GM may crown team GMs (no self-service escalation).
            return jsonify({"ok": False,
                            "error": "Only an organization GM can set team GMs."}), 403
        ta = TeamAssignment.query.filter_by(user_id=user.id, team_id=team.id).first()
        if ta is None:
            if not assigned:
                return jsonify({"ok": True, "action": "noop", "teams": []})
            ta = TeamAssignment(user_id=user.id, team_id=team.id)
            db.session.add(ta)
        if role == "coach":
            ta.is_coach = assigned
        else:
            ta.is_team_gm = assigned
        db.session.commit()
        log_admin_action(current_user, "team.role",
                         f"set {role}={assigned} for {user.username} on {team.name}",
                         target_type="team", target_id=team.id)
        return jsonify({"ok": True, "action": role, "assigned": assigned})

    ta = TeamAssignment.query.filter_by(user_id=user.id, team_id=team.id).first()
    if assigned:
        if ta is None:
            db.session.add(TeamAssignment(user_id=user.id, team_id=team.id))
            db.session.commit()
        action = "assigned"
    else:
        if ta is not None:
            db.session.delete(ta)
            db.session.commit()
        action = "removed"
    log_admin_action(current_user, f"team.{action}",
                     f"{action} {user.username} {'to' if assigned else 'from'} {team.name}",
                     target_type="team", target_id=team.id)
    teams = [
        {"id": t.id, "name": t.name}
        for t in Team.query.join(TeamAssignment)
        .filter(TeamAssignment.user_id == user.id)
        .order_by(Team.name)
        .all()
    ]
    return jsonify({"ok": True, "action": action, "teams": teams})


@auth_bp.route("/players")
@login_required
@gm_required
def manage_players():
    """Redirect to admin panel players tab"""
    return redirect(url_for("main.admin_panel", section="players"))


@auth_bp.route("/players/create", methods=["GET", "POST"])
@login_required
@gm_required
def create_player():
    """Create a new player (team selectable, defaults to session team)."""
    team_id = session.get("current_team_id")
    if not team_id:
        flash("No team selected.", "danger")
        return redirect(url_for("main.admin_panel", section="players"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip()

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect(url_for("main.admin_panel", section="players"))

        requested_team_id = request.form.get("team_id", type=int)
        if requested_team_id and requested_team_id != team_id:
            team = Team.query.get(requested_team_id)
            if team is None:
                flash("Selected team does not exist.", "danger")
                return redirect(url_for("main.admin_panel", section="players"))
            if not current_app.config.get("LOGIN_DISABLED", False):
                allowed_ids = set(current_user.managed_team_ids or [])
                try:
                    allowed_ids |= {t.id for t in
                                    (current_user.assigned_teams or [])}
                except Exception:
                    pass
                if requested_team_id not in allowed_ids:
                    flash("You cannot add players to that team.", "danger")
                    return redirect(url_for("main.admin_panel", section="players"))
            team_id = team.id

        existing = Player.query.filter(
            (Player.name == name) | (Player.email == email)
        ).first()
        if existing:
            flash("A player with this name or email already exists.", "warning")
            return redirect(url_for("main.admin_panel", section="players"))

        player = Player(name=name, email=email, active=True, team_id=team_id)
        db.session.add(player)
        db.session.commit()
        flash(f"Player {name} added.", "success")
        return redirect(url_for("main.admin_panel", section="players"))

    return redirect(url_for("main.admin_panel", section="players"))


@auth_bp.route("/players/<int:player_id>/delete", methods=["POST"])
@login_required
@gm_required
def delete_player(player_id):
    """Delete a player"""
    player = Player.query.get_or_404(player_id)
    db.session.delete(player)
    db.session.commit()
    flash(f"Player {player.name} deleted.", "success")
    return redirect(url_for("main.admin_panel", section="players"))


@auth_bp.route("/players/<int:player_id>/update", methods=["POST"])
@login_required
@gm_required
def update_player(player_id):
    """Update player email and/or active status"""
    player = Player.query.get_or_404(player_id)

    if request.form.get("update_email") == "true":
        new_email = request.form.get("email", "").strip()
        if new_email and new_email != player.email:
            existing = Player.query.filter(
                Player.email == new_email, Player.id != player_id
            ).first()
            if existing:
                flash("Email already in use by another player.", "danger")
            else:
                player.email = new_email
                db.session.commit()
                flash(f"Player {player.name} email updated.", "success")

    if request.form.get("update_active") == "true":
        player.active = request.form.get("active") == "on"
        db.session.commit()
        flash(f"Player {player.name} updated.", "success")

    return redirect(url_for("main.admin_panel", section="players"))


@auth_bp.route("/settings/notifications", methods=["POST"])
@login_required
def update_notification_settings():
    VALID_CHANNELS = {"email", "whatsapp", "whatsapp_group", "both", "all"}
    channel = request.form.get("notification_channel", "email")
    if channel not in VALID_CHANNELS:
        channel = "email"
    phone   = request.form.get("whatsapp_phone", "").strip() or None
    user = User.query.get(current_user.id)
    user.notification_channel = channel
    user.whatsapp_phone = phone
    db.session.commit()
    flash("Notification preferences saved.", "success")
    return redirect(url_for("main.admin_panel", section="settings"))


@auth_bp.route("/admin/teams/<int:team_id>/whatsapp-groups", methods=["GET", "POST"])
@login_required
@gm_required
def manage_whatsapp_groups(team_id):
    team = Team.query.get_or_404(team_id)
    if (
        not current_app.config.get("LOGIN_DISABLED")
        and team.organization_id != current_user.organization_id
    ):
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            db.session.add(WhatsAppGroup(
                team_id=team_id,
                group_name=request.form["group_name"],
                group_wa_id=request.form["group_wa_id"].strip(),
            ))
        elif action == "toggle":
            g = WhatsAppGroup.query.get_or_404(request.form["group_id"])
            g.active = not g.active
        elif action == "delete":
            db.session.delete(WhatsAppGroup.query.get_or_404(request.form["group_id"]))
        db.session.commit()
        return redirect(url_for("auth.manage_whatsapp_groups", team_id=team_id))

    groups = (WhatsAppGroup.query
              .filter_by(team_id=team_id)
              .order_by(WhatsAppGroup.created_at)
              .all())
    return render_template("admin/whatsapp_groups.html", groups=groups, team=team)
