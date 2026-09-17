from datetime import date
from io import BytesIO
import json

from weasyprint import HTML
from werkzeug.utils import secure_filename

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    session,
    abort,
    send_file,
)
from flask_login import login_required, current_user
from core.models import (
    db, Play, Player, TrainingSession, TrainingSegment, TrainingAttendance,
    TrainingSegmentTemplate,
)
from web.decorators import admin_required, team_access_required

training_bp = Blueprint("training", __name__)

ATTENDANCE_STATUSES = ("present", "absent", "excused")

# Max animation phases shown per drill in the session PDF storyboard.
STORYBOARD_MAX_PHASES = 15


def _team_id():
    return session.get("current_team_id")


def _valid_iso_date(value: str) -> bool:
    """TrainingSession.session_date requires YYYY-MM-DD."""
    try:
        date.fromisoformat((value or "").strip())
        return True
    except (ValueError, TypeError):
        return False


@training_bp.route("/trainings/")
@login_required
@team_access_required
def list_sessions():
    """List training sessions, upcoming first."""
    sessions = (
        TrainingSession.query.filter_by(team_id=_team_id())
        .order_by(TrainingSession.session_date.desc(), TrainingSession.start_time.desc())
        .all()
    )
    today = date.today().isoformat()
    return render_template("trainings/list.html", sessions=sessions, today=today)


@training_bp.route("/trainings/new", methods=["POST"])
@login_required
@team_access_required
def create_session():
    title = (request.form.get("title") or "").strip()
    session_date = (request.form.get("session_date") or "").strip()
    if not title or not session_date:
        flash("Title and date are required", "danger")
        return redirect(url_for("training.list_sessions"))
    if not _valid_iso_date(session_date):
        flash("Date must be YYYY-MM-DD", "danger")
        return redirect(url_for("training.list_sessions"))
    ts = TrainingSession(
        team_id=_team_id(),
        title=title,
        session_date=session_date,
        start_time=(request.form.get("start_time") or "").strip() or None,
        location=(request.form.get("location") or "").strip() or None,
        focus=(request.form.get("focus") or "").strip() or None,
        notes=(request.form.get("notes") or "").strip() or None,
    )
    db.session.add(ts)
    db.session.commit()
    flash(f"Training '{title}' scheduled.", "success")
    return redirect(url_for("training.view_session", session_id=ts.id))


