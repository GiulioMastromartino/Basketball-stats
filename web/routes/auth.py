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
from core.services.workos_service import (
    get_auth_url,
    get_magic_link_url,
    authenticate_callback,
    create_workos_user,
    get_logout_url,
)
from core.logger import get_logger
from web.decorators import admin_required, gm_required

logger = get_logger("auth")

auth_bp = Blueprint("auth", __name__)


class EmptyForm(FlaskForm):
    """Empty form for CSRF protection"""

    submit = SubmitField("Sign In")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Redirect to WorkOS AuthKit for authentication"""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    redirect_uri = current_app.config.get(
        "WORKOS_REDIRECT_URI", "http://localhost:5000/auth/callback"
    )
    workos_configured = bool(
        current_app.config.get("WORKOS_API_KEY")
        and current_app.config.get("WORKOS_CLIENT_ID")
    )
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

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username and password:
            user = User.query.filter_by(username=username).first()
            if user and user.password_hash and user.check_password(password):
                if user.is_manager:
                    otp_code = f"{secrets.randbelow(1000000):06d}"
                    user.otp_code = otp_code
                    user.otp_expiry = datetime.utcnow() + timedelta(minutes=5)
                    db.session.commit()
                    session["otp_user_id"] = user.id
                    notify_otp(
                        user.email, otp_code,
                        whatsapp_phone=getattr(user, "whatsapp_phone", None)
                    )
                    flash("Verification code sent. Please check your email.", "info")
                    return redirect(url_for("auth.verify_otp"))

                login_user(user, remember=True)

                if not user.organization_id:
                    flash("Welcome! Please set up your organization to get started.", "info")
                    return redirect(url_for("auth.onboarding"))

                flash(f"Welcome back, {user.username}!", "success")
                return redirect(url_for("main.index"))

            flash("Invalid username or password", "danger")
            return render_template("auth/login.html", auth_url=auth_url, workos_configured=workos_configured, workos_error=workos_error)

        email = request.form.get("email")
        if email:
            try:
                magic_url = get_magic_link_url(email, redirect_uri)
                flash(f"Magic link sent to {email}. Check your inbox!", "info")
                return redirect(magic_url)
            except Exception as e:
                current_app.logger.warning(f"Magic link unavailable: {e}")
                flash("Magic link service unavailable. Try again later.", "danger")

    return render_template("auth/login.html", auth_url=auth_url, workos_configured=workos_configured, workos_error=workos_error)


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

        login_user(user, remember=True)

        # If user has no organization, redirect to onboarding
        if not user.organization_id:
            current_app.logger.info(
                "New WorkOS user has no org_id, redirecting to onboarding",
                extra={"extra_fields": {"user_id": user.id, "email": user.email}},
            )
            flash("Welcome! Please set up your organization to get started.", "info")
            return redirect(url_for("auth.onboarding"))

        # Ensure session has current team
        if not session.get("current_team_id"):
            teams = user.assigned_teams
            if teams:
                session["current_team_id"] = teams[0].id
                session["current_team_name"] = teams[0].name

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

        flash(f"Welcome to {org_name}! You are now a GM and coach.", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/onboarding.html")


@auth_bp.route("/logout")
@login_required
def logout():
    """Log out the user and redirect to WorkOS logout"""
    logout_user()
    session.pop("current_team_id", None)
    session.pop("current_team_name", None)
    flash("You have been logged out.", "info")
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
        login_user(user, remember=True)
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
    username = user.username
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
    """Invite flow (GM plan idea 3): create user + assignments in one POST."""
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
    is_gm = request.form.get("is_gm") == "on"
    is_coach = request.form.get("is_coach") == "on"
    raw_team_ids = request.form.getlist("team_ids")
    try:
        team_ids = [int(t) for t in raw_team_ids if str(t).strip()]
    except (TypeError, ValueError):
        team_ids = []
    teams = Team.query.filter(
        Team.id.in_(team_ids), Team.organization_id == org_id).all() if team_ids else []

    new_user = User(username=username, email=email, organization_id=org_id)
    new_user.set_password(secrets.token_urlsafe(12))
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
    flash(f"Invited {username} — assigned to {len(teams)} team(s).", "success")
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
    """Create a new player"""
    team_id = session.get("current_team_id")
    if not team_id:
        flash("No team selected.", "danger")
        return redirect(url_for("main.admin_panel", section="players"))

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")

        if not name or not email:
            flash("Name and email are required.", "danger")
            return redirect(url_for("main.admin_panel", section="players"))

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
