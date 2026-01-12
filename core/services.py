from core.models import Game, PlayerStat, ShotEvent, db
from core.utils import normalize_date_to_display

def create_game_from_live_data(data):
    """
    Creates a new Game, PlayerStats, and ShotEvents from the JSON data payload.
    """
    if not data:
        raise ValueError("No data received")

    # Create Game
    game = Game(
        date=normalize_date_to_display(data.get("date")),
        opponent=data.get("opponent"),
        team_score=int(data.get("team_score", 0)),
        opponent_score=int(data.get("opponent_score", 0)),
        result="W" if int(data.get("team_score", 0)) > int(data.get("opponent_score", 0)) else "L",
        game_type=data.get("game_type", "Season"),
        sort_date=data.get("date"), # Assuming front-end sends YYYY-MM-DD
        source="LIVE",
    )
    db.session.add(game)
    db.session.flush()

    # Create Player Stats
    for p_name, stats in data.get("player_stats", {}).items():
        if not p_name:
            continue
        
        # Calculate percentages
        fg_pct = (stats["fgm"] / stats["fga"] * 100) if stats["fga"] > 0 else 0.0
        tp_pct = (stats["tpm"] / stats["tpa"] * 100) if stats["tpa"] > 0 else 0.0
        ft_pct = (stats["ftm"] / stats["fta"] * 100) if stats["fta"] > 0 else 0.0

        new_stat = PlayerStat(
            game_id=game.id,
            player_name=p_name,
            minutes=stats.get("minutes", "00:00"),
            points=stats["points"],
            fgm=stats["fgm"],
            fga=stats["fga"],
            fg_percent=fg_pct,
            tpm=stats["tpm"],
            tpa=stats["tpa"],
            tp_percent=tp_pct,
            ftm=stats["ftm"],
            fta=stats["fta"],
            ft_percent=ft_pct,
            oreb=stats["oreb"],
            dreb=stats["dreb"],
            reb=stats["oreb"] + stats["dreb"],
            ast=stats["ast"],
            tov=stats["tov"],
            stl=stats["stl"],
            blk=stats["blk"],
            pf=stats["pf"],
            plus_minus=int(stats.get("plus_minus", 0) or 0),
        )
        db.session.add(new_stat)

    # Create Shot Events (made shots only, from click-map)
    # NOTE: current frontend only logs location for made 2pt/3pt.
    for ev in data.get("shot_locations", []) or []:
        shooter = (ev.get("shooter") or "").strip()
        shot_type = (ev.get("type") or "").strip()   # 2pt / 3pt
        points = int(ev.get("points") or 0)

        # store the raw SVG coords (x,y) as floats; can be normalized later
        x = ev.get("x")
        y = ev.get("y")
        q = ev.get("quarter")

        shot = ShotEvent(
            game_id=game.id,
            player_name=shooter,
            shot_type=shot_type,
            result="made",
            points=points,
            x_loc=float(x) if x is not None else None,
            y_loc=float(y) if y is not None else None,
            quarter=int(q) if q is not None else None,
        )
        db.session.add(shot)

    db.session.commit()
    return game
