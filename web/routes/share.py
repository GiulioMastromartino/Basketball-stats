"""Public read-only share links for games/players (no login required to view).

CREATE side (POST /share, DELETE /share/<id>): login + team-access required,
scoped to the session team. VIEW side (GET /s/<token>): no auth; 404 on
unknown/expired/revoked. JSON responses only; never leaks emails or notes.
"""

import secrets
from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file, session, url_for
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from core.models import Game, Player, PlayerStat, ShareLink, db
from web.decorators import team_access_required

share_bp = Blueprint("share", __name__)

MAX_EXPIRY_DAYS = 30
DEFAULT_EXPIRY_DAYS = 7


def _deny_auditor():
    """Auditors are read-only: block share-link mutations with JSON 403.

    (gm_required issues an HTML redirect, which is wrong for this JSON API —
    hence the explicit check following the repo's JSON-403 convention.)
    """
    if getattr(current_user, "is_auditor", False):
        return jsonify({"error": "Auditors have read-only access"}), 403
    return None


def _session_team_is_fresh():
    """Reject mutations when the session team is no longer assigned.

    team_access_required keeps a sticky session["current_team_id"]; if the
    TeamAssignment was removed afterwards, mutations must not use the stale id.
    Checked locally (not in the shared decorator) to avoid changing every
    route's behavior. Scoped to the active organization so a team assigned
    in another org cannot authorize mutations while a different org is active.
    """
    from flask import current_app

    if current_app.config.get("LOGIN_DISABLED", False):
        return True
    if not current_user.is_authenticated:
        return False
    team_id = session.get("current_team_id")
    if not team_id:
        return False
    active_org_id = (
        session.get("current_org_id")
        or getattr(current_user, "organization_id", None)
    )
    try:
        assigned = {
            t.id for t in (current_user.assigned_teams or [])
            if active_org_id is None
            or getattr(t, "organization_id", None) == active_org_id
        }
    except Exception:
        return False
    if team_id not in assigned:
        return False
    # The session team itself must belong to the active org.
    try:
        from core.models import Team
        team = Team.query.get(team_id)
        if team is None or (
            active_org_id is not None
            and getattr(team, "organization_id", None) != active_org_id
        ):
            return False
    except Exception:
        return False
    return True


def _generate_unique_token(max_attempts: int = 5) -> str:
    """Generate a collision-free token (secrets.token_urlsafe ~43 chars)."""
    for _ in range(max_attempts):
        token = secrets.token_urlsafe(32)
        if not ShareLink.query.filter_by(token=token).first():
            return token
    raise RuntimeError("Could not generate a unique share token")


def _serialize_game(game: Game) -> dict:
    stats = PlayerStat.query.filter_by(game_id=game.id).order_by(
        PlayerStat.player_name.asc()).all()
    return {
        "type": "game",
        "game": {
            "id": game.id,
            "date": game.date,
            "opponent": game.opponent,
            "team_score": game.team_score,
            "opponent_score": game.opponent_score,
            "result": game.result,
            "game_type": game.game_type,
        },
        "player_totals": [
            {
                "player_name": s.player_name,
                "points": s.points,
                "reb": s.reb,
                "ast": s.ast,
                "stl": s.stl,
                "blk": s.blk,
                "tov": s.tov,
                "minutes": s.minutes,
            }
            for s in stats
        ],
    }


def _serialize_player(player: Player) -> dict:
    rows = (
        PlayerStat.query.join(Game, PlayerStat.game_id == Game.id)
        .filter(Game.team_id == player.team_id,
                PlayerStat.player_name == player.name)
        .all()
    )
    games_played = len(rows)

    def _avg(field):
        if not rows:
            return 0.0
        return round(sum(getattr(r, field) or 0 for r in rows) / games_played, 1)

    return {
        "type": "player",
        "player": {
            "id": player.id,
            "name": player.name,
            "team_id": player.team_id,
        },
        "season_averages": {
            "games_played": games_played,
            "points": _avg("points"),
            "reb": _avg("reb"),
            "ast": _avg("ast"),
            "stl": _avg("stl"),
            "blk": _avg("blk"),
            "tov": _avg("tov"),
        },
    }


@share_bp.route("/share", methods=["POST"])
@login_required
@team_access_required
def create_share():
    denied = _deny_auditor()
    if denied:
        return denied
    if not _session_team_is_fresh():
        return jsonify({"error": "Team assignment changed, pick a team"}), 403
    team_id = session.get("current_team_id")
    if not team_id:
        return jsonify({"error": "No team context"}), 400
    data = request.get_json(silent=True) or {}
    target_type = (data.get("target_type") or "").strip().lower()
    target_id = data.get("target_id")
    expires_in_days = data.get("expires_in_days", DEFAULT_EXPIRY_DAYS)

    if target_type not in ("game", "player"):
        return jsonify({"error": "target_type must be 'game' or 'player'"}), 400
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        return jsonify({"error": "target_id must be an integer"}), 400
    try:
        expires_in_days = int(expires_in_days)
    except (TypeError, ValueError):
        return jsonify({"error": "expires_in_days must be an integer"}), 400
    if expires_in_days < 1 or expires_in_days > MAX_EXPIRY_DAYS:
        return jsonify(
            {"error": f"expires_in_days must be between 1 and {MAX_EXPIRY_DAYS}"}
        ), 400

    if target_type == "game":
        target = Game.query.filter_by(id=target_id, team_id=team_id).first()
    else:
        target = Player.query.filter_by(id=target_id, team_id=team_id).first()
    if target is None:
        return jsonify({"error": "Target not found"}), 404

    try:
        token = _generate_unique_token()
    except RuntimeError:
        return jsonify({"error": "Could not generate token, try again"}), 500

    link = ShareLink(
        team_id=team_id,
        target_type=target_type,
        target_id=target_id,
        token=token,
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        revoked=False,
        created_by=getattr(current_user, "id", None),
    )
    db.session.add(link)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Extremely rare token race: regenerate once more.
        link.token = _generate_unique_token()
        db.session.add(link)
        db.session.commit()

    return jsonify({
        "id": link.id,
        "token": link.token,
        "url": url_for("share.get_shared", token=link.token, _external=True),
        "target_type": link.target_type,
        "target_id": link.target_id,
        "expires_at": link.expires_at.isoformat(),
    }), 201


