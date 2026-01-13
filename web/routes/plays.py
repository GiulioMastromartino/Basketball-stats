from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
import os

from core.models import Play, db

plays_bp = Blueprint('plays', __name__, url_prefix='/plays')

# Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
UPLOAD_FOLDER = 'web/static/uploads/plays'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@plays_bp.route('/', methods=['GET'])
def index():
    """List all plays with filtering by type."""
    play_type = request.args.get('type', 'All')
    
    if play_type == 'All':
        plays = Play.query.order_by(Play.play_type, Play.name).all()
    else:
        plays = Play.query.filter_by(play_type=play_type).order_by(Play.name).all()
    
    # Get unique play types for filter
    play_types = db.session.query(Play.play_type).distinct().all()
    play_types = [pt[0] for pt in play_types]
    
    return render_template('plays/index.html', plays=plays, play_types=play_types, current_type=play_type)


@plays_bp.route('/<int:play_id>', methods=['GET'])
def view(play_id):
    """View detailed play information."""
    play = Play.query.get_or_404(play_id)
    return render_template('plays/view.html', play=play)


@plays_bp.route('/add', methods=['POST'])
def add():
    """Add a new play."""
    try:
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        play_type = request.form.get('play_type', 'Offense')
        
        if not name:
            flash('Play name is required', 'error')
            return redirect(url_for('plays.index'))
        
        # Check if play already exists
        if Play.query.filter_by(name=name).first():
            flash(f'Play "{name}" already exists', 'warning')
            return redirect(url_for('plays.index'))
        
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                image_filename = filename
        
        play = Play(
            name=name,
            description=description,
            play_type=play_type,
            image_filename=image_filename
        )
        
        db.session.add(play)
        db.session.commit()
        
        flash(f'Play "{name}" added successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding play: {str(e)}', 'error')
    
    return redirect(url_for('plays.index'))


@plays_bp.route('/<int:play_id>/edit', methods=['POST'])
def edit(play_id):
    """Edit an existing play."""
    play = Play.query.get_or_404(play_id)
    
    try:
        play.name = request.form.get('name', play.name).strip()
        play.description = request.form.get('description', play.description).strip()
        play.play_type = request.form.get('play_type', play.play_type)
        
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                # Delete old image if exists
                if play.image_filename:
                    old_path = os.path.join(UPLOAD_FOLDER, play.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                play.image_filename = filename
        
        db.session.commit()
        flash(f'Play "{play.name}" updated successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating play: {str(e)}', 'error')
    
    return redirect(url_for('plays.view', play_id=play_id))


@plays_bp.route('/<int:play_id>/delete', methods=['POST'])
def delete(play_id):
    """Delete a play."""
    play = Play.query.get_or_404(play_id)
    
    try:
        play_name = play.name
        
        # Delete associated image
        if play.image_filename:
            image_path = os.path.join(UPLOAD_FOLDER, play.image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)
        
        db.session.delete(play)
        db.session.commit()
        
        flash(f'Play "{play_name}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting play: {str(e)}', 'error')
    
    return redirect(url_for('plays.index'))


@plays_bp.route('/api/types', methods=['GET'])
def api_types():
    """Get available play types as JSON."""
    play_types = db.session.query(Play.play_type).distinct().order_by(Play.play_type).all()
    return jsonify([pt[0] for pt in play_types])


@plays_bp.route('/api/search', methods=['GET'])
def api_search():
    """Search plays by name or description."""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    plays = Play.query.filter(
        (Play.name.ilike(f'%{query}%')) |
        (Play.description.ilike(f'%{query}%'))
    ).order_by(Play.name).limit(10).all()
    
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'type': p.play_type
    } for p in plays])
