from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from core.models import db, Play, PlayType

plays_bp = Blueprint("plays", __name__)

@plays_bp.route("/plays/")
@login_required
def list_plays():
    """List all plays"""
    plays = Play.query.order_by(Play.updated_at.desc()).all()
    play_types = PlayType.query.order_by(PlayType.name).all()
    return render_template("plays/list.html", plays=plays, play_types=play_types)

@plays_bp.route("/plays/create")
@login_required
def create_play():
    """Render the Play Builder for a new play"""
    play_types = PlayType.query.order_by(PlayType.name).all()
    return render_template("plays/create.html", play=None, play_types=play_types)

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
    play_types = PlayType.query.order_by(PlayType.name).all()
    return render_template("plays/create.html", play=play, play_types=play_types)

@plays_bp.route("/plays/<int:play_id>/delete", methods=["POST"])
@login_required
def delete_play(play_id):
    play = Play.query.get_or_404(play_id)
    db.session.delete(play)
    db.session.commit()
    flash(f"Play '{play.name}' deleted.", "success")
    return redirect(url_for("plays.list_plays"))

@plays_bp.route("/plays/types/add", methods=["POST"])
@login_required
def add_play_type():
    name = request.form.get("name")
    if name:
        if not PlayType.query.filter_by(name=name).first():
            db.session.add(PlayType(name=name))
            db.session.commit()
            flash(f"Play Type '{name}' added.", "success")
        else:
            flash(f"Play Type '{name}' already exists.", "warning")
    return redirect(url_for("plays.list_plays"))

@plays_bp.route("/plays/types/<int:type_id>/delete", methods=["POST"])
@login_required
def delete_play_type(type_id):
    play_type = PlayType.query.get_or_404(type_id)
    # Don't delete if used by plays (optional safety, or just let it default to something else)
    # For now, simplistic delete
    db.session.delete(play_type)
    db.session.commit()
    flash(f"Play Type '{play_type.name}' deleted.", "success")
    return redirect(url_for("plays.list_plays"))
