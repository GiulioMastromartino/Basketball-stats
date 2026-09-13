"""Template-based game auto-recap (no LLM dependency).

Builds a deterministic 5-bullet story strictly from stored box score +
game events. Every bullet degrades to a neutral factual line when its
data is missing -- never invents events, never raises on sparse data.
"""

from core.models import Game, GameEvent, PlayerStat, ShotEvent, Team, db


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _game_score_for_stat(stat):
    """Hollinger Game Score; falls back to points on any error."""
    try:
        from core.utils import calculate_game_score

        return float(
            calculate_game_score(
                _safe_int(stat.points),
                _safe_int(stat.fgm),
                _safe_int(stat.fga),
                _safe_int(stat.ftm),
                _safe_int(stat.fta),
                _safe_int(stat.oreb),
                _safe_int(stat.dreb),
                _safe_int(stat.stl),
                _safe_int(stat.ast),
                _safe_int(stat.blk),
                _safe_int(stat.pf),
                _safe_int(stat.tov),
            )
        )
    except Exception:
        return float(_safe_int(stat.points))


def _parse_remaining_to_seconds(value):
    """Parse 'M:SS' time_remaining to seconds remaining; None if unparseable."""
    if value is None:
        return None
    try:
        text = str(value).strip()
        if ":" not in text:
            return None
        minutes_str, seconds_str = text.split(":", 1)
        return int(minutes_str) * 60 + int(seconds_str)
    except (TypeError, ValueError):
        return None


def _parse_detail_points(detail):
    """Extract opponent points from an OPP_SCORE detail payload."""
    if not detail:
        return 0
    if isinstance(detail, dict):
        return _safe_int(detail.get("points"), 0)
    if isinstance(detail, str):
        import ast
        import json

        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(detail)
                if isinstance(parsed, dict):
                    return _safe_int(parsed.get("points"), 0)
            except (ValueError, SyntaxError):
                continue
    return 0


def _parse_detail_ftm(detail):
    if not detail:
        return 0
    if isinstance(detail, dict):
        return _safe_int(detail.get("ftm"), 0)
    if isinstance(detail, str):
        import ast
        import json

        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(detail)
                if isinstance(parsed, dict):
                    return _safe_int(parsed.get("ftm"), 0)
            except (ValueError, SyntaxError):
                continue
    return 0


def _team_points_for_event(event):
    """Team points scored by a single GameEvent (0 if none)."""
    try:
        if event.event_type == "SHOT_2PT" and event.shot_attempt == "made":
            return 2
        if event.event_type == "SHOT_3PT" and event.shot_attempt == "made":
            return 3
        if event.event_type == "FT_MADE":
            return 1
        if event.event_type == "FT":
            return _parse_detail_ftm(event.detail)
    except Exception:
        return 0
    return 0


def _quarter_points(game_id, events, shots):
    """Return {quarter: {'team': int, 'opp': int, 'opp_known': bool}}.

    Prefers GameEvents when present (team scores + OPP_SCORE details);
    otherwise falls back to ShotEvent team points per quarter.
    """
    quarters = {}
    try:
        if events:
            for event in events:
                quarter = getattr(event, "quarter", None)
                if quarter is None:
                    continue
                try:
                    quarter = int(quarter)
                except (TypeError, ValueError):
                    continue
                entry = quarters.setdefault(
                    quarter, {"team": 0, "opp": 0, "opp_known": False}
                )
                team_pts = _team_points_for_event(event)
                if team_pts:
                    entry["team"] += team_pts
                if event.event_type == "OPP_SCORE":
                    entry["opp"] += _parse_detail_points(event.detail)
                    entry["opp_known"] = True
        elif shots:
            for shot in shots:
                if getattr(shot, "quarter", None) is None:
                    continue
                try:
                    quarter = int(shot.quarter)
                except (TypeError, ValueError):
                    continue
                entry = quarters.setdefault(
                    quarter, {"team": 0, "opp": 0, "opp_known": False}
                )
                entry["team"] += _safe_int(getattr(shot, "points", 0), 0)
    except Exception:
        pass
    return quarters


def _bullet_result(game, team_name):
    try:
        team_score = game.team_score
        opp_score = game.opponent_score
        opponent = game.opponent or "Opponent"
        if team_score is None or opp_score is None:
            return "Final score not recorded for this game."
        margin = team_score - opp_score
        if margin > 0:
            return (
                f"Final: {team_name} {team_score} - {opponent} {opp_score} "
                f"({team_name} win by {margin})."
            )
        if margin < 0:
            return (
                f"Final: {team_name} {team_score} - {opponent} {opp_score} "
                f"({opponent} win by {abs(margin)})."
            )
        return (
            f"Final: {team_name} {team_score} - {opponent} {opp_score} (tie)."
        )
    except Exception:
        return "Final score not recorded for this game."


