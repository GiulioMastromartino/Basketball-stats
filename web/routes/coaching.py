"""Coaching workflows API (Slice N2).

Read-only JSON endpoints under ``/coaching`` for the season planner,
drill suggester, and play-effectiveness v2, plus NL queries, play
suggestions, and development goals. Auditors may view; goal mutations
require GM or coach authority.
"""

from flask import Blueprint, jsonify, request, session
from flask_login import login_required

from web.decorators import team_access_required

coaching_bp = Blueprint("coaching", __name__, url_prefix="/coaching")


def _team_id():
    return session.get("current_team_id")


def _parse_season_id(raw, *, allow_all=True):
    """Validate a user-supplied season scope.

    Returns ``(value, error)`` where value is an int id or ``"ALL"``.
    Garbage can never reach a bare ``int()`` (no unhandled 500s), and
    ids are scoped to the session team (no cross-team probing).
    """
    from core.models import Season

    text = (raw or "").strip() if isinstance(raw, str) else raw
    if text in (None, ""):
        return "ALL", None
    if isinstance(text, str) and text.upper() == "ALL":
        if not allow_all:
            return None, (jsonify(
                {"error": "season_id is required here"}), 400)
        return "ALL", None
    try:
        sid = int(text)
    except (TypeError, ValueError):
        return None, (jsonify(
            {"error": "season_id must be an integer or ALL"}), 400)
    if Season.query.filter_by(id=sid, team_id=_team_id()).first() is None:
        return None, (jsonify({"error": "season not found"}), 404)
    return sid, None


def _season_id():
    """Legacy accessor (validated at each call site via _parse_season_id)."""
    return request.args.get("season_id", "ALL")


def _default_season():
    """Active season id, falling back to ALL (never merges years silently)."""
    from core.services.season_service import get_active_season

    try:
        active = get_active_season(_team_id())
    except Exception:
        active = None
    return active.id if active else "ALL"


@coaching_bp.route("/season-plan", methods=["GET"])
@login_required
@team_access_required
def season_plan():
    """Sept–June calendar with load flags for the session team.

    Defaults to the active season (explicit ``?season_id=ALL`` still
    available) so months from different years are never merged.
    """
    from core.season_plan import build_season_plan, games_per_month

    if "season_id" in request.args:
        season, err = _parse_season_id(request.args.get("season_id"))
        if err:
            return err
    else:
        season = _default_season()
    counts = games_per_month(_team_id(), season)
    plan = build_season_plan(counts, season_label=str(season))
    plan["season_id"] = season
    return jsonify(plan), 200


@coaching_bp.route("/drill-suggestions", methods=["GET"])
@login_required
@team_access_required
def drill_suggestions():
    """3 drills from the weakest Four Factor over recent games."""
    from core.aggregate_cache import cached_four_factors
    from core.drill_suggester import suggest_drills
    from core.models import Game

    try:
        last_n = int(request.args.get("last_n", 5))
    except (TypeError, ValueError):
        last_n = 5
    last_n = max(1, min(last_n, 20))
    game_type = request.args.get("game_type", "Season")

    query = Game.query.filter_by(team_id=_team_id())
    if game_type and game_type != "ALL":
        query = query.filter(Game.game_type == game_type)
    season, err = _parse_season_id(request.args.get("season_id", "ALL"))
    if err:
        return err
    if season != "ALL":
        query = query.filter(Game.season_id == season)
    games = query.order_by(Game.sort_date.desc()).limit(last_n).all()
    if not games:
        return jsonify({"weakest": None, "label": None, "drills": [],
                        "reason": "no games in scope"}), 200

    factors = cached_four_factors([g.id for g in games])
    result = suggest_drills(factors, zone=request.args.get("zone"))
    result["games_used"] = len(games)
    return jsonify(result), 200


@coaching_bp.route("/play-effectiveness", methods=["GET"])
@login_required
@team_access_required
def play_effectiveness_view():
    """PPP by play × quarter, with cold-play verdicts."""
    from core.play_effectiveness import play_effectiveness

    season, err = _parse_season_id(request.args.get("season_id", "ALL"))
    if err:
        return err
    rows = play_effectiveness(
        _team_id(),
        game_type=request.args.get("game_type", "ALL"),
        season_id=season,
    )
    return jsonify({"plays": rows, "count": len(rows)}), 200


