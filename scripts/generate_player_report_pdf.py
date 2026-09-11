#!/usr/bin/env python3
"""Generate a player report PDF without starting the web app.

Usage:
    python scripts/generate_player_report_pdf.py <player_name> [--game-type Season|Friendly|ALL]

Examples:
    python scripts/generate_player_report_pdf.py Fernandez
    python scripts/generate_player_report_pdf.py Fernandez --game-type Season
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from io import BytesIO
from weasyprint import HTML
from flask import render_template

from web import create_app
from core.models import Game, Team, db
from core.services.report_service import _generate_player_report_data


def main():
    parser = argparse.ArgumentParser(description="Generate a player report PDF")
    parser.add_argument("player_name", help="Player name")
    parser.add_argument("--game-type", default="ALL", choices=["ALL", "Season", "Friendly"])
    parser.add_argument("--output", "-o", default=None, help="Output PDF path")
    args = parser.parse_args()

    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(os.getcwd(), 'basketball_stats.db')}"

    from config import DevelopmentConfig
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URL"]

    app = create_app("development")

    with app.app_context():
        teams = Team.query.all()
        if not teams:
            print("No teams found in database.")
            sys.exit(1)

        team_id = teams[0].id

        query = Game.query.filter(Game.team_id == team_id).order_by(Game.sort_date.asc())
        if args.game_type == "Season":
            query = query.filter(Game.game_type == "Season")
        elif args.game_type == "Friendly":
            query = query.filter(Game.game_type == "Friendly")
        games = query.all()
        game_ids = [g.id for g in games]

        if not games:
            print(f"No games found for team '{teams[0].name}' with game_type '{args.game_type}'.")
            sys.exit(1)

        print(f"Team: {teams[0].name}")
        print(f"Games: {len(games)} ({args.game_type})")
        print(f"Player: {args.player_name}")

        try:
            context = _generate_player_report_data(
                args.player_name, games, game_ids, args.game_type
            )
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

        with app.test_request_context():
            from flask import session as fsession
            fsession["current_team_id"] = team_id
            fsession["current_team_name"] = teams[0].name
            fsession["_permanent"] = True

            html = render_template("player_report_pdf.html", **context)

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pdf_bytes = HTML(string=html, base_url=f"file://{project_root}/").write_pdf()

        output = args.output or f"{args.player_name.replace(' ', '_')}_report_{args.game_type}.pdf"
        with open(output, "wb") as f:
            f.write(pdf_bytes)

        print(f"PDF generated: {output} ({len(pdf_bytes)} bytes)")


if __name__ == "__main__":
    main()