@share_bp.route("/s/<token>", methods=["GET"])
def get_shared(token):
    """Public read-only view. No auth. 404 on unknown/expired/revoked."""
    link = ShareLink.query.filter_by(token=token).first()
    if link is None or link.revoked or link.is_expired:
        return jsonify({"error": "Not found"}), 404

    if link.target_type == "game":
        game = Game.query.filter_by(
            id=link.target_id, team_id=link.team_id).first()
        if game is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_serialize_game(game)), 200

    if link.target_type == "player":
        player = Player.query.filter_by(
            id=link.target_id, team_id=link.team_id).first()
        if player is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(_serialize_player(player)), 200

    return jsonify({"error": "Not found"}), 404


@share_bp.route("/share/<int:link_id>", methods=["DELETE"])
@login_required
@team_access_required
def revoke_share(link_id):
    denied = _deny_auditor()
    if denied:
        return denied
    if not _session_team_is_fresh():
        return jsonify({"error": "Team assignment changed, pick a team"}), 403
    team_id = session.get("current_team_id")
    link = ShareLink.query.filter_by(id=link_id, team_id=team_id).first()
    if link is None:
        return jsonify({"error": "Not found"}), 404
    link.revoked = True
    db.session.commit()
    return jsonify({"success": True, "id": link.id, "revoked": True}), 200


def _team_name(team_id) -> str:
    from core.models import Team
    team = Team.query.get(team_id)
    return team.name if team else "Us"


@share_bp.route("/share/cards/game/<int:game_id>", methods=["GET"])
@login_required
@team_access_required
def game_score_card(game_id):
    """1080×1080 final-score PNG for a game (Slice N3)."""
    from core.social_cards import render_score_card

    game = Game.query.filter_by(id=game_id,
                                team_id=session.get("current_team_id")).first()
    if game is None:
        return jsonify({"error": "Not found"}), 404
    png = render_score_card(_team_name(game.team_id), game.opponent,
                            game.team_score, game.opponent_score,
                            date=game.date or "", result=game.result or "")
    from core.usage_meter import bump as _bump_usage
    _bump_usage("social_cards", team_id=game.team_id)
    return send_file(BytesIO(png), mimetype="image/png",
                     as_attachment=False,
                     download_name=f"score_{game_id}.png")


@share_bp.route("/share/cards/player/<int:player_id>", methods=["GET"])
@login_required
@team_access_required
def player_game_card(player_id):
    """1080×1080 "Player of the game" PNG (best scoring game)."""
    from core.social_cards import render_player_card

    team_id = session.get("current_team_id")
    player = Player.query.filter_by(id=player_id, team_id=team_id).first()
    if player is None:
        return jsonify({"error": "Not found"}), 404
    rows = (PlayerStat.query.join(Game, PlayerStat.game_id == Game.id)
            .filter(Game.team_id == team_id,
                    PlayerStat.player_name == player.name)
            .order_by(PlayerStat.points.desc()).all())
    best = rows[0] if rows else None
    stats = {"points": best.points, "reb": best.reb, "ast": best.ast,
             "stl": best.stl, "blk": best.blk} if best else {}
    game_date = best.game.date if best and best.game else ""
    png = render_player_card(player.name, _team_name(team_id),
                             stats=stats, date=game_date or "")
    return send_file(BytesIO(png), mimetype="image/png",
                     as_attachment=False,
                     download_name=f"player_{player_id}.png")


@share_bp.route("/share/comms-preview", methods=["POST"])
@login_required
@team_access_required
def comms_preview():
    """Preview a post-game comms template with merge tags (Slice N3).

    Body: ``{"template": "postgame_whatsapp", "game_id": 1}``.
    """
    from core.comms_templates import TEMPLATES, postgame_context, render

    data = request.get_json(silent=True) or {}
    name = (data.get("template") or "").strip()
    if name not in TEMPLATES:
        return jsonify({"error": "unknown template",
                        "templates": sorted(TEMPLATES)}), 400
    try:
        game_id = int(data.get("game_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "game_id must be an integer"}), 400
    team_id = session.get("current_team_id")
    game = Game.query.filter_by(id=game_id, team_id=team_id).first()
    if game is None:
        return jsonify({"error": "Not found"}), 404
    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    text = render(name, postgame_context(_team_name(team_id), game, stats))
    from core.usage_meter import bump as _bump_usage
    _bump_usage("comms_previews", team_id=team_id)
    return jsonify({"template": name, "text": text}), 200
