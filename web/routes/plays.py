from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required
from core.models import db, Play, PlayType, PlaySequence
from web.decorators import admin_required
from werkzeug.utils import secure_filename
import os

plays_bp = Blueprint("plays", __name__)


# Alias routes for template compatibility
@plays_bp.route("/plays")
@login_required
def index():
    """Alias for list_plays - for template compatibility"""
    return list_plays()


@plays_bp.route("/plays/view/<int:play_id>")
@login_required
def view(play_id):
    """Alias for view_play - for template compatibility"""
    return view_play(play_id)


@plays_bp.route("/plays/add", methods=["POST"])
@login_required
def add():
    """Add a new play via form submission"""
    print(f"DEBUG: Entering add play route. Form: {request.form}")
    name = request.form.get("name")
    play_type = request.form.get("play_type", "Offense")
    description = request.form.get("description", "")
    
    if not name:
        print("DEBUG: Name missing")
        flash("Play name is required", "danger")
        return redirect(url_for("plays.list_plays"))
    
    # Check for duplicate name
    if Play.query.filter_by(name=name).first():
        print(f"DEBUG: Duplicate name {name}")
        flash(f"Play '{name}' already exists", "warning")
        return redirect(url_for("plays.list_plays"))
    
    try:
        play = Play(
            name=name,
            play_type=play_type,
            description=description
        )
        db.session.add(play)
        db.session.commit()
        print(f"DEBUG: Play {name} created with ID {play.id}")
    except Exception as e:
        print(f"DEBUG: Error creating play: {e}")
        db.session.rollback()
        raise
    
    flash(f"Play '{name}' created successfully", "success")
    return redirect(url_for("plays.view_play", play_id=play.id))


@plays_bp.route("/plays/edit/<int:play_id>", methods=["POST"])
@login_required
def edit(play_id):
    """Edit an existing play via form submission"""
    play = Play.query.get_or_404(play_id)
    
    name = request.form.get("name")
    play_type = request.form.get("play_type", play.play_type)
    description = request.form.get("description", play.description)
    
    if not name:
        flash("Play name is required", "danger")
        return redirect(url_for("plays.view_play", play_id=play_id))
    
    # Check for duplicate name (excluding current play)
    existing = Play.query.filter_by(name=name).first()
    if existing and existing.id != play_id:
        flash(f"Play '{name}' already exists", "warning")
        return redirect(url_for("plays.view_play", play_id=play_id))
    
    play.name = name
    play.play_type = play_type
    play.description = description
    db.session.commit()
    
    flash(f"Play '{name}' updated successfully", "success")
    return redirect(url_for("plays.view_play", play_id=play_id))


@plays_bp.route("/plays/delete/<int:play_id>", methods=["POST"])
@login_required
def delete(play_id):
    """Alias for delete_play - for template compatibility"""
    return delete_play(play_id)


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
@admin_required
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
@admin_required
def delete_play_type(type_id):
    play_type = PlayType.query.get_or_404(type_id)
    # Don't delete if used by plays (optional safety, or just let it default to something else)
    # For now, simplistic delete
    db.session.delete(play_type)
    db.session.commit()
    flash(f"Play Type '{play_type.name}' deleted.", "success")
    return redirect(url_for("plays.list_plays"))
