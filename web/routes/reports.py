import os
import zipfile
from collections import defaultdict
from io import BytesIO
from datetime import datetime
from sqlalchemy import desc, func
from flask import Blueprint, current_app, jsonify, render_template, request, send_file, session, abort
from flask_login import login_required
from weasyprint import HTML

from web.decorators import team_access_required
from core.models import (
    Game,
    GameEvent,
    Lineup,
    LineupSegment,
    Play,
    PlayerLineupStats,
    PlayerStat,
    Possession,
    ShotEvent,
    ShotZone,
    SystemSetting,
    WhatsAppGroup,
    db,
)
from core.services.analytics_service import AnalyticsService
from core.services.evolution_report_service import EvolutionReportService
from core.services.schema4_evolution_report_service import (
    Schema4EvolutionReportService,
)
from core.charts import (
    generate_shot_chart,
    generate_team_shot_chart,
    generate_player_charts,
    generate_team_scoring_trend,
)
from core.play_analytics import (
    get_summary_play_stats,
    get_summary_play_player_stats,
    get_summary_player_play_stats,
    get_untracked_percentages,
    get_summary_player_top_plays_by_points,
)
from core.utils import (
    calculate_ortg,
    calculate_possessions,
    parse_minutes,
    safe_percentage,
)
from core.advanced_game_report import TeamBox, PlayerBox, build_advanced_game_report
from core.advanced_pdf_reports import (
    AdvancedPDFReports,
    generate_visual_game_report_bytes,
    generate_lineup_report_bytes,
    generate_player_scouting_card_bytes,
    generate_season_trend_report_bytes,
    generate_clutch_report_bytes,
)
from core.advanced_analytics import (
    classify_shot_zone,
    ClutchPerformance,
    LineupAnalytics,
    parse_time_to_seconds,
)
from core.game_recap import build_recap

# Import functions extracted to report_service
from core.services.report_service import (
    _safe_ppp,
    _seconds_to_minutes,
    _meets_top_lineup_minutes,
    _get_player_reb_conceded_summary,
    _get_team_reb_conceded_summary,
    _normalize_zone,
    _team_event_points,
    _player_event_points,
    _opponent_event_points,
    _serialize_lineup_summary,
    _build_zone_summary,
    _build_play_summary,
    _build_player_box_detail,
    _build_player_lineup_context,
    _build_possession_summary,
    _build_player_possession_context,
    _build_player_shot_play_context,
    _build_team_box_detail,
    _build_team_lineup_summary,
    _build_team_report_context,
    _parse_detail,
    _parse_detail_points,
    _build_quarter_map,
    _get_shot_scoring_data,
    _get_opponent_box_score_from_events,
    generate_game_pdf_bytes,
    _build_quarterly_stats,
    _parse_time_remaining,
    _event_team_points,
    _get_starting_lineup_from_events,
    _get_starting_lineup_from_segments,
    _build_time_progression,
    _generate_player_report_data,
)

reports_bp = Blueprint("reports", __name__)

VALID_GAME_TYPES = {"ALL", "Season", "Friendly"}
MAX_PLAYERS_IN_ZIP = 50
MIN_TOP_LINEUP_MINUTES = 10
MIN_TOP_LINEUP_SECONDS = MIN_TOP_LINEUP_MINUTES * 60


@reports_bp.route("/recap/<int:game_id>")
@login_required
@team_access_required
def game_recap_json(game_id):
    """Template-based 5-bullet game auto-recap (JSON, no LLM)."""
    recap = build_recap(game_id, session.get('current_team_id'))
    if recap is None:
        abort(404)
    return jsonify(recap)


