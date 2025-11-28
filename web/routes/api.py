#!/usr/bin/env python3
"""
REST API Routes
Provides JSON endpoints with pagination support
"""

import logging

from flask import Blueprint, jsonify, request
from flask_restx import Api, Resource, fields

from config import Config
from core.analytics import AdvancedAnalytics
from core.models import Game, PlayerStat, db

# Create blueprint
api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)

# Initialize API with documentation
api = Api(
    api_bp,
    version="1.0",
    title="Basketball Stats API",
    description="Advanced basketball statistics and analytics API",
    doc="/docs",
)

# Namespaces
ns_players = api.namespace("players", description="Player operations")
ns_team = api.namespace("team", description="Team operations")

# Models for documentation
game_model = api.model(
    "Game",
    {
        "id": fields.Integer(description="Game ID"),
        "date": fields.String(description="Game date"),
        "opponent": fields.String(description="Opponent team"),
        "result": fields.String(description="W/L/T"),
        "team_score": fields.Integer(description="Team score"),
        "opponent_score": fields.Integer(description="Opponent score"),
        "game_type": fields.String(description="Game type"),
    },
)


@ns_team.route("/games")
class TeamGames(Resource):
    """Team games list"""

    @ns_team.doc("list_games")
    def get(self):
        """Get all games"""
        try:
            games = Game.query.order_by(Game.sort_date.desc()).all()
            return [
                {
                    "id": g.id,
                    "date": g.date,
                    "opponent": g.opponent,
                    "result": g.result,
                    "score": g.score_display,
                    "game_type": g.game_type,
                }
                for g in games
            ]
        except Exception as e:
            logger.error(f"API Error: {e}")
            api.abort(500, str(e))


@ns_players.route("/")
class PlayerList(Resource):
    """Get all players"""

    @ns_players.doc("list_players")
    def get(self):
        """List all players"""
        try:
            # Get unique players
            players = db.session.query(PlayerStat.player_name).distinct().all()
            return [p[0] for p in players]
        except Exception as e:
            logger.error(f"API Error: {e}")
            api.abort(500, str(e))


@api.route("/health")
class HealthCheck(Resource):
    def get(self):
        return {"status": "healthy"}
