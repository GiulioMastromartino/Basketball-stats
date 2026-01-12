from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required
from core.models import Play, db
import os
from werkzeug.utils import secure_filename

plays_bp = Blueprint("plays", __name__)

@plays_bp.route("/plays")
@login_required
def index():
    """List all plays"""
    plays = Play.query.order_by(Play.name).all()
    return render_template("plays.html", plays=plays)

@plays_bp.route("/plays/add", methods=["POST"])
@login_required
def add_play():
    """Add a new play"""
    name = request.form.get("name")
    description = request.form.get("description")
    play_type = request.form.get("play_type", "Offense")
    
    if not name:
        flash("Play name is required.", "danger")
        return redirect(url_for("plays.index"))

    # Handle Image Upload
    image_filename = None
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename != "":
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(current_app.static_folder, "uploads", "plays")
            os.makedirs(upload_folder, exist_ok=True)
            file.save(os.path.join(upload_folder, filename))
            image_filename = filename

    try:
        new_play = Play(
            name=name,
            description=description,
            play_type=play_type,
            image_filename=image_filename
        )
        db.session.add(new_play)
        db.session.commit()
        flash(f"Added play: {name}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding play: {str(e)}", "danger")

    return redirect(url_for("plays.index"))

@plays_bp.route("/plays/<int:play_id>/delete", methods=["POST"])
@login_required
def delete_play(play_id):
    """Delete a play"""
    play = Play.query.get_or_404(play_id)
    try:
        db.session.delete(play)
        db.session.commit()
        flash(f"Deleted play: {play.name}", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting play: {str(e)}", "danger")
    
    return redirect(url_for("plays.index"))
