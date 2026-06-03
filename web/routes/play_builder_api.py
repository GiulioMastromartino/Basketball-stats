"""
API routes for the Play Builder (Canvas-based)
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

# Create the blueprint
builder_api_bp = Blueprint('builder_api', __name__)

# Temporary in-memory storage for demonstration (or use a simple JSON file/DB model)
# In a real app, you'd likely use a dedicated 'PlayCanvas' model in the database.
# For now, we'll just mock the persistence to satisfy the route requirements.
_canvas_storage = {}

@builder_api_bp.route('/plays/api/save-canvas', methods=['POST'])
@login_required
def save_canvas():
    """
    Save the canvas state for a play.
    Expected JSON payload: { 'play_id': <int>, 'canvas_data': <json_object> }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    play_id = data.get('play_id')
    canvas_data = data.get('canvas_data')
    
    if not play_id:
        return jsonify({"error": "Missing play_id"}), 400

    # Store the data (using stringified key for simplicity in dict)
    _canvas_storage[str(play_id)] = canvas_data
    
    return jsonify({
        "message": "Canvas saved successfully",
        "play_id": play_id
    }), 200


@builder_api_bp.route('/plays/api/load-canvas/<play_id>', methods=['GET'])
@login_required
def load_canvas(play_id):
    """
    Load the canvas state for a specific play_id.
    """
    # Retrieve from storage
    canvas_data = _canvas_storage.get(str(play_id))
    
    if canvas_data is None:
        # Return empty structure or 404 depending on preference.
        # Returning empty object usually safer for frontend initialization.
        return jsonify({
            "play_id": play_id,
            "canvas_data": None,
            "message": "No canvas data found for this play"
        }), 200
        
    return jsonify({
        "play_id": play_id,
        "canvas_data": canvas_data
    }), 200
