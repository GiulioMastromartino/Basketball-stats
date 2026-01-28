from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file
from flask_login import login_required, current_user
from core import db
from core.pdf_exports import PlaysBasedPDFGenerator

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')

@reports_bp.route('/game/<int:game_id>/advanced_pdf')
@login_required
def advanced_game_summary_pdf(game_id):
    """Generate advanced game report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_game_report_pdf(game_id)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'game_report_{game_id}.pdf'
        )
    except Exception as e:
        flash(f"Error generating PDF: {str(e)}", "danger")
        return redirect(url_for('main.game_detail', game_id=game_id))

@reports_bp.route('/team/advanced_pdf')
@login_required
def team_report_pdf():
    """Generate advanced team report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_team_report_pdf()
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='team_report.pdf'
        )
    except Exception as e:
        flash(f"Error generating PDF: {str(e)}", "danger")
        return redirect(url_for('reports.index'))

@reports_bp.route('/player/<int:player_id>/advanced_pdf')
@login_required
def player_report_pdf(player_id):
    """Generate advanced player report PDF."""
    try:
        generator = PlaysBasedPDFGenerator()
        pdf_buffer = generator.generate_player_report_pdf(player_id)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'player_report_{player_id}.pdf'
        )
    except Exception as e:
        flash(f"Error generating PDF: {str(e)}", "danger")
        return redirect(url_for('reports.index'))

# Legacy alias for compatibility if needed
@reports_bp.route('/game/<int:game_id>/pdf')
@login_required
def game_summary_pdf(game_id):
    return advanced_game_summary_pdf(game_id)
