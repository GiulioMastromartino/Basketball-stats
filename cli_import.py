#!/usr/bin/env python3
"""Bulk-import the box-score CSVs in ``Games/`` into the database.

Games are multi-tenant: ``games.team_id`` is NOT NULL and every stat row hangs
off a game, so the target team MUST be resolved before the first INSERT. This
script therefore picks the team up front (``--team`` / ``--team-id`` /
``IMPORT_TEAM`` / ``IMPORT_TEAM_ID`` env vars, otherwise the first team of the
current organization) and aborts with an actionable message when it cannot.

Usage::

    python cli_import.py                      # default team, Games/ folder
    python cli_import.py --team "Dev Team"    # by name (or slug)
    python cli_import.py --team-id 3
    IMPORT_TEAM_ID=3 python cli_import.py
    python cli_import.py --games-dir /tmp/games

Exit codes: 0 = every CSV imported or already present, 1 = at least one CSV
failed (or nothing could be imported or skipped), 2 = bad usage (unresolvable
team, missing games folder).
"""
import argparse
import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.csv_processor import CSVProcessor
from core.models import Game, PlayerStat, Team, db
from web import create_app

# Team selection precedence, first match wins:
#   1. --team-id / --team on the command line
#   2. IMPORT_TEAM_ID / IMPORT_TEAM environment variables
#   3. the first team of the current organization (id order)
TEAM_ENV_VAR = "IMPORT_TEAM"
TEAM_ID_ENV_VAR = "IMPORT_TEAM_ID"

# Shown whenever a filename cannot be understood, so the user knows what to
# rename the file to instead of just seeing "invalid filename format".
FILENAME_HINT = (
    "expected Opponent_TeamScore-OppScore_DD-MM-YYYY_[F/S/P].csv "
    "(ISO dates as Opponent_TeamScore-OppScore_YYYY-MM-DD_[F/S/P].csv work too)"
)

EXIT_OK = 0
EXIT_IMPORT_ERROR = 1
EXIT_USAGE_ERROR = 2


class TeamResolutionError(RuntimeError):
    """No single team could be resolved as the import target."""


def _team_choices(teams=None):
    """Render the available teams for an error message."""
    if teams is None:
        teams = Team.query.order_by(Team.id).all()
    if not teams:
        return "(no teams in this database)"
    return ", ".join(f"{t.id}={t.name}" for t in teams)


