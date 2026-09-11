#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.models import db, Game, LineupSegment, GameEvent, PlayerLineupStats, Lineup
from core.services.lineup_service import calculate_segment_duration

def recalc_all():
    segments = LineupSegment.query.order_by(LineupSegment.game_id, LineupSegment.id).all()
    print(f"Processing {len(segments)} segments...")
    affected_lineup_ids = set()

    for seg in segments:
        events = GameEvent.query.filter_by(lineup_segment_id=seg.id).order_by(GameEvent.timestamp).all()
        pts_scored = 0
        pts_allowed = 0
        poss = 0
        poss_ending = set()
        reb_conceded = 0

        for ev in events:
            et = ev.event_type
            if et == "SHOT_2PT" and ev.shot_attempt == "made":
                pts_scored += 2
            elif et == "SHOT_3PT" and ev.shot_attempt == "made":
                pts_scored += 3
            elif et == "FT_MADE":
                pts_scored += 1
            elif et == "OPP_SCORE":
                pts = 2
                if ev.detail:
                    try:
                        if isinstance(ev.detail, str) and (ev.detail.startswith('{') or ev.detail.startswith('[')):
                            import json
                            detail_data = json.loads(ev.detail)
                            if isinstance(detail_data, dict):
                                pts = int(detail_data.get('points', 2))
                            else:
                                pts = int(ev.detail)
                        else:
                            pts = int(ev.detail)
                    except (ValueError, TypeError, json.JSONDecodeError):
                        pts = 2
                pts_allowed += pts
            elif et == "OPP_OREB":
                reb_conceded += 1

            if et in ["SHOT_2PT", "SHOT_3PT", "TURNOVER", "FT", "FT_MADE", "FT_MISS"]:
                if ev.possession_number and ev.possession_number not in poss_ending:
                    poss_ending.add(ev.possession_number)
                    poss += 1

        seg.points_scored = pts_scored
        seg.points_allowed = pts_allowed
        seg.possessions = poss
        seg.reb_conceded = reb_conceded

        seg.duration_seconds = calculate_segment_duration(events)

        if seg.lineup_id:
            affected_lineup_ids.add(seg.lineup_id)

    db.session.commit()
    print(f"Updated {len(segments)} segments, affecting {len(affected_lineup_ids)} lineups")

    for lid in sorted(affected_lineup_ids):
        from core.services.lineup_service import update_lineup_cached_stats
        update_lineup_cached_stats(lid)

    print("Done.")

if __name__ == "__main__":
    from run import app
    with app.app_context():
        recalc_all()
