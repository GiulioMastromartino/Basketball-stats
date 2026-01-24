from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required
from core.models import db, Play
import json

plays_bp = Blueprint("plays", __name__)

@plays_bp.route("/plays")
@login_required
def index():
    """List all plays"""
    plays = Play.query.order_by(Play.updated_at.desc()).all()
    return render_template("plays/index.html", plays=plays)

@plays_bp.route("/plays/builder")
@login_required
def builder():
    """Play builder interface"""
    play_id = request.args.get("id")
    play = None
    if play_id:
        play = Play.query.get_or_404(play_id)
    return render_template("plays/create.html", play=play)

@plays_bp.route("/api/plays", methods=["GET"])
@login_required
def get_plays():
    """API to get plays"""
    plays = Play.query.order_by(Play.updated_at.desc()).all()
    return jsonify([p.to_dict() for p in plays])

@plays_bp.route("/api/plays/<int:play_id>", methods=["GET"])
@login_required
def get_play(play_id):
    """API to get a single play"""
    play = Play.query.get_or_404(play_id)
    return jsonify(play.to_dict())

@plays_bp.route("/api/plays", methods=["POST"])
@login_required
def create_play():
    """API to create a play"""
    data = request.get_json()
    
    if not data or not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
        
    play = Play(
        name=data["name"],
        description=data.get("description", ""),
        play_type=data.get("type", "Offense"),
        setup_data=json.dumps(data.get("setup_data", {}))
    )
    
    db.session.add(play)
    db.session.commit()
    
    return jsonify(play.to_dict()), 201

@plays_bp.route("/api/plays/<int:play_id>", methods=["PUT"])
@login_required
def update_play(play_id):
    """API to update a play"""
    play = Play.query.get_or_404(play_id)
    data = request.get_json()
    
    if "name" in data:
        play.name = data["name"]
    if "description" in data:
        play.description = data["description"]
    if "type" in data:
        play.play_type = data["type"]
    if "setup_data" in data:
        play.setup_data = json.dumps(data["setup_data"])
        
    db.session.commit()
    return jsonify(play.to_dict())

@plays_bp.route("/api/plays/<int:play_id>", methods=["DELETE"])
@login_required
def delete_play(play_id):
    """API to delete a play"""
    play = Play.query.get_or_404(play_id)
    db.session.delete(play)
    db.session.commit()
    return jsonify({"success": True})
