from datetime import datetime, timedelta
import os
from flask import (
    Blueprint,
    flash,
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

from core.models import User, SystemSetting, db, bcrypt
from core.services.workos_service import (
    get_auth_url,
    get_magic_link_url,
    authenticate_callback,
    create_workos_user,
    get_logout_url,
)
from web.decorators import admin_required

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

    if request.method == "POST":
        email = request.form.get("email")
        if email:
            auth_url = get_magic_link_url(email, redirect_uri)
            flash(f"Magic link sent to {email}. Check your inbox!", "info")
            return redirect(auth_url)

    auth_url = get_auth_url(redirect_uri)
    return render_template("auth/login.html", auth_url=auth_url)


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

                # Check if this is the admin email
                admin_email = os.getenv("ADMIN_EMAIL", "").lower()
                is_admin = admin_email and workos_user.email.lower() == admin_email

                user = User(
                    workos_id=workos_user.id,
                    email=workos_user.email,
                    username=username,
                    role="admin" if is_admin else "editor",
                    is_admin=is_admin,  # Legacy field
                    email_verified=True,
                    password_hash=None,
                )
                db.session.add(user)

            db.session.commit()

        login_user(user, remember=True)
        flash(f"Welcome, {user.username}!", "success")
        return redirect(url_for("main.index"))

    except Exception as e:
        current_app.logger.error(f"WorkOS authentication error: {e}")
        flash("Authentication failed. Please try again.", "danger")
        return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
@login_required
def logout():
    """Log out the user and redirect to WorkOS logout"""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/users")
@login_required
@admin_required
def manage_users():
    """List all users for management"""
    users = User.query.order_by(User.username).all()

    settings_data = SystemSetting.query.all()
    settings = {s.key: s.value for s in settings_data}

    return render_template("auth/manage_users.html", users=users, settings=settings)


@auth_bp.route("/settings/update", methods=["POST"])
@login_required
@admin_required
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

        flash("System settings updated.", "success")
    except Exception as e:
        flash(f"Error updating settings: {e}", "danger")

    return redirect(url_for("auth.manage_users"))


@auth_bp.route("/users/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    """Admin-only user creation via WorkOS"""
    if request.method == "POST":
        email = request.form.get("email")
        role = request.form.get("role", "editor")

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
                role=role,
                email_verified=False,
                password_hash=None,
            )
            db.session.add(new_user)
            db.session.commit()

            flash(f"User {email} created. An invitation has been sent.", "success")
            return redirect(url_for("auth.manage_users"))

        except Exception as e:
            current_app.logger.error(f"Failed to create WorkOS user: {e}")
            flash(f"Failed to create user: {str(e)}", "danger")
            return render_template("auth/create_user.html")

    return render_template("auth/create_user.html")


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user account"""
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("auth.manage_users"))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.username} deleted.", "success")
    return redirect(url_for("auth.manage_users"))


@auth_bp.route("/users/<int:user_id>/role", methods=["POST"])
@login_required
@admin_required
def change_role(user_id):
    """Change a user's role"""
    if user_id == current_user.id:
        flash("You cannot change your own role.", "danger")
        return redirect(url_for("auth.manage_users"))

    user = User.query.get_or_404(user_id)
    new_role = request.form.get("role")

    if new_role not in ["admin", "editor", "viewer"]:
        flash("Invalid role.", "danger")
        return redirect(url_for("auth.manage_users"))

    user.role = new_role
    user.is_admin = new_role == "admin"
    db.session.commit()

    flash(f"Role for {user.username} updated to {new_role}.", "success")
    return redirect(url_for("auth.manage_users"))
