import zipfile
from io import BytesIO
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, send_file
from flask_login import login_required
from weasyprint import HTML

from core.models import Game, PlayerStat, ShotEvent, db
from core.services.analytics_service import AnalyticsService
from core.charts import (
    generate_shot_chart, 
    generate_team_shot_chart, 
    generate_player_charts, 
    generate_team_scoring_trend
)
from core.play_analytics import (
    get_play_stats,
    get_play_player_stats,
    get_player_play_stats,
    get_untracked_percentages,
    get_player_top_plays_by_points,
)
from core.utils import calculate_possessions, safe_percentage
from core.advanced_game_report import TeamBox, PlayerBox, build_advanced_game_report

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

VALID_GAME_TYPES = {"ALL", "Season", "Friendly"}
MAX_PLAYERS_IN_ZIP = 50

@reports_bp.route("/games/<int:game_id>/summary.pdf")
@login_required
def game_summary_pdf(game_id):
    """Generate full game summary PDF"""
    game = Game.query.get_or_404(game_id)
    stats = PlayerStat.query.filter_by(game_id=game_id).all()

    if not stats:
        return jsonify({"error": "No stats for this game"}), 404

    # Enrich stats
    stats_with_metrics = AnalyticsService.calculate_game_stats(stats)
    
    # Generate player shot charts
    for player in stats_with_metrics:
        player.shot_chart = generate_shot_chart(player.player_name, [game_id], db.session)

    # Top performers & alerts
    top_performers = AnalyticsService.get_game_top_performers(stats_with_metrics)
    alerts = AnalyticsService.get_game_alerts(stats_with_metrics)
    team_aggregates = AnalyticsService.get_team_aggregates(stats_with_metrics)

    # Shot chart & Plays
    shot_events = ShotEvent.query.filter_by(game_id=game_id).first()
    shot_chart = generate_team_shot_chart([game_id], db.session) if shot_events else ""

    plays_data = get_play_stats(game_id, play_type="Offense")
    plays_players_data = get_play_player_stats(game_id, play_type="Offense")
    players_plays_data = get_player_play_stats(game_id, play_type="Offense")
    untracked = get_untracked_percentages(game_id) or {}
    
    # Get top 3 plays per player by points
    player_top_plays = get_player_top_plays_by_points(game_id, limit=3)
    
    # Attach top plays to each player stat object
    for player in stats_with_metrics:
        top_plays = player_top_plays.get(player.player_name, [])
        # Transform to format expected by template
        player.top_3_plays = [
            {
                "points": play["points"],
                "play_name": play["name"]
            }
            for play in top_plays
        ]

    html = render_template(
        "game_summary_pdf.html",
        game=game,
        stats=stats_with_metrics,
        top_performers=top_performers,
        alerts=alerts,
        team_aggregates=team_aggregates,
        shot_chart=shot_chart,
        plays_data=plays_data,
        plays_players_data=plays_players_data,
        players_plays_data=players_plays_data,
        untracked=untracked,
        generated_date=datetime.now().strftime("%B %d, %Y"),
    )

    return _render_pdf(html, f"game_{game.opponent}_{game.date}.pdf")

@reports_bp.route("/games/<int:game_id>/advanced_summary.pdf")
@login_required
def advanced_game_summary_pdf(game_id):
    """Generate advanced game summary PDF using new backend module"""
    game = Game.query.get_or_404(game_id)
    stats = PlayerStat.query.filter_by(game_id=game_id).all()

    if not stats:
        return jsonify({"error": "No stats for this game"}), 404

    # Build team box scores
    team_box = TeamBox(
        pts=sum(s.points for s in stats),
        fgm=sum(s.fgm for s in stats),
        fga=sum(s.fga for s in stats),
        tpm=sum(s.tpm for s in stats),
        tpa=sum(s.tpa for s in stats),
        ftm=sum(s.ftm for s in stats),
        fta=sum(s.fta for s in stats),
        orb=sum(s.oreb for s in stats),
        drb=sum(s.dreb for s in stats),
        trb=sum(s.oreb + s.dreb for s in stats),
        ast=sum(s.ast for s in stats),
        stl=sum(s.stl for s in stats),
        blk=sum(s.blk for s in stats),
        tov=sum(s.tov for s in stats),
    )

    # Estimate opponent box (minimal, we only have their score)
    # Use team possessions estimate for opponent possessions
    team_poss = team_box.fga + 0.44 * team_box.fta - team_box.orb + team_box.tov
    
    # Rough estimate: assume opponent had similar possession count
    # and work backwards to estimate their FGA (very rough)
    opp_pts = game.opponent_score
    # Assume opponent eFG% of 0.45, FTr of 0.25 for estimation
    opp_fga_est = int(team_poss * 0.6)  # rough
    opp_fta_est = int(opp_fga_est * 0.25)
    
    opp_box = TeamBox(
        pts=opp_pts,
        fgm=0,  # unknown
        fga=opp_fga_est,
        tpm=0,
        tpa=0,
        ftm=0,
        fta=opp_fta_est,
        orb=0,
        drb=team_box.orb,  # our ORB = their DRB
        trb=team_box.orb,
        ast=0,
        stl=0,
        blk=0,
        tov=int(team_poss * 0.15),  # estimate
    )

    # Build player boxes
    players = [
        PlayerBox(
            name=s.player_name,
            minutes=float(s.minutes.split(':')[0]) if isinstance(s.minutes, str) and ':' in s.minutes else float(s.minutes or 0),
            pts=s.points,
            fgm=s.fgm,
            fga=s.fga,
            tpm=s.tpm,
            tpa=s.tpa,
            ftm=s.ftm,
            fta=s.fta,
            orb=s.oreb,
            drb=s.dreb,
            trb=s.oreb + s.dreb,
            ast=s.ast,
            stl=s.stl,
            blk=s.blk,
            tov=s.tov,
        )
        for s in stats
    ]

    # Game metadata
    game_meta = {
        "date": game.date,
        "location": "",  # Game model has no location field
        "competition": game.game_type or "",
        "team_name": "LX",  # TODO: get from config/db
        "opp_name": game.opponent,
        "team_points": team_box.pts,
        "opp_points": opp_pts,
        "generated_at": datetime.now().strftime("%B %d, %Y"),
    }

    # Assume 40-minute game (200 total team minutes)
    team_minutes_total = 200.0

    # Build report
    report = build_advanced_game_report(
        game=game_meta,
        team_box=team_box,
        opp_box=opp_box,
        players=players,
        team_minutes_total=team_minutes_total,
        team_shots=None,  # TODO: parse from ShotEvent if needed
        opp_shots=None,
    )

    html = render_template(
        "game_summary_advanced_pdf.html",
        game=game_meta,
        report=report,
    )

    return _render_pdf(html, f"advanced_report_{game.opponent}_{game.date}.pdf")

