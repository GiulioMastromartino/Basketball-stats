"""
Merged API v1 routes.
Combines routes from legacy api.py and play_builder_api.py under a single blueprint.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required
from core.models import Play, db

api_v1_bp = Blueprint("api_v1", __name__)


@api_v1_bp.route("/plays", methods=["GET"])
@login_required
def get_plays():
    """Get all plays, optionally filtered by type"""
    play_type = request.args.get("type", "All")

    if play_type == "All":
        plays = Play.query.order_by(Play.play_type, Play.name).all()
    else:
        plays = Play.query.filter_by(play_type=play_type).order_by(Play.name).all()

    return jsonify(
        [
            {
                "id": p.id,
                "name": p.name,
                "type": p.play_type,
                "description": p.description,
            }
            for p in plays
        ]
    )


@api_v1_bp.route("/plays/types", methods=["GET"])
@login_required
def get_play_types():
    """Get unique play types"""
    play_types = (
        db.session.query(Play.play_type).distinct().order_by(Play.play_type).all()
    )
    return jsonify([pt[0] for pt in play_types])


@api_v1_bp.route("/plays/api/save-canvas", methods=["POST"])
@login_required
def save_canvas():
    """
    Save the play metadata, canvas JSON, SVG preview, and animation frames.
    Expected JSON payload:
    {
        "play_id": <int> (optional, if update),
        "metadata": { ... },
        "canvas_json": <dict>,
        "diagram_svg": <str>,
        "frames": [ ... ]
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

    # Save SVG preview if provided
    if "diagram_svg" in payload:
        play.diagram_svg = payload["diagram_svg"]

    # Commit play first to get ID for sequences
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

    # Handle animation frames (sequences)
    frames = payload.get("frames", [])

    if frames:
        try:
            # Delete existing sequences
            from core.models import PlaySequence

            PlaySequence.query.filter_by(play_id=play.id).delete()

            # Create new sequences
            for idx, frame in enumerate(frames):
                sequence = PlaySequence(
                    play_id=play.id,
                    sequence_number=idx + 1,
                    element_data=frame.get("data"),
                    caption=frame.get("caption", f"Frame {idx + 1}"),
                )
                db.session.add(sequence)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify(
                {"success": False, "error": f"Sequence save failed: {str(e)}"}
            ), 500

    return jsonify(
        {"success": True, "play_id": play.id, "message": "Play saved successfully"}
    )


@api_v1_bp.route("/plays/api/load-canvas/<int:play_id>", methods=["GET"])
@login_required
def load_canvas(play_id):
    """
    Return the canvas JSON, metadata, and animation frames for a given play.
    """
    play = Play.query.get_or_404(play_id)

    # Load sequences
    from core.models import PlaySequence

    sequences = (
        PlaySequence.query.filter_by(play_id=play.id)
        .order_by(PlaySequence.sequence_number)
        .all()
    )

    frames = []
    for seq in sequences:
        frames.append({"id": seq.id, "data": seq.element_data, "caption": seq.caption})

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
            "updated_at": play.updated_at.isoformat(),
        },
        "canvas_json": play.canvas_data,
        "frames": frames,
    }

    return jsonify(response)