def _bullet_top_performer(game_id):
    try:
        stats = PlayerStat.query.filter_by(game_id=game_id).all()
    except Exception:
        stats = []
    if not stats:
        return "No individual player stats recorded for this game."
    try:
        scored = [(_game_score_for_stat(s), s) for s in stats]
        scored.sort(key=lambda pair: (pair[0], _safe_int(pair[1].points)), reverse=True)
        best_score, best = scored[0]
        name = best.player_name or "Unknown player"
        parts = [f"{_safe_int(best.points)} pts"]
        reb = _safe_int(getattr(best, "reb", 0) or (_safe_int(best.oreb) + _safe_int(best.dreb)))
        ast = _safe_int(best.ast)
        if reb:
            parts.append(f"{reb} reb")
        if ast:
            parts.append(f"{ast} ast")
        line = ", ".join(parts)
        return f"Top performer: {name} ({line}; Game Score {best_score:.1f})."
    except Exception:
        try:
            best = max(stats, key=lambda s: _safe_int(s.points))
            return (
                f"Top performer: {best.player_name or 'Unknown player'} "
                f"({_safe_int(best.points)} pts)."
            )
        except Exception:
            return "No individual player stats recorded for this game."


def _bullet_biggest_run(events, quarter_points):
    # Primary: score-margin swing from GameEvents.
    try:
        margins = [
            e.score_margin
            for e in sorted(events, key=lambda e: (e.timestamp or 0))
            if e.score_margin is not None
        ]
    except Exception:
        margins = []
    if len(margins) >= 2:
        try:
            min_so_far = margins[0]
            max_rise = 0
            rise_start = margins[0]
            rise_end = margins[0]
            for margin in margins[1:]:
                if margin - min_so_far > max_rise:
                    max_rise = margin - min_so_far
                    rise_start = min_so_far
                    rise_end = margin
                if margin < min_so_far:
                    min_so_far = margin
            max_so_far = margins[0]
            max_fall = 0
            fall_start = margins[0]
            fall_end = margins[0]
            for margin in margins[1:]:
                if max_so_far - margin > max_fall:
                    max_fall = max_so_far - margin
                    fall_start = max_so_far
                    fall_end = margin
                if margin > max_so_far:
                    max_so_far = margin
            if max_rise == 0 and max_fall == 0:
                return "Score margin held steady across the recorded events; no run detected."
            if max_rise >= max_fall:
                return (
                    f"Biggest run: {max_rise}-point swing toward the team "
                    f"(margin {rise_start} to {rise_end})."
                )
            return (
                f"Biggest run: {max_fall}-point swing toward the opponent "
                f"(margin {fall_start} to {fall_end})."
            )
        except Exception:
            pass
    # Fallback: quarter splits (team margin per quarter when opp known,
    # else team scoring by quarter).
    try:
        if quarter_points and len(quarter_points) >= 2:
            known = {q: v for q, v in quarter_points.items() if v.get("opp_known")}
            if len(known) >= 2:
                margins_q = {q: v["team"] - v["opp"] for q, v in known.items()}
                best_q = max(margins_q, key=lambda q: margins_q[q])
                worst_q = min(margins_q, key=lambda q: margins_q[q])
                swing = margins_q[best_q] - margins_q[worst_q]
                return (
                    f"Biggest run: quarter swing of {swing} "
                    f"(best Q{best_q} {margins_q[best_q]:+d}, "
                    f"worst Q{worst_q} {margins_q[worst_q]:+d})."
                )
            team_only = {q: v["team"] for q, v in quarter_points.items()}
            best_q = max(team_only, key=lambda q: team_only[q])
            worst_q = min(team_only, key=lambda q: team_only[q])
            swing = team_only[best_q] - team_only[worst_q]
            return (
                f"Biggest run: team scoring swing of {swing} between quarters "
                f"(best Q{best_q} with {team_only[best_q]} pts, "
                f"Q{worst_q} with {team_only[worst_q]} pts)."
            )
    except Exception:
        pass
    return "Scoring-run data not available for this game."


def _bullet_quarter_shape(quarter_points):
    try:
        if not quarter_points:
            return "Quarter-by-quarter scoring not recorded for this game."
        ordered = sorted(quarter_points.items())
        opp_known_any = any(v.get("opp_known") for _, v in ordered)
        if opp_known_any:
            segments = [
                f"Q{q} {v['team']}-{v['opp']}" for q, v in ordered
            ]
            margins = {q: v["team"] - v["opp"] for q, v in ordered}
            best_q = max(margins, key=lambda q: margins[q])
            return (
                f"Quarter shape: {', '.join(segments)}; "
                f"strongest Q{best_q} ({margins[best_q]:+d})."
            )
        segments = [f"Q{q} {v['team']} pts" for q, v in ordered]
        best_q = max(ordered, key=lambda item: item[1]["team"])[0]
        return (
            f"Quarter shape (team points): {', '.join(segments)}; "
            f"strongest Q{best_q}."
        )
    except Exception:
        return "Quarter-by-quarter scoring not recorded for this game."