@reports_bp.route("/games/<int:game_id>/summary.pdf")
@login_required
@team_access_required
def game_summary_pdf(game_id):
    """Generate full game summary PDF"""
    filename, pdf_bytes = generate_game_pdf_bytes(game_id)

    if not pdf_bytes:
        return jsonify({"error": "No stats for this game or game not found"}), 404

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/games/<int:game_id>/advanced_summary.pdf")
@login_required
@team_access_required
def advanced_game_summary_pdf(game_id):
    """Generate advanced game summary PDF using new backend module"""
    game = Game.query.filter_by(id=game_id, team_id=session.get('current_team_id')).first()
    if not game:
        abort(404)
    stats = PlayerStat.query.filter_by(game_id=game_id).all()

    if not stats:
        return jsonify({"error": "No stats for this game"}), 404

    team_name = SystemSetting.get_value("team_name", "LX")

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

    team_poss = calculate_possessions(
        team_box.fga, team_box.fta, team_box.orb, team_box.tov
    )
    opp_pts = game.opponent_score

    opp_box = _get_opponent_box_score_from_events(game_id)

    if opp_box is None:
        opp_fga_est = int(team_poss * 0.6)
        opp_fta_est = int(opp_fga_est * 0.25)

        opp_box = TeamBox(
            pts=opp_pts,
            fgm=0,
            fga=opp_fga_est,
            tpm=0,
            tpa=0,
            ftm=0,
            fta=opp_fta_est,
            orb=0,
            drb=team_box.orb,
            trb=team_box.orb,
            ast=0,
            stl=0,
            blk=0,
            tov=int(team_poss * 0.15),
        )

    opp_poss = calculate_possessions(opp_box.fga, opp_box.fta, opp_box.orb, opp_box.tov)
    pace = (team_poss + opp_poss) / 2 if (team_poss + opp_poss) > 0 else team_poss

    players = [
        PlayerBox(
            name=s.player_name,
            minutes=parse_minutes(s.minutes),
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

    shot_events = ShotEvent.query.filter_by(game_id=game_id).all()
    team_shots = [
        {"x": s.x_loc, "y": s.y_loc, "made": s.result == "made"}
        for s in shot_events
        if s.x_loc is not None and s.y_loc is not None
    ]

    zone_stats = defaultdict(lambda: {"makes": 0, "attempts": 0, "points": 0})
    for s in shot_events:
        if s.x_loc is not None and s.y_loc is not None:
            zone = classify_shot_zone(s.x_loc, s.y_loc, s.shot_type or "2pt")
            zone_stats[zone]["attempts"] += 1
            zone_stats[zone]["points"] += s.points or 0
            if s.result == "made":
                zone_stats[zone]["makes"] += 1

    events = (
        GameEvent.query.filter_by(game_id=game_id).order_by(GameEvent.timestamp).all()
    )

    quarterly_stats = _build_quarterly_stats(events, game)

    clutch_stats = ClutchPerformance.get_clutch_stats(game_id)

    game_meta = {
        "date": game.date,
        "location": "",
        "competition": game.game_type or "",
        "team_name": team_name,
        "opp_name": game.opponent,
        "team_points": team_box.pts,
        "opp_points": opp_pts,
        "generated_at": datetime.now().strftime("%B %d, %Y"),
    }

    team_minutes_total = 200.0

    report = build_advanced_game_report(
        game=game_meta,
        team_box=team_box,
        opp_box=opp_box,
        players=players,
        team_minutes_total=team_minutes_total,
        team_shots=team_shots,
        opp_shots=[],
    )

    html = render_template(
        "game_summary_advanced_pdf.html",
        game=game_meta,
        report=report,
        zone_stats=dict(zone_stats),
        quarterly_stats=quarterly_stats,
        clutch_stats=clutch_stats,
    )

    return _render_pdf(html, f"advanced_report_{game.opponent}_{game.date}.pdf")


@reports_bp.route("/team/report.pdf")
@login_required
@team_access_required
def team_report_pdf():
    """Generate enhanced team-level PDF report"""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type, _get_season_id())

    if not games:
        return jsonify({"error": "No games for selected filter"}), 404

    html = render_template(
        "team_report_pdf.html", **_build_team_report_context(game_type, games, game_ids)
    )

    return _render_pdf(html, f"Team_Report_{game_type}.pdf")


@reports_bp.route("/player/<player_name>/report.pdf")
@login_required
@team_access_required
def player_report_pdf(player_name):
    """Generate multi-page PDF report for a player"""
    return render_player_report_pdf(player_name)


def render_player_report_pdf(player_name):
    """Build the player PDF response.

    Single code path for every player report URL (`/player/<name>/report.pdf`
    and the legacy player-id export), so the layouts can no longer diverge.
    """
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type, _get_season_id())

    if not games:
        return jsonify({"error": "No games"}), 404

    try:
        context = _generate_player_report_data(player_name, games, game_ids, game_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    html = render_template("player_report_pdf.html", **context)
    return _render_pdf(html, f"{player_name.replace(' ', '_')}_report_{game_type}.pdf")


@reports_bp.route("/download-all", strict_slashes=False)
@login_required
@team_access_required
def download_all_reports():
    """Generate ZIP with all player reports sequentially to stay under 500MB RAM"""
    import time
    import gc
    import psutil
    import os
    import tempfile

    current_app.logger.info("Starting memory-optimized bulk player report download...")
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type, _get_season_id())

    if not games:
        return jsonify({"error": "No games"}), 404

    players = (
        db.session.query(PlayerStat.player_name)
        .filter(PlayerStat.game_id.in_(game_ids))
        .filter(PlayerStat.minutes.notin_(("00:00", "0")))
        .distinct()
        .order_by(PlayerStat.player_name)
        .limit(MAX_PLAYERS_IN_ZIP)
        .all()
    )
    player_names = [p[0] for p in players]

    team_avg = AnalyticsService.calculate_team_averages(game_ids, db.session)
    zip_path = None

    process = psutil.Process(os.getpid())

    def get_mem():
        return process.memory_info().rss / 1024 / 1024

    results = []
    current_app.logger.info(
        f"Processing {len(player_names)} players sequentially. Initial Mem: {get_mem():.1f}MB"
    )

    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            zip_path = tmp.name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            success_count = 0

            try:
                team_context = _build_team_report_context(game_type, games, game_ids)
                team_html = render_template("team_report_pdf.html", **team_context)
                team_pdf = HTML(string=team_html).write_pdf()
                if team_pdf:
                    zipf.writestr(f"Team_Report_{game_type}.pdf", team_pdf)
                    success_count += 1
            except Exception as e:
                current_app.logger.error(f"Failed team report for bulk download: {e}")

            for i, player_name in enumerate(player_names):
                player_start_time = time.time()
                try:
                    # Clear memory before starting each player
                    gc.collect()

                    context = _generate_player_report_data(
                        player_name,
                        games,
                        game_ids,
                        game_type,
                        team_avg_override=team_avg,
                    )
                    html = render_template("player_report_pdf.html", **context)

                    pdf_doc = HTML(string=html)
                    pdf_data = pdf_doc.write_pdf()

                    if pdf_data:
                        filename = (
                            f"{player_name.replace(' ', '_')}_report_{game_type}.pdf"
                        )
                        zipf.writestr(filename, pdf_data)
                        success_count += 1

                    duration = time.time() - player_start_time
                    current_app.logger.info(
                        f"[{i + 1}/{len(player_names)}] {player_name}: {duration:.2f}s | Mem: {get_mem():.1f}MB"
                    )

                    # Force cleanup after each report
                    del context
                    del html
                    del pdf_doc
                    del pdf_data

                except Exception as e:
                    current_app.logger.error(f"Failed report for {player_name}: {e}")
                    continue

            if success_count == 0:
                if zip_path and os.path.exists(zip_path):
                    os.unlink(zip_path)
                return jsonify({"error": "Failed to generate any reports"}), 500

        current_app.logger.info(f"Bulk download complete. Final Mem: {get_mem():.1f}MB")

        response = send_file(
            zip_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"team_and_player_reports_{game_type}.zip",
        )

        @response.call_on_close
        def _cleanup_zip():
            if zip_path and os.path.exists(zip_path):
                os.unlink(zip_path)

        return response
    except Exception as e:
        if zip_path and os.path.exists(zip_path):
            os.unlink(zip_path)
        current_app.logger.error(f"Bulk download critical failure: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def _get_game_type(default="ALL"):
    if default not in VALID_GAME_TYPES:
        default = "ALL"
    game_type = request.args.get("game_type", default)
    return game_type if game_type in VALID_GAME_TYPES else "ALL"


def _get_season_id():
    from core.services.season_service import resolve_request_season_id
    # Read-only context: honor ?season=/session without persisting overrides.
    return resolve_request_season_id(session.get("current_team_id"), persist=False)


def _get_games(game_type, season_id="ALL"):
    query = Game.query.filter(Game.team_id == session['current_team_id']).order_by(Game.sort_date.asc())
    if game_type == "Season":
        query = query.filter(Game.game_type == "Season")
    elif game_type == "Friendly":
        query = query.filter(Game.game_type == "Friendly")
    if season_id != "ALL":
        query = query.filter(Game.season_id == int(season_id))
    games = query.all()
    return games, [g.id for g in games]


def _render_pdf(html, filename):
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    html_doc = HTML(string=html, base_url=f"file://{project_root}/")
    pdf_bytes = html_doc.write_pdf()
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)
    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/games/<int:game_id>/visual.pdf")
