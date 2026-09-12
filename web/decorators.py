from functools import wraps
from flask import abort, flash, redirect, url_for, session, current_app
from flask_login import current_user

def _auth_disabled():
    return current_app.config.get("LOGIN_DISABLED", False)

def gm_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if _auth_disabled():
            return f(*args, **kwargs)
        if not current_user.is_authenticated or not current_user.is_gm:
            flash("You do not have permission to perform this action.", "danger")
            return redirect(url_for('main.index'))
        if getattr(current_user, "is_auditor", False):
            flash("Auditors have read-only access.", "danger")
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_view_required(f):
    """GM or read-only auditor may view admin pages; mutations stay GM-only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if _auth_disabled():
            return f(*args, **kwargs)
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('main.landing'))
        is_gm = bool(getattr(current_user, "is_gm", False))
        is_auditor = bool(getattr(current_user, "is_auditor", False))
        if not (is_gm or is_auditor):
            flash("You do not have permission to perform this action.", "danger")
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def team_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if _auth_disabled():
            return f(*args, **kwargs)
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('main.landing'))
        team_id = session.get('current_team_id')
        if not team_id:
            teams = current_user.assigned_teams
            if teams:
                team_id = teams[0].id
                session['current_team_id'] = team_id
                session['current_team_name'] = teams[0].name
            else:
                flash("You are not assigned to any team.", "danger")
                return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

admin_required = gm_required
