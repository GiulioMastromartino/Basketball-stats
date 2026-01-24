from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from core.models import db, Play

plays_bp = Blueprint("plays", __name__)

@plays_bp.route("/plays/")
@login_required
def list_plays():
    """List all plays"""
    plays = Play.query.order_by(Play.updated_at.desc()).all()
    return render_template("plays/list.html", plays=plays)

@plays_bp.route("/plays/create")
@login_required
def create_play():
    """Render the Play Builder for a new play"""
    return render_template("plays/create.html", play=None)

@plays_bp.route("/plays/<int:play_id>")
@login_required
def view_play(play_id):
    """View play details"""
    play = Play.query.get_or_404(play_id)
    # Sort sequences by sequence_number just in case
    play.sequences.sort(key=lambda x: x.sequence_number)
    return render_template("plays/detail.html", play=play)

@plays_bp.route("/plays/<int:play_id>/edit-builder")
@login_required
def edit_play_builder(play_id):
    """Render the Play Builder for an existing play"""
    play = Play.query.get_or_404(play_id)
    return render_template("plays/create.html", play=play)

@plays_bp.route("/plays/<int:play_id>/delete", methods=["POST"])
@login_required
def delete_play(play_id):
    play = Play.query.get_or_404(play_id)
    db.session.delete(play)
    db.session.commit()
    flash(f"Play '{play.name}' deleted.", "success")
    return redirect(url_for("plays.list_plays"))
