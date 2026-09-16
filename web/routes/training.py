from datetime import date

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
    session,
    abort,
)
from flask_login import login_required
from core.models import db, Play, Player, TrainingSession, TrainingSegment, TrainingAttendance
from web.decorators import admin_required, team_access_required

training_bp = Blueprint("training", __name__)

ATTENDANCE_STATUSES = ("present", "absent", "excused")


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
    total_min = sum(s.duration_min or 0 for s in ts.segments)
    return render_template(
        "trainings/detail.html", ts=ts, plays=plays, total_min=total_min,
        statuses=ATTENDANCE_STATUSES,
    )


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
    db.session.commit()
    flash(f"Segment '{title}' added.", "success")
    return redirect(url_for("training.view_session", session_id=session_id))


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
