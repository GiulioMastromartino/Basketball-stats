#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.csv_processor import CSVProcessor
from core.models import Game, PlayerStat, db
from core.validators import DataValidator
from web import create_app


def import_all_csvs():
    print(f"Current working directory: {os.getcwd()}")

    app = create_app("development")
    with app.app_context():
        games_dir = Path(app.config["GAMES_DIR"])
        print(f"Looking for games in: {games_dir.absolute()}")

        if not games_dir.exists():
            print(f"ERROR: Directory {games_dir} does not exist!")
            return

        csv_files = sorted(games_dir.glob("*.csv"))
        print(f"Found {len(csv_files)} CSV files.")

        if not csv_files:
            print("No CSV files found. Listing directory contents:")
            for f in games_dir.iterdir():
                print(f" - {f.name}")
            return

        imported = 0
        skipped = 0
        errors = 0

        for csv_path in csv_files:
            print(f"Processing: {csv_path.name}")
            try:
                info = CSVProcessor.parse_filename(csv_path.name)
                if not info:
                    print(f"  XXX Invalid filename format: {csv_path.name}")
                    errors += 1
                    continue

                # Check duplicates
                existing = Game.query.filter_by(
                    sort_date=info["sort_date"], opponent=info["opponent"]
                ).first()

                if existing:
                    print(f"  --- Skipped (Already exists: {existing.id})")
                    skipped += 1
                    continue

                game_data = CSVProcessor.process_game(str(csv_path), info)
                if not game_data:
                    print("  XXX Failed to process CSV content")
                    errors += 1
                    continue

                # Create Game
                game = Game(
                    date=game_data["date"],
                    opponent=game_data["opponent"],
                    team_score=game_data["team_score"],
                    opponent_score=game_data["opponent_score"],
                    result=game_data["result"],
                    game_type=game_data["game_type"],
                    sort_date=game_data["sort_date"],
                )
                db.session.add(game)
                db.session.flush()

                # Create Stats
                for player in game_data["players"]:
                    # Basic validation to prevent crash
                    if not player.get("name"):
                        continue

                    stat = PlayerStat(
                        game_id=game.id,
                        player_name=player["name"],
                        minutes=player["minutes"],
                        points=player["points"],
                        fgm=player["fgm"],
                        fga=player["fga"],
                        fg_percent=player["fg_percent"],
                        tpm=player["tpm"],
                        tpa=player["tpa"],
                        tp_percent=player["tp_percent"],
                        ftm=player["ftm"],
                        fta=player["fta"],
                        ft_percent=player["ft_percent"],
                        oreb=player["oreb"],
                        dreb=player["dreb"],
                        reb=player["reb"],
                        ast=player["ast"],
                        tov=player["tov"],
                        stl=player["stl"],
                        blk=player["blk"],
                        pf=player["pf"],
                    )
                    db.session.add(stat)

                db.session.commit()
                print(f"  VVV Imported successfully")
                imported += 1

            except Exception as e:
                print(f"  XXX Error: {e}")
                import traceback

                traceback.print_exc()
                errors += 1
                db.session.rollback()

        print(f"\nSummary: Imported {imported} | Skipped {skipped} | Errors {errors}")


if __name__ == "__main__":
    import_all_csvs()
