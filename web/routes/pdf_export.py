from flask import Blueprint, send_file, request, jsonify
from flask_login import login_required
from core.pdf_exports import PlaysBasedPDFGenerator
from core.models import Game, Player
from io import BytesIO

pdf_export_bp = Blueprint("pdf_export", __name__)

@pdf_export_bp.route("/api/pdf/game/<int:game_id>")
@login_required
def export_game_pdf(game_id):
    """Export professional game report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_game_report_pdf(game_id)
        
        game = Game.query.get_or_404(game_id)
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
def export_player_pdf(player_id):
    """Export professional player performance report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_player_report_pdf(player_id)
        
        player = Player.query.get_or_404(player_id)
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