def _bullet_clutch(game, events):
    try:
        team_score = game.team_score
        opp_score = game.opponent_score
        final_margin = None
        if team_score is not None and opp_score is not None:
            final_margin = abs(team_score - opp_score)
    except Exception:
        final_margin = None

    clutch_hit = False
    has_clutch_window_data = False
    try:
        max_game_seconds = None
        for event in events:
            game_seconds = getattr(event, "game_seconds", None)
            if game_seconds is not None:
                try:
                    game_seconds = int(game_seconds)
                except (TypeError, ValueError):
                    continue
                if max_game_seconds is None or game_seconds > max_game_seconds:
                    max_game_seconds = game_seconds
        for event in events:
            margin = getattr(event, "score_margin", None)
            if margin is None:
                continue
            in_window = False
            game_seconds = getattr(event, "game_seconds", None)
            try:
                game_seconds = int(game_seconds) if game_seconds is not None else None
            except (TypeError, ValueError):
                game_seconds = None
            quarter = getattr(event, "quarter", None)
            try:
                quarter = int(quarter) if quarter is not None else None
            except (TypeError, ValueError):
                quarter = None
            if game_seconds is not None:
                if max_game_seconds is not None:
                    threshold = max(0, max_game_seconds - 300)
                    in_window = game_seconds >= threshold
                elif quarter is not None and quarter >= 4:
                    in_window = True
            elif quarter is not None and quarter >= 4:
                remaining = _parse_remaining_to_seconds(
                    getattr(event, "time_remaining", None)
                )
                if remaining is not None:
                    in_window = remaining <= 300
                else:
                    # Q4 event without clock detail: can't confirm window.
                    in_window = False
            if in_window:
                has_clutch_window_data = True
                if abs(margin) <= 5:
                    clutch_hit = True
                    break
    except Exception:
        clutch_hit = False

    try:
        if clutch_hit:
            if final_margin is not None:
                return (
                    "Clutch finish: game within 5 points in the last 5 minutes "
                    f"(final margin {final_margin})."
                )
            return "Clutch finish: game within 5 points in the last 5 minutes."
        if final_margin is not None and final_margin <= 5:
            return (
                "Clutch finish: final margin within 5 points "
                f"(margin {final_margin})."
            )
        if has_clutch_window_data:
            if final_margin is not None:
                return (
                    "No clutch-time pressure: margin stayed above 5 in the last "
                    f"5 minutes (final margin {final_margin})."
                )
            return "No clutch-time pressure: margin stayed above 5 in the last 5 minutes."
        if final_margin is not None:
            return (
                "Clutch data not available for the final 5 minutes; "
                f"final margin {final_margin}."
            )
    except Exception:
        pass
    return "Clutch data not available for this game."


def build_recap(game_id, team_id):
    """Build the 5-bullet recap for a game.

    Returns {"game_id": int, "bullets": [str x5]} or None when the game
    does not exist / does not belong to team_id. Never raises on
    sparse data.
    """
    try:
        game = (
            Game.query.filter_by(id=game_id, team_id=team_id).first()
            if team_id is not None
            else db.session.get(Game, game_id)
        )
    except Exception:
        return None
    if game is None:
        return None

    try:
        team = db.session.get(Team, team_id) if team_id is not None else None
        team_name = team.name if team and team.name else "Team"
    except Exception:
        team_name = "Team"

    try:
        events = (
            GameEvent.query.filter_by(game_id=game.id)
            .order_by(GameEvent.timestamp)
            .all()
        )
    except Exception:
        events = []
    try:
        shots = ShotEvent.query.filter_by(game_id=game.id).all()
    except Exception:
        shots = []

    try:
        quarter_points = _quarter_points(game.id, events, shots)
    except Exception:
        quarter_points = {}

    bullets = [
        _bullet_result(game, team_name),
        _bullet_top_performer(game.id),
        _bullet_biggest_run(events, quarter_points),
        _bullet_quarter_shape(quarter_points),
        _bullet_clutch(game, events),
    ]
    bullets = [
        bullet if isinstance(bullet, str) and bullet.strip() else "No data recorded."
        for bullet in bullets
    ]
    return {"game_id": game.id, "bullets": bullets}
