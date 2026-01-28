from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_manager:
            flash("You do not have permission to perform this action.", "danger")
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function
