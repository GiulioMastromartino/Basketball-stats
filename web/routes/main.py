diff --git a/web/routes/main.py b/web/routes/main.py
index 0c224fe..9e7aa11 100644
--- a/web/routes/main.py
+++ b/web/routes/main.py
@@ -12,6 +12,7 @@ from flask_login import login_required
 from sqlalchemy import case, func
 
 from core.models import Game, PlayerStat, ShotEvent, db, Play
+from core.play_analytics import get_play_stats
 from core.csv_processor import CSVProcessor
 from core.parser import parse_game_pdf
 from core.services import create_game_from_live_data
@@ -161,51 +162,10 @@ def game_detail(game_id):
 
     # Fetch shot events for this game if available
     shot_events = ShotEvent.query.filter_by(game_id=game.id).all()
-
-    # --- Plays dashboard (offense only) ---
-    plays_agg = (
-        db.session.query(
-            Play.id.label("id"),
-            Play.name.label("name"),
-            func.count(ShotEvent.id).label("runs"),
-            func.sum(case((ShotEvent.result == "made", 1), else_=0)).label("made"),
-            func.sum(ShotEvent.points).label("points"),
-        )
-        .join(Play, Play.id == ShotEvent.play_id)
-        .filter(
-            ShotEvent.game_id == game.id,
-            ShotEvent.play_id.isnot(None),
-            Play.play_type == "Offense",
-        )
-        .group_by(Play.id, Play.name)
-        .order_by(func.count(ShotEvent.id).desc())
-        .all()
-    )
-
-    plays_data = []
-    for row in plays_agg:
-        runs = int(row.runs or 0)
-        made = int(row.made or 0)
-        points = int(row.points or 0)
-
-        fg_pct = round((made / runs * 100), 1) if runs > 0 else 0
-        ppp = round((points / runs), 2) if runs > 0 else 0
-
-        plays_data.append(
-            {
-                "id": row.id,
-                "name": row.name,
-                "runs": runs,
-                "made": made,
-                "fg_pct": fg_pct,
-                "points": points,
-                "ppp": ppp,
-            }
-        )
+
+    # --- Plays analysis dashboard (offense only) ---
+    plays_data = get_play_stats(game.id, play_type="Offense")
*** End Patch