@login_required
@team_access_required
def visual_game_report_pdf(game_id):
    """Generate visual game report with score worm, quarterly flow, four factors."""
    filename, pdf_bytes = generate_visual_game_report_bytes(game_id)

    if not pdf_bytes:
        return jsonify({"error": "Could not generate visual report"}), 404

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/lineup/report.pdf")
@login_required
@team_access_required
def lineup_report_pdf():
    """Generate lineup analysis report with top lineups, duo matrix."""
    game_type = _get_game_type()
    games, game_ids = _get_games(game_type, _get_season_id())

    # Mirror the /api/advanced/lineup/* filters so the PDF matches the Lineups
    # page. game_ids from _get_games is already team- and season-scoped; passing
    # None (as this route used to do for game_type=ALL) drops that filter and
    # aggregates other teams' lineups.
    # type=float to match the combinations endpoint, which accepts fractional
    # thresholds from the Min Poss input.
    min_possessions = request.args.get("min_possessions", 5.0, type=float)
    if min_possessions < 1:
        min_possessions = 5.0
    rank_by = request.args.get("rank_by", "overall")
    if rank_by not in {"overall", "offensive", "defensive"}:
        rank_by = "overall"

    filename, pdf_bytes = generate_lineup_report_bytes(
        game_ids=game_ids,
        min_possessions=min_possessions,
        rank_by=rank_by,
    )

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    response = send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )
    # Avoid browsers reusing a cached PDF when regenerating the same URL.
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@reports_bp.route("/player/<player_name>/scouting.pdf")
@login_required
@team_access_required
def player_scouting_card_pdf(player_name):
    """Generate player scouting card with shot chart and hot zones."""
    game_type = _get_game_type()

    filename, pdf_bytes = generate_player_scouting_card_bytes(player_name, game_type)

    if not pdf_bytes:
        return jsonify({"error": "No data for player"}), 404

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/season/trends.pdf")
@login_required
@team_access_required
def season_trend_report_pdf():
    """Generate season trend report with rolling averages."""
    game_type = _get_game_type(default="Season")
    player_name = request.args.get("player", None)

    filename, pdf_bytes = generate_season_trend_report_bytes(player_name, game_type)

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/clutch/report.pdf")
@login_required
@team_access_required
def clutch_report_pdf():
    """Generate clutch time performance report."""
    game_type = _get_game_type(default="Season")

    filename, pdf_bytes = generate_clutch_report_bytes(game_type)

    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/live/halftime-pdf", methods=["POST"])
