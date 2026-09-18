"""
Health check endpoints for Kubernetes and container orchestration.
"""

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from core.models import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health/live", methods=["GET"])
def live():
    """Liveness probe – returns 200 to indicate the process is alive."""
    return jsonify({"status": "alive", "service": "basketball-stats"}), 200


@health_bp.route("/health/ready", methods=["GET"])
def ready():
    """Readiness probe – checks DB connectivity."""
    try:
        # Use raw SQL for a session-ping without ORM complexity
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ready", "database": "connected"}), 200
    except Exception as e:
        current_app.logger.error(f"Readiness check failed: {e}")
        return jsonify(
            {"status": "not ready", "database": "disconnected", "error": str(e)}
        ), 503


@health_bp.route("/health/sync", methods=["GET"])
def sync():
    """Sync-health probe for monitors (no auth — external metadata only).

    Returns 200 with ``{"status": "ok"}`` when every tracked championship
    checked in recently, else 503 with ``{"status": "stale"}`` so uptime
    monitors and the ``HoopsLabSyncStale`` Prometheus alert can fire.
    Per-championship detail lives behind login at
    ``/analytics/championship/sync-health``.
    """
    from core.sync_diff import sync_health_snapshot

    snapshot = sync_health_snapshot()
    champs = snapshot.get("championships", [])
    stale = [c["display_name"] or c["id"] for c in champs if c.get("stale")]
    error_count = sum(len(c.get("recent_errors") or []) for c in champs)
    if snapshot.get("error") and not champs:
        # Unauthenticated probe: log the detail, expose only the status.
        current_app.logger.error("sync probe failed: %s", snapshot["error"])
        return jsonify({"status": "unknown", "championships": 0,
                        "whatsapp": "unknown"}), 503
    from core.services.whatsapp_service import get_connection_state
    body = {"championships": len(champs),
            "whatsapp": get_connection_state()}
    if stale or error_count:
        return jsonify({"status": "stale", "stale": stale,
                        "error_count": error_count, **body}), 503
    return jsonify({"status": "ok", **body}), 200
