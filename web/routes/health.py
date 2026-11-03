"""
Health check endpoints for Kubernetes and container orchestration.
"""

import httpx
from flask import Blueprint, jsonify, current_app
from sqlalchemy import text
from core.models import db
from config import get_config

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


    return jsonify({"status": "ok", **body}), 200


@health_bp.route("/health/peers", methods=["GET"])
def peers():
    """Check health of all configured peer servers."""
    config = get_config()
    peer_urls = config.SERVER_URLS
    results = []

    for url in peer_urls:
        try:
            with httpx.Client(timeout=config.SYNC_TIMEOUT) as client:
                resp = client.get(f"{url.rstrip('/')}/health/live")
                results.append(
                    {
                        "server": url,
                        "status": "healthy" if resp.status_code == 200 else "unhealthy",
                        "status_code": resp.status_code,
                    }
                )
        except Exception as exc:
            results.append(
                {
                    "server": url,
                    "status": "unreachable",
                    "error": str(exc),
                }
            )

    healthy = sum(1 for r in results if r.get("status") == "healthy")
    return jsonify(
        {
            "status": "healthy" if healthy == len(results) else "degraded",
            "total": len(results),
            "healthy": healthy,
            "servers": results,
        }
    ), 200


@health_bp.route("/health/peers/<path:server_url>", methods=["GET"])
def peer(server_url):
    """Check health of a specific peer server."""
    config = get_config()
    full_url = server_url if "://" in server_url else f"http://{server_url}"

    if full_url not in config.SERVER_URLS:
        return jsonify(
            {"status": "error", "message": f"Server {full_url} not in configured peers"}
        ), 400

    try:
        with httpx.Client(timeout=config.SYNC_TIMEOUT) as client:
            resp = client.get(f"{full_url.rstrip('/')}/health/live")
            return jsonify(
                {
                    "server": full_url,
                    "status": "healthy" if resp.status_code == 200 else "unhealthy",
                    "status_code": resp.status_code,
                }
            ), 200
    except Exception as exc:
        return jsonify(
            {"server": full_url, "status": "unreachable", "error": str(exc)}
        ), 503