def resolve_team(team=None, team_id=None):
    """Resolve the team the games will be imported into.

    Accepts an explicit id (``team_id``) or a team name/slug
    (``team``, case-insensitive). Falls back to the first team of the current
    organization. Raises :class:`TeamResolutionError` with an actionable
    message when nothing matches unambiguously, so a multi-tenant import can
    never silently create team-less games.
    """
    if team_id is not None:
        match = Team.query.filter_by(id=int(team_id)).first()
        if match is None:
            raise TeamResolutionError(
                f"no team with id {team_id}. Existing teams: {_team_choices()}"
            )
        return match

    if team:
        wanted = str(team).strip().lower()
        matches = [
            t for t in Team.query.order_by(Team.id)
            if t.name.strip().lower() == wanted
            or t.slug.strip().lower() == wanted
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise TeamResolutionError(
                f"team {team!r} matches {len(matches)} teams "
                f"({_team_choices(matches)}); use --team-id to disambiguate."
            )
        raise TeamResolutionError(
            f"no team named {team!r}. Existing teams: {_team_choices()}"
        )

    # Default: the first team of the current organization.
    fallback = Team.query.order_by(Team.organization_id, Team.id).first()
    if fallback is None:
        raise TeamResolutionError(
            "no team to import into: this database has no teams. Create an "
            "organization and a team first (python quick_start.py), or pass "
            "--team/--team-id."
        )
    return fallback


def _short_reason(exc):
    """One-line reason for a failed file.

    SQLAlchemy errors render as the driver message followed by the failing
    SQL and its parameters; only the first line says what went wrong.
    """
    lines = str(exc).strip().splitlines()
    first = lines[0].strip() if lines else ""
    if not first:
        first = exc.__class__.__name__
    elif exc.__class__.__name__.lower() not in first.lower():
        first = f"{exc.__class__.__name__}: {first}"
    return first


def _record_failure(result, filename, reason):
    """Count a failed file and remember why (for the summary banner)."""
    result["errors"] += 1
    result["failures"].append((filename, reason))


def import_all_csvs(app=None, games_dir=None, team=None, team_id=None):
    """Import every ``*.csv`` found in ``games_dir``.

    Returns a summary dict (``files``/``imported``/``skipped``/``errors``/
    ``failures``) instead of only printing, so callers and tests can inspect
    the outcome. ``app`` may be injected to reuse an already-configured
    application (tests do this); otherwise a development app is created.
    """
    result = {
        "files": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
        "failures": [],  # [(filename, reason), ...]
        "team_id": None,
        "team_name": None,
    }

    print(f"Current working directory: {os.getcwd()}")

    if app is None:
        app = create_app("development")
    with app.app_context():
        games_dir = Path(games_dir or app.config["GAMES_DIR"])
        print(f"Looking for games in: {games_dir.absolute()}")

        if not games_dir.exists():
            result["fatal"] = f"Directory {games_dir} does not exist!"
            print(f"ERROR: {result['fatal']}")
            return result

        csv_files = sorted(games_dir.glob("*.csv"))
        print(f"Found {len(csv_files)} CSV files.")
        result["files"] = len(csv_files)

        if not csv_files:
            print("No CSV files found. Listing directory contents:")
            for f in games_dir.iterdir():
                print(f" - {f.name}")
            return result

        # Never write a game without a team: resolve the target once, up front,
        # and refuse to import anything when it cannot be resolved.
        target_team = resolve_team(team=team, team_id=team_id)
        result["team_id"] = target_team.id
        result["team_name"] = target_team.name
        print(f"Importing into team: {target_team.name} (id={target_team.id})")

        for csv_path in csv_files:
            print(f"Processing: {csv_path.name}")
            try:
                info = CSVProcessor.parse_filename(csv_path.name)
                if not info:
                    reason = f"Invalid filename format; {FILENAME_HINT}"
                    print(f"  XXX {reason}")
                    _record_failure(result, csv_path.name, reason)
                    continue

                # Check duplicates (scoped to the team we import into, so the
                # same opponent/date played by another team is not skipped).
                existing = Game.query.filter_by(
                    team_id=target_team.id,
                    sort_date=info["sort_date"],
                    opponent=info["opponent"],
                ).first()

                if existing:
                    print(f"  --- Skipped (Already exists: {existing.id})")
                    result["skipped"] += 1
                    continue

                parse_errors = []
                game_data = CSVProcessor.process_game(
                    str(csv_path), info, parse_errors
                )
                if not game_data:
                    detail = parse_errors[0] if parse_errors else "unreadable file"
                    reason = f"Could not read the CSV file ({detail})"
                    print(f"  XXX Failed to process CSV content: {reason}")
                    _record_failure(result, csv_path.name, reason)
                    continue
                if not game_data.get("players"):
                    reason = "CSV parsed but contains no player rows"
                    print(f"  XXX Failed to process CSV content: {reason}")
                    _record_failure(result, csv_path.name, reason)
                    continue

                # Create Game (team_id is NOT NULL: games belong to a team)
                game = Game(
                    team_id=target_team.id,
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
                        plus_minus=player.get("plus_minus", 0),
                    )
                    db.session.add(stat)

                db.session.commit()
                print(f"  VVV Imported successfully")
                result["imported"] += 1

            except Exception as e:
                # Report a readable one-line reason (not a raw traceback) and
                # roll back this file's partial writes.
                reason = _short_reason(e)
                print(f"  XXX Error: {reason}")
                _record_failure(result, csv_path.name, reason)
                db.session.rollback()

        print(f"\nSummary: Imported {result['imported']} | "
              f"Skipped {result['skipped']} | Errors {result['errors']}")

        if result["failures"]:
            print("\n" + "=" * 70)
            print(f"IMPORT FAILED: {len(result['failures'])} of "
                  f"{result['files']} CSV file(s) were not imported "
                  f"(team {result['team_name']} id={result['team_id']}):")
            for name, reason in result["failures"]:
                print(f"  - {name}: {reason}")
            print("=" * 70)

    return result


def _record_failure(result, filename, reason):
    """Count a failed file and remember why (for the summary banner)."""
    result["errors"] += 1
    result["failures"].append((filename, reason))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import box-score CSVs from the Games/ folder into the "
                    "database.",
    )
    parser.add_argument(
        "--team",
        help="Target team, by name or slug (case-insensitive). Defaults to the "
             "first team of the current organization. --team-id wins when "
             "both are given.",
    )
    parser.add_argument(
        "--team-id",
        type=int,
        help="Target team id (takes precedence over --team).",
    )
    parser.add_argument(
        "--games-dir",
        help="Directory to import from (default: the app's GAMES_DIR).",
    )
    args = parser.parse_args(argv)

    # CLI flag > env var > app default.
    team = args.team or os.getenv(TEAM_ENV_VAR) or None
    team_id = args.team_id
    if team_id is None and os.getenv(TEAM_ID_ENV_VAR, "").strip():
        try:
            team_id = int(os.getenv(TEAM_ID_ENV_VAR).strip())
        except ValueError:
            print(f"ERROR: {TEAM_ID_ENV_VAR} must be a team id (an integer), "
                  f"got {os.getenv(TEAM_ID_ENV_VAR)!r}")
            return EXIT_USAGE_ERROR

    try:
        result = import_all_csvs(
            games_dir=args.games_dir, team=team, team_id=team_id
        )
    except TeamResolutionError as e:
        # No team => no games can be created; say so instead of failing every
        # row with a NOT NULL constraint error.
        print(f"\nERROR: {e}")
        return EXIT_USAGE_ERROR

    if result.get("fatal"):
        return EXIT_USAGE_ERROR

    # Any failed file, or a run that found files but could neither import nor
    # skip a single one, is a failure: an import that silently does nothing
    # must not exit 0. A fully-skipped re-run (everything already imported) is
    # a success.
    if result["errors"]:
        return EXIT_IMPORT_ERROR
    if result["files"] and not result["imported"] and not result["skipped"]:
        return EXIT_IMPORT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