@reports_bp.route("/team/report.pdf")
@login_required
def team_report_pdf():
    """Generate enhanced team-level PDF report"""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)
    
    if not games:
        return jsonify({"error": "No games for selected filter"}), 404

    # Calculate metrics
    team_data = AnalyticsService.calculate_enhanced_team_metrics(games, game_ids, db.session)
    
    # Generate Charts
    team_data['chart_trend'] = generate_team_scoring_trend(games)
    team_data['chart_shooting'] = generate_team_shot_chart(game_ids, db.session)

    html = render_template(
        "team_report_pdf.html",
        game_type=game_type,
        generated_date=datetime.now().strftime("%B %d, %Y"),
        **team_data,
    )

    return _render_pdf(html, f"Team_Report_{game_type}.pdf")

@reports_bp.route("/player/<player_name>/report.pdf")
@login_required
def player_report_pdf(player_name):
    """Generate multi-page PDF report for a player"""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)
    
    if not games:
        return jsonify({"error": "No games"}), 404

    try:
        context = _generate_player_report_data(player_name, games, game_ids, game_type)
    except ValueError as e:
         return jsonify({"error": str(e)}), 404

    html = render_template("player_report_pdf.html", **context)
    return _render_pdf(html, f"{player_name.replace(' ', '_')}_report_{game_type}.pdf")

@reports_bp.route("/download-all")
@login_required
def download_all_reports():
    """Generate ZIP with all player reports"""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type)
    
    if not games:
        return jsonify({"error": "No games"}), 404

    players = (
        db.session.query(PlayerStat.player_name)
        .distinct()
        .order_by(PlayerStat.player_name)
        .limit(MAX_PLAYERS_IN_ZIP) # Limit to prevent OOM
        .all()
    )
    player_names = [p[0] for p in players]

    # Pre-calculate team averages once
    team_avg = AnalyticsService.calculate_team_averages(game_ids, db.session)
    generated_date = datetime.now().strftime("%B %d, %Y")

    zip_buffer = BytesIO()
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for player_name in player_names:
                try:
                    context = _generate_player_report_data(player_name, games, game_ids, game_type, team_avg_override=team_avg)
                    html = render_template("player_report_pdf.html", **context)
                    
                    pdf_doc = HTML(string=html)
                    pdf_data = pdf_doc.write_pdf()
                    
                    filename = f"{player_name.replace(' ', '_')}_report_{game_type}.pdf"
                    zipf.writestr(filename, pdf_data)
                except ValueError:
                    continue # Skip players with no stats
                    
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"all_player_reports_{game_type}.zip",
        )
    except Exception as e:
        return jsonify({"error": f"Failed: {str(e)}"}), 500

# --- Helpers ---

def _get_game_type():
    game_type = request.args.get("game_type", "ALL")
    return game_type if game_type in VALID_GAME_TYPES else "ALL"

def _get_games(game_type):
    query = Game.query.order_by(Game.sort_date.asc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")
    games = query.all()
    return games, [g.id for g in games]

def _render_pdf(html, filename):
    html_doc = HTML(string=html)
    pdf_bytes = html_doc.write_pdf()
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )

def _generate_player_report_data(player_name, games, game_ids, game_type, team_avg_override=None):
    """Internal helper to gather all data for a player report"""
    stats = (
        PlayerStat.query.filter(PlayerStat.player_name == player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes != "00:00")
        .filter(PlayerStat.minutes != "0")
        .all()
    )
    
    if not stats:
        raise ValueError("No stats for player")

    # Sort stats
    game_map = {g.id: g for g in games}
    stats_with_dates = [(s, game_map.get(s.game_id)) for s in stats]
    stats_with_dates.sort(key=lambda x: x[1].sort_date if x[1] else "")
    stats = [s[0] for s in stats_with_dates]

    # Metrics
    report_data = AnalyticsService.calculate_player_metrics(stats, game_map, len(stats))
    
    # Team Context
    team_avg = team_avg_override or AnalyticsService.calculate_team_averages(game_ids, db.session)
    team_rankings = AnalyticsService.calculate_team_rankings(player_name, game_ids, report_data, db.session)
    
    # Charts
    charts = generate_player_charts(stats, game_map, player_name)
    shot_chart = generate_shot_chart(player_name, game_ids, db.session)

    return {
        "player_name": player_name,
        "game_type": game_type,
        "generated_date": datetime.now().strftime("%B %d, %Y"),
        "team_avg": team_avg,
        "team_rankings": team_rankings,
        "shot_chart": shot_chart,
        **report_data,
        **charts
    }
