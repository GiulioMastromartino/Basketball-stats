"""PDF Export Routes

Flask blueprint providing endpoints for exporting:
- Game reports with plays analysis
- Player performance reports
- Team statistical reports

Endpoints:
- GET /reports/game/<game_id>/pdf - Export game report
- GET /reports/player/<player_id>/pdf - Export player report
- GET /reports/team/pdf - Export team report
"""

from flask import Blueprint, send_file, jsonify, current_app
from core.models import Game, Player
from core.pdf_exports import PlaysBasedPDFGenerator
import logging

pdf_export_bp = Blueprint('pdf_export', __name__, url_prefix='/reports')
logger = logging.getLogger(__name__)


@pdf_export_bp.route('/game/<int:game_id>/pdf', methods=['GET'])
def export_game_pdf(game_id):
    """Export game report PDF with plays analysis.

    Args:
        game_id (int): Game database ID

    Returns:
        Response: PDF file download

    Raises:
        404: Game not found
        500: PDF generation error
    """
    try:
        game = Game.query.get(game_id)
        if not game:
            return jsonify({'error': f'Game {game_id} not found'}), 404

        # Generate PDF
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_game_report_pdf(game_id)

        # Prepare filename
        game_date = game.date.strftime('%Y%m%d') if hasattr(game.date, 'strftime') else str(game.date).replace('-', '')
        filename = f"game_{game_id}_{game_date}_{game.opponent.replace(' ', '_')}.pdf"

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except ValueError as e:
        logger.error(f"Validation error in game PDF export: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating game PDF: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to generate PDF report'}), 500


@pdf_export_bp.route('/player/<int:player_id>/pdf', methods=['GET'])
def export_player_pdf(player_id):
    """Export player performance report PDF.

    Args:
        player_id (int): Player database ID

    Returns:
        Response: PDF file download

    Raises:
        404: Player not found
        500: PDF generation error
    """
    try:
        player = Player.query.get(player_id)
        if not player:
            return jsonify({'error': f'Player {player_id} not found'}), 404

        # Generate PDF
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_player_report_pdf(player_id)

        # Prepare filename
        filename = f"player_{player_id}_{player.name.replace(' ', '_')}.pdf"

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except ValueError as e:
        logger.error(f"Validation error in player PDF export: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating player PDF: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to generate PDF report'}), 500


@pdf_export_bp.route('/team/pdf', methods=['GET'])
def export_team_pdf():
    """Export team statistical report PDF.

    Returns:
        Response: PDF file download

    Raises:
        500: PDF generation error
    """
    try:
        # Generate PDF
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_team_report_pdf()

        # Prepare filename
        from datetime import datetime
        date_str = datetime.now().strftime('%Y%m%d')
        filename = f"team_report_{date_str}.pdf"

        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Error generating team PDF: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to generate PDF report'}), 500


@pdf_export_bp.route('/game/<int:game_id>/preview', methods=['GET'])
def preview_game_pdf(game_id):
    """Preview game report without downloading.

    Args:
        game_id (int): Game database ID

    Returns:
        Response: PDF inline display
    """
    try:
        game = Game.query.get(game_id)
        if not game:
            return jsonify({'error': f'Game {game_id} not found'}), 404

        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_game_report_pdf(game_id)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf'
        )

    except Exception as e:
        logger.error(f"Error previewing game PDF: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to preview PDF report'}), 500


@pdf_export_bp.route('/player/<int:player_id>/preview', methods=['GET'])
def preview_player_pdf(player_id):
    """Preview player report without downloading.

    Args:
        player_id (int): Player database ID

    Returns:
        Response: PDF inline display
    """
    try:
        player = Player.query.get(player_id)
        if not player:
            return jsonify({'error': f'Player {player_id} not found'}), 404

        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_player_report_pdf(player_id)

        return send_file(
            pdf_buffer,
            mimetype='application/pdf'
        )

    except Exception as e:
        logger.error(f"Error previewing player PDF: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to preview PDF report'}), 500


@pdf_export_bp.route('/team/preview', methods=['GET'])
def preview_team_pdf():
    """Preview team report without downloading.

    Returns:
        Response: PDF inline display
    """
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_team_report_pdf()

        return send_file(
            pdf_buffer,
            mimetype='application/pdf'
        )

    except Exception as e:
        logger.error(f"Error previewing team PDF: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to preview PDF report'}), 500