@training_bp.route("/trainings/<int:session_id>")
@login_required
@team_access_required
def view_session(session_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    plays = Play.query.filter_by(team_id=_team_id()).order_by(Play.name).all()
    templates = (
        TrainingSegmentTemplate.query.filter_by(team_id=_team_id())
        .order_by(TrainingSegmentTemplate.usage_count.desc(), TrainingSegmentTemplate.title)
        .all()
    )
    template_categories = sorted({t.category for t in templates if t.category})
    template_category_by_title = {t.title: (t.category or "") for t in templates}
    total_min = sum(s.duration_min or 0 for s in ts.segments)
    return render_template(
        "trainings/detail.html", ts=ts, plays=plays, total_min=total_min,
        statuses=ATTENDANCE_STATUSES, templates=templates,
        template_categories=template_categories,
        template_category_by_title=template_category_by_title,
    )


@training_bp.route("/trainings/<int:session_id>/pdf")
@login_required
@team_access_required
def export_session_pdf(session_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    total_min = sum(s.duration_min or 0 for s in ts.segments)
    attendance_counts = {status: 0 for status in ATTENDANCE_STATUSES}
    for att in ts.attendance:
        if att.status in attendance_counts:
            attendance_counts[att.status] += 1
    diagram_segments = [s for s in ts.segments if s.play and s.play.diagram_svg]
    storyboard = {}
    for s in diagram_segments:
        snaps = sorted(
            (q for q in s.play.sequences if q.svg_snapshot),
            key=lambda q: q.sequence_number,
        )
        if snaps:
            court = (s.play.court_type or "half").strip().lower()
            if court not in ("half", "full"):
                court = "half"
            storyboard[s.id] = {
                "frames": snaps[:STORYBOARD_MAX_PHASES], "total": len(snaps),
                "court": court,
            }
    html = render_template(
        "trainings/session_pdf.html", ts=ts, total_min=total_min,
        team_name=ts.team.name if ts.team else "",
        attendance_counts=attendance_counts,
        diagram_segments=diagram_segments,
        storyboard=storyboard,
        storyboard_max=STORYBOARD_MAX_PHASES,
        generated_date=date.today().isoformat(),
    )
    pdf = HTML(string=html).write_pdf()
    filename = secure_filename(f"Training_{ts.session_date}_{ts.title}") or f"Training_{ts.id}"
    response = send_file(
        BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
        download_name=f"{filename}.pdf",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


SESSION_FILE_VERSION = 1
SESSION_FILE_MAX_BYTES = 5 * 1024 * 1024


def _session_to_file_dict(ts):
    """Serialize a session (details, agenda, attendance) for file export."""
    return {
        "app": "basketball-stats",
        "kind": "training_session",
        "version": SESSION_FILE_VERSION,
        "session": {
            "title": ts.title,
            "session_date": ts.session_date,
            "start_time": ts.start_time,
            "location": ts.location,
            "focus": ts.focus,
            "notes": ts.notes,
            "post_notes": ts.post_notes,
            "segments": [
                {
                    "position": s.position,
                    "title": s.title,
                    "duration_min": s.duration_min,
                    "notes": s.notes,
                    "play": s.play.name if s.play else None,
                }
                for s in sorted(ts.segments, key=lambda s: (s.position or 0))
            ],
            "attendance": [
                {"player": a.player.name if a.player else None, "status": a.status}
                for a in ts.attendance
                if a.player is not None
            ],
        },
    }


def _validate_session_file_dict(data):
    """Validate an uploaded session file; return (session_dict, error)."""
    if not isinstance(data, dict):
        return None, "File must contain a JSON object"
    payload = data.get("session") if isinstance(data.get("session"), dict) else data
    title = payload.get("title") or ""
    if not isinstance(title, str) or not title.strip():
        return None, "Session file must contain a title"
    title = title.strip()
    if len(title) > 150:
        return None, "Session title must be 150 characters or fewer"
    session_date = payload.get("session_date") or ""
    if not isinstance(session_date, str) or not _valid_iso_date(session_date):
        return None, "Session file must contain a valid session_date (YYYY-MM-DD)"
    session_date = session_date.strip()
    segments = payload.get("segments", [])
    if not isinstance(segments, list):
        return None, "segments must be a list"
    clean_segments = []
    for seg in segments:
        if not isinstance(seg, dict):
            return None, "each segment must be an object"
        seg_title = seg.get("title") or ""
        if not isinstance(seg_title, str) or not seg_title.strip():
            return None, "each segment must contain a title"
        duration = seg.get("duration_min")
        if duration is not None:
            if isinstance(duration, bool) or not isinstance(duration, int):
                return None, f"segment '{seg_title.strip()}' has an invalid duration"
            if not 1 <= duration <= 480:
                return None, f"segment '{seg_title.strip()}' duration must be 1-480 minutes"
        play = seg.get("play")
        if play is not None and (not isinstance(play, str) or not play.strip()):
            return None, f"segment '{seg_title.strip()}' has an invalid play reference"
        clean_segments.append({
            "title": seg_title.strip(),
            "duration_min": duration,
            "notes": seg.get("notes") if isinstance(seg.get("notes"), str) else None,
            "play": play.strip() if isinstance(play, str) else None,
        })
    attendance = payload.get("attendance", [])
    if not isinstance(attendance, list):
        return None, "attendance must be a list"
    clean_attendance = []
    for att in attendance:
        if not isinstance(att, dict):
            return None, "each attendance entry must be an object"
        player = att.get("player") or ""
        if not isinstance(player, str) or not player.strip():
            return None, "each attendance entry must contain a player name"
        status = att.get("status") or "present"
        if status not in ATTENDANCE_STATUSES:
            return None, f"unknown attendance status '{status}' for '{player.strip()}'"
        clean_attendance.append({"player": player.strip(), "status": status})
    str_or_none = lambda v: v.strip() or None if isinstance(v, str) else None
    notes = payload.get("notes")
    post_notes = payload.get("post_notes")
    return {
        "title": title,
        "session_date": session_date,
        "start_time": str_or_none(payload.get("start_time")),
        "location": str_or_none(payload.get("location")),
        "focus": str_or_none(payload.get("focus")),
        "notes": notes if isinstance(notes, str) else None,
        "post_notes": post_notes if isinstance(post_notes, str) else None,
        "segments": clean_segments,
        "attendance": clean_attendance,
    }, None


@training_bp.route("/trainings/<int:session_id>/export")
@login_required
@team_access_required
def export_session_file(session_id):
    """Download a training session as a JSON file (details, agenda, attendance)."""
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    payload = _session_to_file_dict(ts)
    filename = secure_filename(f"Training_{ts.session_date}_{ts.title}") or f"Training_{ts.id}"
    response = send_file(
        BytesIO(json.dumps(payload, indent=2).encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"{filename}.json",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@training_bp.route("/trainings/import", methods=["POST"])
@login_required
@team_access_required
def import_session_file():
    """Import a training session from an exported JSON file."""
    if getattr(current_user, "is_auditor", False):
        flash("Auditors have read-only access.", "danger")
        return redirect(url_for("training.list_sessions"))
    team_id = _team_id()
    upload = request.files.get("session_file")
    if not upload or not (upload.filename or "").strip():
        flash("Select a session file to import", "danger")
        return redirect(url_for("training.list_sessions"))
    if not upload.filename.lower().endswith(".json"):
        flash("Session file must be a .json export", "danger")
        return redirect(url_for("training.list_sessions"))
    try:
        raw = upload.read(SESSION_FILE_MAX_BYTES + 1)
    except Exception:
        flash("Could not read the uploaded file", "danger")
        return redirect(url_for("training.list_sessions"))
    if len(raw) > SESSION_FILE_MAX_BYTES:
        flash("Session file is too large (max 5 MB)", "danger")
        return redirect(url_for("training.list_sessions"))
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        flash("Session file is not valid JSON", "danger")
        return redirect(url_for("training.list_sessions"))
    session_dict, error = _validate_session_file_dict(data)
    if error:
        flash(f"Invalid session file: {error}", "danger")
        return redirect(url_for("training.list_sessions"))
    ts = TrainingSession(
        team_id=team_id, title=session_dict["title"],
        session_date=session_dict["session_date"], start_time=session_dict["start_time"],
        location=session_dict["location"], focus=session_dict["focus"],
        notes=session_dict["notes"], post_notes=session_dict["post_notes"],
    )
    db.session.add(ts)
    db.session.flush()
    plays_by_name = {p.name: p for p in Play.query.filter_by(team_id=team_id).all()}
    players_by_name = {p.name: p for p in Player.query.filter_by(team_id=team_id).all()}
    unlinked_plays = set()
    for position, seg in enumerate(session_dict["segments"], start=1):
        play = plays_by_name.get(seg["play"]) if seg["play"] else None
        if seg["play"] and play is None:
            unlinked_plays.add(seg["play"])
        db.session.add(TrainingSegment(
            session_id=ts.id, position=position, title=seg["title"],
            duration_min=seg["duration_min"], play_id=play.id if play else None,
            notes=seg["notes"],
        ))
    linked, skipped_players = 0, set()
    seen_player_ids = set()
    for att in session_dict["attendance"]:
        player = players_by_name.get(att["player"])
        if player is None or player.id in seen_player_ids:
            if player is None:
                skipped_players.add(att["player"])
            continue
        seen_player_ids.add(player.id)
        db.session.add(TrainingAttendance(
            session_id=ts.id, player_id=player.id, status=att["status"]))
        linked += 1
    db.session.commit()
    summary = f"Session '{ts.title}' imported ({len(session_dict['segments'])} segments, {linked} attendance)."
    if unlinked_plays:
        summary += f" Plays not found: {', '.join(sorted(unlinked_plays))}."
    if skipped_players:
        summary += f" Players not found: {', '.join(sorted(skipped_players))}."
    flash(summary, "success")
    return redirect(url_for("training.view_session", session_id=ts.id))


@training_bp.route("/trainings/<int:session_id>/edit", methods=["POST"])
@login_required
@team_access_required
def edit_session(session_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    title = (request.form.get("title") or "").strip()
    session_date = (request.form.get("session_date") or "").strip()
    if not title or not session_date:
        flash("Title and date are required", "danger")
        return redirect(url_for("training.view_session", session_id=session_id))
    if not _valid_iso_date(session_date):
        flash("Date must be YYYY-MM-DD", "danger")
        return redirect(url_for("training.view_session", session_id=session_id))
    ts.title = title
    ts.session_date = session_date
    ts.start_time = (request.form.get("start_time") or "").strip() or None
    ts.location = (request.form.get("location") or "").strip() or None
    ts.focus = (request.form.get("focus") or "").strip() or None
    ts.notes = (request.form.get("notes") or "").strip() or None
    ts.post_notes = (request.form.get("post_notes") or "").strip() or None
    db.session.commit()
    flash("Training updated.", "success")
    return redirect(url_for("training.view_session", session_id=session_id))


@training_bp.route("/trainings/<int:session_id>/delete", methods=["POST"])
@login_required
@team_access_required
@admin_required
def delete_session(session_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    db.session.delete(ts)
    db.session.commit()
    flash(f"Training '{ts.title}' deleted.", "success")
    return redirect(url_for("training.list_sessions"))


def _upsert_segment_template(team_id, title, duration_min, play_id, notes, category=None):
    """Save a segment into the team library so it can be reused later."""
    tpl = TrainingSegmentTemplate.query.filter_by(team_id=team_id, title=title).first()
    if tpl:
        changed = False
        if duration_min is not None and tpl.duration_min != duration_min:
            tpl.duration_min = duration_min
            changed = True
        if play_id is not None and tpl.play_id != play_id:
            tpl.play_id = play_id
            changed = True
        if notes and tpl.notes != notes:
            tpl.notes = notes
            changed = True
        if category and tpl.category != category:
            tpl.category = category
            changed = True
        tpl.usage_count = (tpl.usage_count or 0) + 1
        return tpl, changed
    tpl = TrainingSegmentTemplate(
        team_id=team_id, title=title, duration_min=duration_min,
        play_id=play_id, notes=notes, category=category, usage_count=1,
    )
    db.session.add(tpl)
    return tpl, True


@training_bp.route("/trainings/<int:session_id>/segments/add", methods=["POST"])
@login_required
@team_access_required
def add_segment(session_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Segment title is required", "danger")
        return redirect(url_for("training.view_session", session_id=session_id))
    raw_duration = request.form.get("duration_min")
    if raw_duration in (None, ""):
        duration_min = None
    else:
        try:
            duration_min = int(str(raw_duration).strip())
        except (TypeError, ValueError):
            flash("Duration must be 1-480 minutes", "danger")
            return redirect(url_for("training.view_session", session_id=session_id))
        if duration_min < 1 or duration_min > 480:
            flash("Duration must be 1-480 minutes", "danger")
            return redirect(url_for("training.view_session", session_id=session_id))
    play_id = request.form.get("play_id") or None
    if play_id:
        try:
            play_id = int(play_id)
        except (TypeError, ValueError):
            play_id = None
        if play_id and not Play.query.filter_by(id=play_id, team_id=_team_id()).first():
            play_id = None
    position = (db.session.query(db.func.max(TrainingSegment.position))
                .filter_by(session_id=session_id).scalar() or 0) + 1
    seg = TrainingSegment(
        session_id=session_id, position=position, title=title,
        duration_min=duration_min, play_id=play_id,
        notes=(request.form.get("notes") or "").strip() or None,
    )
    db.session.add(seg)
    _upsert_segment_template(
        _team_id(), title, duration_min, play_id,
        (request.form.get("notes") or "").strip() or None,
        (request.form.get("category") or "").strip() or None,
    )
    db.session.commit()
    flash(f"Segment '{title}' added.", "success")
    return redirect(url_for("training.view_session", session_id=session_id))


@training_bp.route("/trainings/segments/<int:segment_id>/move", methods=["POST"])
@login_required
@team_access_required
def move_segment(segment_id):
    seg = TrainingSegment.query.get_or_404(segment_id)
    ts = TrainingSession.query.filter_by(id=seg.session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    direction = (request.form.get("direction") or "").strip().lower()
    if direction == "up":
        neighbor = (
            TrainingSegment.query.filter_by(session_id=seg.session_id)
            .filter(TrainingSegment.position < seg.position)
            .order_by(TrainingSegment.position.desc()).first()
        )
    elif direction == "down":
        neighbor = (
            TrainingSegment.query.filter_by(session_id=seg.session_id)
            .filter(TrainingSegment.position > seg.position)
            .order_by(TrainingSegment.position.asc()).first()
        )
    else:
        flash("Unknown direction", "danger")
        return redirect(url_for("training.view_session", session_id=ts.id))
    if neighbor:
        seg.position, neighbor.position = neighbor.position, seg.position
        db.session.commit()
        flash(f"Segment '{seg.title}' moved {direction}.", "success")
    return redirect(url_for("training.view_session", session_id=ts.id))


@training_bp.route("/trainings/segments/<int:segment_id>/edit", methods=["POST"])
@login_required
@team_access_required
def edit_segment(segment_id):
    seg = TrainingSegment.query.get_or_404(segment_id)
    ts = TrainingSession.query.filter_by(id=seg.session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    old_title = seg.title
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Segment title is required", "danger")
        return redirect(url_for("training.view_session", session_id=ts.id))
    raw_duration = request.form.get("duration_min")
    if raw_duration in (None, ""):
        duration_min = None
    else:
        try:
            duration_min = int(str(raw_duration).strip())
        except (TypeError, ValueError):
            flash("Duration must be 1-480 minutes", "danger")
            return redirect(url_for("training.view_session", session_id=ts.id))
        if duration_min < 1 or duration_min > 480:
            flash("Duration must be 1-480 minutes", "danger")
            return redirect(url_for("training.view_session", session_id=ts.id))
    play_id = request.form.get("play_id") or None
    if play_id:
        try:
            play_id = int(play_id)
        except (TypeError, ValueError):
            play_id = None
        if play_id and not Play.query.filter_by(id=play_id, team_id=_team_id()).first():
            play_id = None
    notes = (request.form.get("notes") or "").strip() or None
    category = (request.form.get("category") or "").strip() or None
    seg.title = title
    seg.duration_min = duration_min
    seg.play_id = play_id
    seg.notes = notes
    # keep the library in sync: refresh (or rename) the matching template
    tpl = TrainingSegmentTemplate.query.filter_by(
        team_id=_team_id(), title=old_title).first()
    conflict = (
        TrainingSegmentTemplate.query.filter_by(team_id=_team_id(), title=title).first()
        if title != old_title else None
    )
    if tpl and conflict is None:
        tpl.title = title
        if duration_min is not None:
            tpl.duration_min = duration_min
        if play_id is not None:
            tpl.play_id = play_id
        if notes:
            tpl.notes = notes
        if category:
            tpl.category = category
    elif tpl is None:
        _upsert_segment_template(_team_id(), title, duration_min, play_id, notes, category)
    db.session.commit()
    flash(f"Segment '{title}' updated.", "success")
    return redirect(url_for("training.view_session", session_id=ts.id))


@training_bp.route("/trainings/segments/<int:segment_id>/delete", methods=["POST"])
@login_required
@team_access_required
def delete_segment(segment_id):
    seg = TrainingSegment.query.get_or_404(segment_id)
    ts = TrainingSession.query.filter_by(id=seg.session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    db.session.delete(seg)
    db.session.commit()
    flash("Segment removed.", "success")
    return redirect(url_for("training.view_session", session_id=ts.id))


@training_bp.route("/trainings/<int:session_id>/templates/create", methods=["POST"])
@login_required
@team_access_required
def create_template(session_id):
    """Manually save a new reusable segment (not tied to a session agenda)."""
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Template title is required", "danger")
        return redirect(url_for("training.view_session", session_id=session_id))
    raw_duration = request.form.get("duration_min")
    duration_min = None
    if raw_duration not in (None, ""):
        try:
            duration_min = int(str(raw_duration).strip())
        except (TypeError, ValueError):
            duration_min = None
        if duration_min is not None and not (1 <= duration_min <= 480):
            flash("Duration must be 1-480 minutes", "danger")
            return redirect(url_for("training.view_session", session_id=session_id))
    tpl, _ = _upsert_segment_template(
        _team_id(), title, duration_min, None,
        (request.form.get("notes") or "").strip() or None,
        (request.form.get("category") or "").strip() or None,
    )
    db.session.commit()
    flash(f"Template '{title}' saved to library.", "success")
    return redirect(url_for("training.view_session", session_id=session_id))


@training_bp.route("/trainings/templates/<int:template_id>/delete", methods=["POST"])
@login_required
@team_access_required
def delete_template(template_id):
    tpl = TrainingSegmentTemplate.query.filter_by(
        id=template_id, team_id=_team_id()).first()
    if not tpl:
        abort(404)
    db.session.delete(tpl)
    db.session.commit()
    flash(f"Template '{tpl.title}' removed from library.", "success")
    return redirect(url_for("training.list_sessions"))


@training_bp.route("/trainings/<int:session_id>/templates/<int:template_id>/apply", methods=["POST"])
@login_required
@team_access_required
def apply_template(session_id, template_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    tpl = TrainingSegmentTemplate.query.filter_by(
        id=template_id, team_id=_team_id()).first()
    if not tpl:
        abort(404)
    position = (db.session.query(db.func.max(TrainingSegment.position))
                .filter_by(session_id=session_id).scalar() or 0) + 1
    seg = TrainingSegment(
        session_id=session_id, position=position, title=tpl.title,
        duration_min=tpl.duration_min, play_id=tpl.play_id, notes=tpl.notes,
    )
    db.session.add(seg)
    tpl.usage_count = (tpl.usage_count or 0) + 1
    db.session.commit()
    flash(f"Segment '{tpl.title}' added from library.", "success")
    return redirect(url_for("training.view_session", session_id=session_id))


@training_bp.route("/trainings/<int:session_id>/attendance/seed", methods=["POST"])
@login_required
@team_access_required
def seed_attendance(session_id):
    ts = TrainingSession.query.filter_by(id=session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    existing = {a.player_id for a in ts.attendance}
    players = Player.query.filter_by(team_id=_team_id(), active=True).order_by(Player.name).all()
    added = 0
    for p in players:
        if p.id not in existing:
            db.session.add(TrainingAttendance(session_id=session_id, player_id=p.id, status="present"))
            added += 1
    db.session.commit()
    flash(f"Roster loaded ({added} added).", "success")
    return redirect(url_for("training.view_session", session_id=session_id))


@training_bp.route("/trainings/attendance/<int:attendance_id>/status", methods=["POST"])
@login_required
@team_access_required
def set_attendance(attendance_id):
    att = TrainingAttendance.query.get_or_404(attendance_id)
    ts = TrainingSession.query.filter_by(id=att.session_id, team_id=_team_id()).first()
    if not ts:
        abort(404)
    status = (request.form.get("status") or "").strip()
    if status not in ATTENDANCE_STATUSES:
        flash("Unknown status", "danger")
        return redirect(url_for("training.view_session", session_id=ts.id))
    att.status = status
    db.session.commit()
    return redirect(url_for("training.view_session", session_id=ts.id))