@coaching_bp.route("/nl-query", methods=["POST"])
@login_required
@team_access_required
def nl_query():
    """Answer a natural-language coaching question (Slice N4).

    Body: ``{"query": "best lineup vs zone", "game_type": "Season"}``.
    """
    from core.nl_queries import answer_query

    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    game_type = data.get("game_type", "Season")
    return jsonify(answer_query(query, _team_id(), game_type)), 200


@coaching_bp.route("/play-suggestions", methods=["GET"])
@login_required
@team_access_required
def play_suggestions():
    """Rank plays for the current situation (Slice N4).

    Params: ``situation`` free text, ``quarter`` int, ``limit`` int.
    """
    from core.play_suggester import suggest_plays

    try:
        quarter = int(request.args["quarter"]) if "quarter" in request.args else None
    except (TypeError, ValueError):
        return jsonify({"error": "quarter must be an integer"}), 400
    try:
        limit = int(request.args.get("limit", 5))
    except (TypeError, ValueError):
        return jsonify({"error": "limit must be an integer"}), 400
    result = suggest_plays(
        _team_id(),
        situation=request.args.get("situation", ""),
        quarter=quarter,
        limit=max(1, min(limit, 20)),
        game_type=request.args.get("game_type", "ALL"),
    )
    return jsonify(result), 200


def _deny_auditor():
    from flask import jsonify as _jsonify
    from flask_login import current_user as _user
    if getattr(_user, "is_auditor", False):
        return _jsonify({"error": "Auditors have read-only access"}), 403
    return None


def _require_coach_or_gm():
    """Goal mutations need coaching authority (GM or coach, never auditor).

    The coach path is scoped to the session team: coaching Team A never
    authorizes mutations on Team B. The GM path stays organization-level.
    """
    from flask import jsonify as _jsonify
    from flask_login import current_user as _user
    if getattr(_user, "is_auditor", False):
        return _jsonify({"error": "Auditors have read-only access"}), 403
    if getattr(_user, "is_gm", False):
        return None
    try:
        from core.models import TeamAssignment
        coach = TeamAssignment.query.filter_by(
            user_id=getattr(_user, "id", None),
            team_id=_team_id(), is_coach=True).first()
    except Exception:
        coach = None
    if coach is None:
        return _jsonify({"error": "Coach or GM access required"}), 403
    return None


@coaching_bp.route("/dev-goals", methods=["GET"])
@login_required
@team_access_required
def list_dev_goals():
    """List development goals with live progress bars."""
    from core.dev_goals import goal_progress
    from core.models import DevelopmentGoal

    goals = DevelopmentGoal.query.filter_by(team_id=_team_id()).all()
    return jsonify({"goals": [goal_progress(g) for g in goals]}), 200


@coaching_bp.route("/dev-goals", methods=["POST"])
@login_required
@team_access_required
def create_dev_goal():
    """Create a development goal (GM/coach only)."""
    from core.dev_goals import DEFAULT_WINDOW, METRICS, goal_progress, validate_goal
    from core.models import DevelopmentGoal, db

    denied = _require_coach_or_gm()
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    player_name = (data.get("player_name") or "").strip()
    metric = (data.get("metric") or "").strip()
    target = data.get("target")
    window = data.get("window", DEFAULT_WINDOW)
    errors = validate_goal(player_name, metric, target, window)
    if errors:
        return jsonify({"error": "; ".join(errors),
                        "metrics": sorted(METRICS)}), 400
    goal = DevelopmentGoal(team_id=_team_id(), player_name=player_name,
                           metric=metric, target=float(target),
                           window=int(window))
    db.session.add(goal)
    db.session.commit()
    return jsonify(goal_progress(goal)), 201


@coaching_bp.route("/dev-goals/<int:goal_id>", methods=["DELETE"])
@login_required
@team_access_required
def delete_dev_goal(goal_id):
    """Delete a development goal (GM/coach only)."""
    from core.models import DevelopmentGoal, db

    denied = _require_coach_or_gm()
    if denied:
        return denied
    goal = DevelopmentGoal.query.filter_by(id=goal_id,
                                           team_id=_team_id()).first()
    if goal is None:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(goal)
    db.session.commit()
    return jsonify({"success": True, "id": goal_id}), 200
