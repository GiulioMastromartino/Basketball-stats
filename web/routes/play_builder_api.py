from flask import Blueprint, request, jsonify
from flask_login import login_required
from core.models import db, Play, PlaySequence

builder_api_bp = Blueprint("builder_api", __name__)

@builder_api_bp.route("/plays/api/save-canvas", methods=["POST"])
@login_required
def save_canvas():
    """
    Save the play metadata and canvas JSON.
    Expected JSON payload:
    {
        "play_id": <int> (optional, if update),
        "metadata": {
            "name": <str>,
            "description": <str>,
            "play_type": <str>,
            "difficulty": <str>,
            "personnel": <str>,
            "tags": <str>
        },
        "canvas_json": <dict> (FabricJS JSON object)
    }
    """
    payload = request.get_json()
    if not payload:
        return jsonify({"success": False, "error": "No data provided"}), 400

    metadata = payload.get("metadata", {})
    name = metadata.get("name")
    
    if not name:
        return jsonify({"success": False, "error": "Play name is required"}), 400

    play_id = payload.get("play_id")
    
    if play_id:
        # Update existing play
        play = Play.query.get(play_id)
        if not play:
            return jsonify({"success": False, "error": "Play not found"}), 404
        
        # Check unique name (exclude self)
        existing = Play.query.filter_by(name=name).first()
        if existing and existing.id != play.id:
            return jsonify({"success": False, "error": "Name already exists"}), 400
    else:
        # Create new play
        if Play.query.filter_by(name=name).first():
            return jsonify({"success": False, "error": "Name already exists"}), 400
        
        play = Play()
        db.session.add(play)

    # Update fields
    play.name = name
    play.description = metadata.get("description")
    play.play_type = metadata.get("play_type", "Offense")
    play.difficulty = metadata.get("difficulty", "Medium")
    play.personnel_required = metadata.get("personnel")
    play.tags = metadata.get("tags")
    play.canvas_data = payload.get("canvas_json")
    
    # Commit changes
    try:
        db.session.commit()
        return jsonify({
            "success": True, 
            "play_id": play.id, 
            "message": "Play saved successfully"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@builder_api_bp.route("/plays/api/load-canvas/<int:play_id>", methods=["GET"])
@login_required
def load_canvas(play_id):
    """
    Return the canvas JSON and metadata for a given play.
    """
    play = Play.query.get_or_404(play_id)
    
    response = {
        "success": True,
        "play_id": play.id,
        "metadata": {
            "name": play.name,
            "description": play.description,
            "play_type": play.play_type,
            "difficulty": play.difficulty,
            "personnel": play.personnel_required,
            "tags": play.tags,
            "created_at": play.created_at.isoformat(),
            "updated_at": play.updated_at.isoformat()
        },
        "canvas_json": play.canvas_data
    }
    
    return jsonify(response)
