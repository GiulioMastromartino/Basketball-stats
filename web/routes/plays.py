from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from core.models import db, Play
import json

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

# --- API Endpoints ---

@plays_bp.route("/api/v1/plays/api/save-canvas", methods=["POST"])
@login_required
def save_canvas():
    """API to save play canvas data"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400

    play_id = data.get("play_id")
    metadata = data.get("metadata", {})
    canvas_json = data.get("canvas_json")

    name = metadata.get("name")
    play_type = metadata.get("play_type", "Offense")
    tags = metadata.get("tags", "")

    if not name:
        return jsonify({"success": False, "error": "Play name is required"}), 400

    try:
        if play_id:
            play = Play.query.get(play_id)
            if not play:
                return jsonify({"success": False, "error": "Play not found"}), 404
            
            # Update existing
            play.name = name
            play.play_type = play_type
            play.tags = tags
            if canvas_json:
                play.canvas_data = canvas_json
            
            db.session.commit()
            return jsonify({"success": True, "play_id": play.id, "message": "Updated"})
        
        else:
            # Create new
            play = Play(
                name=name,
                play_type=play_type,
                tags=tags,
                canvas_data=canvas_json,
                description="" # Optional
            )
            db.session.add(play)
            db.session.commit()
            return jsonify({"success": True, "play_id": play.id, "message": "Created"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@plays_bp.route("/api/v1/plays/api/load-canvas/<int:play_id>", methods=["GET"])
@login_required
def load_canvas(play_id):
    """API to load play canvas data"""
    play = Play.query.get(play_id)
    if not play:
        return jsonify({"success": False, "error": "Play not found"}), 404
    
    return jsonify({
        "success": True,
        "play_id": play.id,
        "metadata": {
            "name": play.name,
            "play_type": play.play_type,
            "tags": play.tags
        },
        "canvas_json": play.canvas_data
    })
