from flask import Blueprint, send_file, request, jsonify, session, abort
from flask_login import login_required
from web.decorators import team_access_required
from core.pdf_exports import PlaysBasedPDFGenerator
from core.models import Game, Player
from io import BytesIO

pdf_export_bp = Blueprint("pdf_export", __name__)

@pdf_export_bp.route("/api/pdf/game/<int:game_id>")
@login_required
@team_access_required
def export_game_pdf(game_id):
    """Export professional game report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_game_report_pdf(game_id)
        
        game = Game.query.filter_by(id=game_id, team_id=session.get('current_team_id')).first()
        if not game:
            abort(404)
        filename = f"Game_Report_{game.opponent.replace(' ', '_')}_{game.date}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@pdf_export_bp.route("/api/pdf/player/<int:player_id>")
@login_required
@team_access_required
def export_player_pdf(player_id):
    """Export professional player performance report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_player_report_pdf(player_id)
        
        player = Player.query.filter_by(id=player_id, team_id=session.get('current_team_id')).first()
        if not player:
            abort(404)
        filename = f"Player_Report_{player.name.replace(' ', '_')}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@pdf_export_bp.route("/api/pdf/team")
@login_required
@team_access_required
def export_team_pdf():
    """Export professional team-wide report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_team_report_pdf()
        
        filename = "Team_Statistical_Report.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
