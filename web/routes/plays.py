from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    current_app,
    session,
    abort,
)
from flask_login import current_user, login_required
from core.models import db, Play, PlayType, PlaySequence
from web.decorators import admin_required, team_access_required
from werkzeug.utils import secure_filename
import os

plays_bp = Blueprint("plays", __name__)


def _court_svg_inner():
    """Inner markup of the shared halfcourt asset (single source of truth).

    The 500x470 court from the live-game shot-location popup, saved as
    static/images/halfcourt.svg. The builder editor, SVG export, and detail
    preview all reuse it instead of copy-pasted courts.
    Returns "" when the file is missing (callers fall back gracefully).
    """
    try:
        path = os.path.join(current_app.static_folder, "images", "halfcourt.svg")
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        start = svg.find(">") + 1
        end = svg.rfind("</svg>")
        if start > 0 and end > start:
            return svg[start:end].strip()
    except OSError:
        pass
    return ""


def _court_svg_full():
    """Whole halfcourt file (for inline <svg> embedding in the editor)."""
    try:
        path = os.path.join(current_app.static_folder, "images", "halfcourt.svg")
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _court_bg_data_uri():
    """Halfcourt asset as an inline data-URI for the editor CSS background.

    Same file as _court_svg_inner (single source of truth), inlined so the
    background paints with no subresource request. Fully URL-encoded:
    WebKit (Safari, DuckDuckGo) refuses data-URI SVG with raw <>" chars,
    which is why the court flashed then vanished there.
    """
    import urllib.parse

    try:
        path = os.path.join(current_app.static_folder, "images", "halfcourt.svg")
        with open(path, encoding="utf-8") as f:
            svg = f.read()
        one_line = " ".join(svg.split())
        return "data:image/svg+xml;utf8," + urllib.parse.quote(one_line, safe="")
    except OSError:
        return ""


# Alias routes for template compatibility
@plays_bp.route("/plays")
@login_required
@team_access_required
def index():
    """Alias for list_plays - for template compatibility"""
    return list_plays()


@plays_bp.route("/plays/view/<int:play_id>")
@login_required
@team_access_required
def view(play_id):
    """Alias for view_play - for template compatibility"""
    return view_play(play_id)


@plays_bp.route("/plays/add", methods=["POST"])
@login_required
@team_access_required
def add():
    """Add a new play via form submission"""
    name = request.form.get("name")
    play_type = request.form.get("play_type", "Offense")
    description = request.form.get("description", "")

    if not name:
        flash("Play name is required", "danger")
        return redirect(url_for("plays.list_plays"))

    # Check for duplicate name
    if Play.query.filter_by(name=name, team_id=session.get('current_team_id')).first():
        flash(f"Play '{name}' already exists", "warning")
        return redirect(url_for("plays.list_plays"))

    play = Play(name=name, play_type=play_type, description=description, team_id=session.get('current_team_id'))
    db.session.add(play)
    db.session.commit()

    flash(f"Play '{name}' created successfully", "success")
    return redirect(url_for("plays.view_play", play_id=play.id))


@plays_bp.route("/plays/edit/<int:play_id>", methods=["POST"])
@login_required
@team_access_required
def edit(play_id):
    """Edit an existing play via form submission"""
    play = Play.query.filter_by(id=play_id, team_id=session.get('current_team_id')).first()
    if not play:
        abort(404)

    name = request.form.get("name")
    play_type = request.form.get("play_type", play.play_type)
    description = request.form.get("description", play.description)

    if not name:
        flash("Play name is required", "danger")
        return redirect(url_for("plays.view_play", play_id=play_id))

    # Check for duplicate name (excluding current play)
    existing = Play.query.filter_by(name=name, team_id=session.get('current_team_id')).first()
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
@team_access_required
def delete(play_id):
    """Alias for delete_play - for template compatibility"""
    return delete_play(play_id)


@plays_bp.route("/plays/")
@login_required
@team_access_required
def list_plays():
    """List all plays"""
    plays = Play.query.filter_by(team_id=session.get('current_team_id')).order_by(Play.updated_at.desc()).all()
    play_types = PlayType.query.filter_by(team_id=session.get('current_team_id')).order_by(PlayType.name).all()
    return render_template("plays/list.html", plays=plays, play_types=play_types)


