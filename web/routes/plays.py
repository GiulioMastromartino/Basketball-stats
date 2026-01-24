from flask import Blueprint, render_template, abort
from flask_login import login_required
from core.models import Play

plays_bp = Blueprint("plays", __name__)

@plays_bp.route("/plays/create", methods=["GET"])
@login_required
def create_page():
    """Render the empty builder page for a new play."""
    return render_template("plays/create.html", play=None)

@plays_bp.route("/plays/<int:play_id>/edit-builder", methods=["GET"])
@login_required
def edit_builder_page(play_id):
    """Render the builder page for an existing play."""
    play = Play.query.get_or_404(play_id)
    return render_template("plays/create.html", play=play)
