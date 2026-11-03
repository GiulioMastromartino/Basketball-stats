"""
Health check endpoints for Kubernetes and container orchestration.
"""

import os
from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from core.models import db
from config import get_config

health_bp = Blueprint("health", __name__)


def _instance_id():
    """Identify this app node: NODE_NAME:pid.

    Gunicorn preloads the factory in the master process and forks workers,
    so pid is read per-request so each worker reports its own pid. NODE_NAME
    comes from config (set per physical server via env var).
    """
    config = get_config()
    return f"{config.NODE_NAME}:{os.getpid()}"


@health_bp.route("/health/live", methods=["GET"])
def live():
    """Liveness probe – returns 200 to indicate the process is alive."""
    return jsonify(
        {"status": "alive", "service": "basketball-stats", "instance": _instance_id()}
    ), 200


@health_bp.route("/health/ready", methods=["GET"])
def ready():
    """Readiness probe – checks DB connectivity."""
    try:
        # Use raw SQL for a session-ping without ORM complexity
        db.session.execute(text("SELECT 1"))
        return jsonify(
            {
                "status": "ready",
                "database": "connected",
                "instance": _instance_id(),
            }
        ), 200
    except Exception as e:
        current_app.logger.error(f"Readiness check failed: {e}")
        return jsonify(
            {
                "status": "not ready",
                "database": "disconnected",
                "error": str(e),
                "instance": _instance_id(),
            }
        ), 503
