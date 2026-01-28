from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired

from core.models import User, db, bcrypt
from web.decorators import admin_required

auth_bp = Blueprint("auth", __name__)


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(url_for("main.index"))
        flash("Invalid username or password", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/users")
@login_required
@admin_required
def manage_users():
    """List all users for management"""
    users = User.query.order_by(User.username).all()
    return render_template("auth/manage_users.html", users=users)

@auth_bp.route("/users/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    """Admin-only user creation"""
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or Email already exists", "warning")
        else:
            hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
            # Auto-set is_admin for backward compatibility if role is admin
            is_admin_flag = (role == 'admin')
            
            new_user = User(
                username=username, 
                email=email, 
                password_hash=hashed_pw, 
                role=role,
                is_admin=is_admin_flag
            )
            db.session.add(new_user)
            db.session.commit()
            flash(f"User {username} created successfully.", "success")
            return redirect(url_for("auth.manage_users"))

    return render_template("auth/create_user.html")

@auth_bp.route("/users/<int:user_id>/change-password", methods=["GET", "POST"])
@login_required
@admin_required
def change_password(user_id):
    """Admin route to change any user's password"""
    user = User.query.get_or_404(user_id)
    
    if request.method == "POST":
        password = request.form.get("password")
        if not password:
            flash("Password cannot be empty", "danger")
        else:
            user.password_hash = bcrypt.generate_password_hash(password).decode("utf-8")
            db.session.commit()
            flash(f"Password for {user.username} updated successfully.", "success")
            return redirect(url_for("auth.manage_users"))
            
    return render_template("auth/change_password.html", user=user)

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
