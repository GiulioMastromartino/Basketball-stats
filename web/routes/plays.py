from flask import Blueprint, render_template
from flask_login import login_required

plays_bp = Blueprint('plays', __name__)

@plays_bp.route('/play-builder')
@login_required
def play_builder():
    """Render the Play Builder interface"""
    return render_template('play_builder.html')
