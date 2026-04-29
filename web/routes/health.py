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