@plays_bp.route("/plays/create")
@login_required
@team_access_required
def create_play():
    """Render the Play Builder for a new play"""
    play_types = PlayType.query.filter_by(team_id=session.get('current_team_id')).order_by(PlayType.name).all()
    return render_template("plays/create.html", play=None, play_types=play_types,
                           court_svg_inner=_court_svg_inner(),
                           court_bg_uri=_court_bg_data_uri(),
                           court_svg_full=_court_svg_full())


@plays_bp.route("/plays/<int:play_id>")
@login_required
@team_access_required
def view_play(play_id):
    """View play details"""
    play = Play.query.filter_by(id=play_id, team_id=session.get('current_team_id')).first()
    if not play:
        abort(404)
    # Sort sequences by sequence_number just in case
    play.sequences.sort(key=lambda x: x.sequence_number)
    return render_template("plays/detail.html", play=play,
                           court_svg_inner=_court_svg_inner())


@plays_bp.route("/plays/<int:play_id>/edit-builder")
@login_required
@team_access_required
def edit_play_builder(play_id):
    """Render the Play Builder for an existing play"""
    play = Play.query.filter_by(id=play_id, team_id=session.get('current_team_id')).first()
    if not play:
        abort(404)
    play_types = PlayType.query.filter_by(team_id=session.get('current_team_id')).order_by(PlayType.name).all()
    return render_template("plays/create.html", play=play, play_types=play_types,
                           court_svg_inner=_court_svg_inner(),
                           court_bg_uri=_court_bg_data_uri(),
                           court_svg_full=_court_svg_full())


@plays_bp.route("/plays/<int:play_id>/delete", methods=["POST"])
@login_required
@team_access_required
@admin_required
def delete_play(play_id):
    play = Play.query.filter_by(id=play_id, team_id=session.get('current_team_id')).first()
    if not play:
        abort(404)
    db.session.delete(play)
    db.session.commit()
    flash(f"Play '{play.name}' deleted.", "success")
    return redirect(url_for("plays.list_plays"))


@plays_bp.route("/plays/clear-all", methods=["POST"])
@login_required
@team_access_required
@admin_required
def clear_all_plays():
    """Delete all plays from the database"""
    try:
        PlaySequence.query.delete()
        num_deleted = Play.query.filter_by(team_id=session.get('current_team_id')).delete(synchronize_session=False)
        db.session.commit()
        flash(f"Deleted {num_deleted} plays.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error clearing plays: {str(e)}", "danger")
    return redirect(url_for("plays.list_plays"))


@plays_bp.route("/plays/<int:play_id>/type", methods=["PATCH"])
@login_required
@team_access_required
def set_play_type(play_id):
    """Re-file a play into another section (drag-and-drop in the library)."""
    if getattr(current_user, "is_auditor", False):
        return jsonify({"error": "Auditors have read-only access"}), 403
    team_id = session.get('current_team_id')
    play = Play.query.filter_by(id=play_id, team_id=team_id).first()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("play_type") or "").strip()
    if not name or len(name) > 50:
        return jsonify({"error": "play_type must be a non-empty name"}), 400
    known = {
        pt.name
        for pt in PlayType.query.filter_by(team_id=team_id).all()
    }
    if name not in known:
        return jsonify({"error": "Unknown play type"}), 400
    play.play_type = name
    db.session.commit()
    return jsonify({"id": play.id, "play_type": play.play_type}), 200


@plays_bp.route("/plays/types/add", methods=["POST"])
@login_required
@team_access_required
def add_play_type():
    name = request.form.get("name")
    if name:
        if not PlayType.query.filter_by(name=name, team_id=session.get('current_team_id')).first():
            db.session.add(PlayType(name=name, team_id=session.get('current_team_id')))
            db.session.commit()
            flash(f"Play Type '{name}' added.", "success")
        else:
            flash(f"Play Type '{name}' already exists.", "warning")
    return redirect(url_for("plays.list_plays"))


@plays_bp.route("/plays/types/<int:type_id>/delete", methods=["POST"])
@login_required
@team_access_required
@admin_required
def delete_play_type(type_id):
    play_type = PlayType.query.filter_by(id=type_id, team_id=session.get('current_team_id')).first()
    if not play_type:
        abort(404)
    # Don't delete if used by plays (optional safety, or just let it default to something else)
    # For now, simplistic delete
    db.session.delete(play_type)
    db.session.commit()
    flash(f"Play Type '{play_type.name}' deleted.", "success")
    return redirect(url_for("plays.list_plays"))
