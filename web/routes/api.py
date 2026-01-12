from flask import Blueprint, jsonify, request
from flask_login import login_required
from core.models import Play, db

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/plays', methods=['GET'])
@login_required
def get_plays():
    """Get all plays, optionally filtered by type"""
    play_type = request.args.get('type', 'All')
    
    if play_type == 'All':
        plays = Play.query.order_by(Play.play_type, Play.name).all()
    else:
        plays = Play.query.filter_by(play_type=play_type).order_by(Play.name).all()
    
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'type': p.play_type,
            'description': p.description
        }
        for p in plays
    ])


@api_bp.route('/plays/types', methods=['GET'])
@login_required
def get_play_types():
    """Get unique play types"""
    play_types = db.session.query(Play.play_type).distinct().order_by(Play.play_type).all()
    return jsonify([pt[0] for pt in play_types])
