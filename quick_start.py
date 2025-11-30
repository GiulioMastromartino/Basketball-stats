#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.models import Game, PlayerStat, User, db
from web import create_app


def create_sample_data():
    games = [
        {
            "date": "15/03",
            "opponent": "Lakers",
            "team_score": 105,
            "opponent_score": 98,
            "result": "W",
            "game_type": "Season",
            "sort_date": "2024-03-15",
        },
        {
            "date": "20/03",
            "opponent": "Warriors",
            "team_score": 92,
            "opponent_score": 95,
            "result": "L",
            "game_type": "Season",
            "sort_date": "2024-03-20",
        },
        {
            "date": "25/03",
            "opponent": "Celtics",
            "team_score": 110,
            "opponent_score": 108,
            "result": "W",
            "game_type": "Playoff",
            "sort_date": "2024-03-25",
        },
    ]
    players = [
        {"name": "John Doe", "points": 28, "reb": 8, "ast": 6},
        {"name": "Jane Smith", "points": 22, "reb": 12, "ast": 4},
        {"name": "Mike Johnson", "points": 18, "reb": 5, "ast": 9},
    ]
    for gd in games:
        game = Game(**gd)
        db.session.add(game)
        db.session.flush()
        for p in players:
            stat = PlayerStat(
                game_id=game.id,
                player_name=p["name"],
                points=p["points"],
                reb=p["reb"],
                ast=p["ast"],
                minutes="30:00",
                fgm=int(p["points"] * 0.4),
                fga=int(p["points"] * 0.8),
                fg_percent=50.0,
                tpm=2,
                tpa=5,
                tp_percent=40.0,
                ftm=2,
                fta=3,
                ft_percent=66.7,
                oreb=2,
                dreb=p["reb"] - 2,
                stl=2,
                blk=1,
                tov=2,
                pf=2,
            )
            db.session.add(stat)
    db.session.commit()
    print("✓ Sample data created")


def setup_local_environment():
    print("=" * 60)
    print("BASKETBALL STATS ANALYZER - LOCAL SETUP")
    print("=" * 60)
    app = create_app("development")
    with app.app_context():
        db.create_all()
        print("✓ Database created")
        if User.query.filter_by(username="admin").first() is None:
            admin = User(username="admin", email="admin@local.com", is_admin=True)
            admin.set_password(os.getenv("ADMIN_PASSWORD", "admin123"))
            db.session.add(admin)
            db.session.commit()
            print("✓ Admin: admin/admin123")
        if Game.query.count() == 0:
            create_sample_data()
        for folder in [app.config["GAMES_DIR"], app.config["OUTPUT_DIR"]]:
            os.makedirs(folder, exist_ok=True)
    print("\nReady! Open http://localhost:8080\n")
    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Basketball Stats - Quick Start")
    parser.add_argument(
        "--no-run", action="store_true", help="Setup database only, don't start server"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Reset database before setup"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run server on (default: 8080)"
    )
    args = parser.parse_args()

    if args.reset:
        Path("basketball_stats.db").unlink(missing_ok=True)
        print("Database reset.\n")

    app = setup_local_environment()

    if not args.no_run:  # START BY DEFAULT
        app.run(host="0.0.0.0", port=args.port, debug=True)
    else:
        print("Setup complete. Run 'python quick_start.py' to start server.")