@login_required
@team_access_required
def live_halftime_pdf():
    """
    Generate half-time summary PDF from live game data.

    Accepts JSON payload with current game state and generates a PDF
    without requiring the game to be saved to the database.

    Expected payload:
    {
        "opponent": "Team Name",
        "date": "2024-01-15",
        "team_score": 45,
        "opp_score": 42,
        "player_stats": {
            "Player1": {points, fgm, fga, tpm, tpa, ftm, fta, oreb, dreb, ast, stl, blk, tov, pf, minutes, plus_minus},
            ...
        },
        # Either source is accepted; shot_locations is what the legacy
        # tracker sends, game_events is the v2/saved-game shape.
        "shot_locations": [...],
        "game_events": [...],
        "schema_version": 4
    }
    """
    from flask import request
    from weasyprint import HTML
    from io import BytesIO
    from flask import send_file

    from core.halftime_summary import build_halftime_summary

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({"error": "No data provided"}), 400

    opponent = str(data.get("opponent") or "Unknown").strip() or "Unknown"
    date = (
        str(data.get("date") or "").strip()
        or datetime.now().strftime("%Y-%m-%d")
    )
    try:
        schema_version = int(data.get("schema_version", 1))
    except (TypeError, ValueError):
        schema_version = 1

    summary = build_halftime_summary(data)

    html = render_template(
        "halftime_summary_pdf.html",
        opponent=opponent,
        date=date,
        team_score=summary["team_score"],
        opp_score=summary["opp_score"],
        stats=summary["stats"],
        top_performers=summary["top_performers"],
        team_aggregates=summary["team_aggregates"],
        quarterly_stats=summary["quarterly_stats"],
        generated_date=datetime.now().strftime("%B %d, %Y at %H:%M"),
        schema_version=schema_version,
        is_live=True,
    )

    pdf_doc = HTML(string=html)
    pdf_bytes = pdf_doc.write_pdf()

    filename = f"halftime_{opponent}_{date}.pdf"
    pdf_io = BytesIO(pdf_bytes)
    pdf_io.seek(0)

    return send_file(
        pdf_io,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@reports_bp.route("/live/halftime-share", methods=["POST"])
@login_required
@team_access_required
def live_halftime_share():
    """One-tap halftime share from the v2 console (Slice N1).

    Accepts the same live payload as ``/live/halftime-pdf`` plus optional
    ``group_id`` (a WhatsAppGroup id scoped to the session team) or
    ``phone`` (E.164-ish digits). Builds the staff WhatsApp text and sends
    it; when no destination is given the text is returned unsent so the
    console can show it for manual copy. WhatsApp is text-only (OpenWA has
    no media support in this stack) — the PDF itself is fetched via the
    existing ``halftime-pdf`` endpoint.
    """
    from flask_login import current_user

    from core.halftime_share import build_halftime_text, validate_halftime_payload

    if getattr(current_user, "is_auditor", False):
        return jsonify({"error": "Auditors have read-only access"}), 403

    data = request.get_json(silent=True) or {}
    errors = validate_halftime_payload(data)
    if errors:
        return jsonify({"error": "; ".join(errors)}), 400

    text = build_halftime_text(data)
    team_id = session.get("current_team_id")

    group_id = data.get("group_id")
    phone = (data.get("phone") or "").strip() if data.get("phone") else ""
    pdf_base64 = data.get("pdf_base64") or ""
    pdf_filename = (data.get("pdf_filename")
                    or f"halftime_{data.get('opponent', 'game')}_"
                    f"{data.get('date', '')}.pdf")

    from core.services import whatsapp_service

    target_group = None
    if group_id is not None:
        try:
            group_id = int(group_id)
        except (TypeError, ValueError):
            return jsonify({"error": "group_id must be an integer"}), 400
        target_group = WhatsAppGroup.query.filter_by(
            id=group_id, team_id=team_id, active=True).first()
        if target_group is None:
            return jsonify({"error": "WhatsApp group not found"}), 404
    elif not phone:
        # True one-tap: fall back to the team's default staff group
        # (first active) so the console needs no destination at all.
        target_group = WhatsAppGroup.query.filter_by(
            team_id=team_id, active=True).order_by(
            WhatsAppGroup.id).first()
        if target_group is None:
            return jsonify({"sent": False, "text_sent": False,
                            "text": text, "pdf_sent": None,
                            "hint": "no staff group configured — pass "
                                    "group_id or phone, or add one under "
                                    "team settings"}), 200

    if target_group is not None:
        ok = whatsapp_service.send_text_message(
            target_group.group_wa_id, text,
            label=f"group:{target_group.group_wa_id}")
        channel = {"kind": "whatsapp_group",
                   "group_id": target_group.id}
        dest = target_group.group_wa_id
    else:
        chat_id = whatsapp_service._to_number(phone)
        if not chat_id:
            return jsonify({"error": "phone is required"}), 400
        ok = whatsapp_service.send_text_message(chat_id, text, label=phone)
        channel = {"kind": "whatsapp", "phone": phone}
        dest = chat_id

    pdf_sent = None
    text_sent = bool(ok)
    if text_sent and pdf_base64:
        # Optional attachment: console posts the rendered halftime PDF
        # (base64) alongside the live payload; forwarded as a document.
        # Reported separately: the text is already delivered at this
        # point, so a PDF failure must not read as "nothing sent"
        # (which would invite duplicate texts on retry).
        pdf_sent = bool(whatsapp_service.send_document(
            dest, filename=pdf_filename,
            mimetype="application/pdf",
            media_base64=pdf_base64, caption=text[:200]))

    if text_sent:
        from core.usage_meter import bump as _bump_usage
        _bump_usage("halftime_shares", team_id=team_id)
    status = 200 if text_sent else 502
    return jsonify({"sent": text_sent, "text_sent": text_sent,
                    "text": text, "channel": channel,
                    "pdf_sent": pdf_sent}), status


@reports_bp.route("/games/<int:game_id>/evolution.pdf")
@login_required
@team_access_required
def game_evolution_pdf(game_id: int):
    """Generate game evolution PDF showing stats over time.

    This report includes:
    - Score progression (score worm)
    - Team efficiency metrics over time
    - Player stat evolution
    - Scoring runs and lead changes
    - Quarter-by-quarter breakdown
    - Clutch time analysis (if applicable)

    Args:
        game_id: The game ID to generate the report for

    Returns:
        PDF file download
    """
    try:
        game = db.session.get(Game, game_id)
        if game is None or game.team_id != session.get('current_team_id'):
            raise ValueError(f"Game with id {game_id} not found")

        if (game.schema_version or 0) >= 4:
            report = Schema4EvolutionReportService.build_report(game_id)
        else:
            report = EvolutionReportService.build_report(game_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    html = render_template(
        "game_evolution_pdf.html",
        report=report,
        generated_date=datetime.now().strftime("%B %d, %Y at %H:%M"),
    )

    return _render_pdf(html, f"evolution_{report.opponent}_{report.date}.pdf")


@reports_bp.route("/scout/<path:opponent>")
@login_required
@team_access_required
def opponent_scout_pdf(opponent):
    """Generate one-page opponent scouting PDF."""
    from core.scout_report import DEFAULT_LIMIT, build_scout

    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    context = build_scout(opponent, session.get('current_team_id'), limit)

    html = render_template("game_scout_pdf.html", **context)

    safe = (context.get("opponent") or "opponent").replace(" ", "_")
    return _render_pdf(html, f"scout_{safe}.pdf")
