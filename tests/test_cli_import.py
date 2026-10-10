"""Regression tests for cli_import.py — the documented quick-start import path.

D1: the CLI built ``Game(...)`` without ``team_id`` while
``core/models.py`` declares ``games.team_id`` NOT NULL. In a real database
every import therefore died with
``IntegrityError: NOT NULL constraint failed: games.team_id`` and the run
reported ``Imported 0``. Games are multi-tenant, so the CLI must resolve the
target team (``--team`` / ``--team-id`` / ``IMPORT_TEAM`` / ``IMPORT_TEAM_ID``
env vars, else the first team of the current org) and refuse to import
without one.

D2: the loop printed a raw traceback per file, a neutral summary line, and
exited 0. Now the reason is reported per file, the failure banner is printed,
and the process exits non-zero.
"""
from pathlib import Path

import pytest
from sqlalchemy import text

import cli_import
from core.models import Game, Organization, PlayerStat, Team

HEADER = ("Name,MIN,PTS,FGM,FGA,FG%,3PM,3PA,3P%,FTM,FTA,FT%,"
          "OREB,DREB,REB,AST,TOV,STL,BLK,PF")
ROW1 = ("John Doe,24:30,18,7,14,50.0,2,5,40.0,2,3,66.7,"
        "1,4,5,3,2,1,2,3")
ROW2 = ("Jane Smith,28:15,22,9,16,56.2,3,7,42.9,1,2,50.0,"
        "2,5,7,4,3,1,0,2")
TOTAL = ("Total,52:45,40,16,30,53.3,5,12,41.7,3,5,60.0,"
         "3,9,12,7,5,2,2,5")

VALID_CSV = "\n".join([HEADER, ROW1, ROW2, TOTAL]) + "\n"
FILENAME = "Lakers_95-88_15-03-2025_S.csv"

# A second team in the same org: proves the CLI passes the SELECTED team and
# not just whatever the test-only team backfill happens to fill in.
OTHER_FILENAME = "Celtics_101-99_20-03-2025_P.csv"


def _make_team(name, slug):
    org = Organization.query.first()
    team = Team(name=name, slug=slug, organization_id=org.id)
    db = cli_import.db
    db.session.add(team)
    db.session.commit()
    return team


def _write_csv(directory, filename=FILENAME, content=VALID_CSV):
    path = Path(directory) / filename
    path.write_text(content, encoding="utf-8")
    return path


def _null_team_games():
    """Games with no team — what the bug used to try (and fail) to create."""
    return cli_import.db.session.execute(
        text("SELECT COUNT(*) FROM games WHERE team_id IS NULL")
    ).scalar()


# ---------------------------------------------------------------------------
# D1 — team_id is resolved and written
# ---------------------------------------------------------------------------


def test_import_sets_team_id_on_every_game(app, db_session, tmp_path):
    team = _make_team("Alpha", "alpha")
    _write_csv(tmp_path)

    result = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team_id=team.id
    )

    assert result["imported"] == 1, result
    assert result["errors"] == 0, result
    game = Game.query.filter_by(opponent="Lakers").one()
    assert game.team_id == team.id
    assert game.team_score == 95
    assert game.opponent_score == 88
    assert game.result == "W"
    assert game.sort_date == "2025-03-15"
    assert _null_team_games() == 0
    # Player stats hang off the game, so the Total row is still skipped.
    assert PlayerStat.query.filter_by(game_id=game.id).count() == 2


def test_import_honours_selected_team(app, db_session, tmp_path):
    """Two teams exist: the games must land on the one that was asked for."""
    first = _make_team("Alpha", "alpha")
    second = _make_team("Bravo", "bravo")
    _write_csv(tmp_path)
    assert first.id != second.id

    result = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team_id=second.id
    )

    assert result["imported"] == 1
    game = Game.query.filter_by(opponent="Lakers").one()
    assert game.team_id == second.id
    assert [g.team_id for g in Game.query.all()] == [second.id]


def test_import_by_team_name_and_slug(app, db_session, tmp_path):
    _make_team("Alpha", "alpha")
    _make_team("Bravo", "bravo")
    _write_csv(tmp_path)
    target = Team.query.filter_by(slug="bravo").one()

    by_name = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team="Bravo"
    )
    by_slug = cli_import.resolve_team(team="bravo")

    assert by_name["imported"] == 1
    assert by_slug.id == target.id
    assert Game.query.filter_by(opponent="Lakers").one().team_id == target.id
    assert _null_team_games() == 0


def test_team_id_flag_wins_over_team_name(app, db_session, tmp_path):
    _make_team("Alpha", "alpha")
    bravo = _make_team("Bravo", "bravo")
    _write_csv(tmp_path)

    result = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team="Alpha", team_id=bravo.id
    )

    assert result["imported"] == 1
    assert Game.query.one().team_id == bravo.id


def test_default_team_is_the_first_of_the_current_org(app, db_session, tmp_path):
    _make_team("Alpha", "alpha")
    _make_team("Bravo", "bravo")
    _write_csv(tmp_path)
    expected = Team.query.order_by(
        Team.organization_id, Team.id
    ).first()

    result = cli_import.import_all_csvs(app=app, games_dir=str(tmp_path))

    assert expected is not None
    assert result["imported"] == 1
    assert result["team_id"] == expected.id
    game = Game.query.one()
    assert game.team_id == expected.id
    assert _null_team_games() == 0


def test_import_without_any_team_fails_loudly(app, db_session, tmp_path):
    """No team can be resolved => refuse, never write a team-less game."""
    # The suite's autouse fixture provisions a fallback team; drop it so the
    # database genuinely has nothing to import into.
    cli_import.db.session.execute(text("DELETE FROM teams"))
    cli_import.db.session.commit()
    _write_csv(tmp_path)

    with pytest.raises(cli_import.TeamResolutionError) as excinfo:
        cli_import.import_all_csvs(app=app, games_dir=str(tmp_path))

    assert "no team" in str(excinfo.value)
    assert Game.query.count() == 0


def test_unknown_team_name_and_id_are_rejected(app, db_session, tmp_path):
    _make_team("Alpha", "alpha")

    with pytest.raises(cli_import.TeamResolutionError) as name_err:
        cli_import.resolve_team(team="Nobody")
    assert "no team named" in str(name_err.value)

    with pytest.raises(cli_import.TeamResolutionError) as id_err:
        cli_import.resolve_team(team_id=4242)
    assert "no team with id 4242" in str(id_err.value)


def test_ambiguous_team_name_points_at_team_id(app, db_session, tmp_path):
    org = Organization.query.first()
    cli_import.db.session.add(Team(name="Dup", slug="dup-1", organization_id=org.id))
    cli_import.db.session.add(Team(name="Dup", slug="dup-2", organization_id=org.id))
    cli_import.db.session.commit()

    with pytest.raises(cli_import.TeamResolutionError) as excinfo:
        cli_import.resolve_team(team="Dup")

    assert "--team-id" in str(excinfo.value)


# ---------------------------------------------------------------------------
# D1 — duplicate detection still works, scoped to the team
# ---------------------------------------------------------------------------


def test_reimport_skips_existing_games(app, db_session, tmp_path):
    _make_team("Alpha", "alpha")
    _write_csv(tmp_path)

    first = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team="Alpha"
    )
    second = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team="Alpha"
    )

    assert (first["imported"], first["skipped"]) == (1, 0)
    assert (second["imported"], second["skipped"]) == (0, 1)
    assert second["errors"] == 0
    assert Game.query.count() == 1


def test_duplicate_check_is_scoped_to_the_team(app, db_session, tmp_path):
    """Another team playing the same opponent on the same date is not a dupe."""
    _make_team("Alpha", "alpha")
    bravo = _make_team("Bravo", "bravo")
    _write_csv(tmp_path)

    first = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team="Alpha"
    )
    assert (first["imported"], first["skipped"]) == (1, 0)

    # Same opponent/date again in the folder: a different team importing it is
    # NOT a duplicate, otherwise team B could never import team A's games.
    _write_csv(tmp_path, OTHER_FILENAME)
    other = cli_import.import_all_csvs(
        app=app, games_dir=str(tmp_path), team_id=bravo.id
    )

    assert (other["imported"], other["skipped"]) == (2, 0)
    assert Game.query.count() == 3
    assert Game.query.filter_by(opponent="Lakers").count() == 2
    assert Game.query.filter_by(team_id=bravo.id).count() == 2


# ---------------------------------------------------------------------------
# D2 — obvious, non-zero exit on failure
# ---------------------------------------------------------------------------


def test_failed_file_is_reported_and_exits_nonzero(
    app, db_session, capsys, monkeypatch, tmp_path
):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")
    _write_csv(tmp_path)
    _write_csv(tmp_path, "not-a-boxscore.csv", "garbage,no,players\n")

    exit_code = cli_import.main(["--games-dir", str(tmp_path), "--team", "Alpha"])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "Invalid filename format" in out
    assert "not-a-boxscore.csv" in out
    assert "IMPORT FAILED" in out
    assert "Errors 1" in out
    # No raw traceback dumped in the user's face.
    assert "Traceback" not in out
    # The good file is still imported; the bad one is not.
    assert Game.query.filter_by(opponent="Lakers").count() == 1


def test_csv_without_player_rows_is_reported(app, db_session, capsys,
                                             monkeypatch, tmp_path):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")
    _write_csv(tmp_path, "OnlyTotal_70-60_01-01-2025_S.csv",
               "Name,MIN,PTS\nTotal,40:00,0\n")

    exit_code = cli_import.main(["--games-dir", str(tmp_path)])
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "no player rows" in out
    assert Game.query.count() == 0


def test_unresolvable_team_exits_nonzero_with_help(
    app, db_session, capsys, monkeypatch, tmp_path
):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")
    _write_csv(tmp_path)

    exit_code = cli_import.main(
        ["--games-dir", str(tmp_path), "--team", "Nobody"]
    )
    out = capsys.readouterr().out

    assert exit_code == 2
    assert "no team named 'Nobody'" in out
    assert "Alpha" in out  # lists the teams that DO exist
    assert Game.query.count() == 0


def test_empty_database_cannot_import(app, db_session, capsys,
                                      monkeypatch, tmp_path):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    cli_import.db.session.execute(text("DELETE FROM teams"))
    cli_import.db.session.commit()
    _write_csv(tmp_path)

    exit_code = cli_import.main(["--games-dir", str(tmp_path)])
    out = capsys.readouterr().out

    assert exit_code == 2
    assert "no team to import into" in out
    assert "quick_start.py" in out
    assert Game.query.count() == 0


def test_missing_games_dir_exits_nonzero(app, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")

    exit_code = cli_import.main(
        ["--games-dir", str(tmp_path / "nope"), "--team", "Alpha"]
    )

    assert exit_code == 2


def test_successful_import_exits_zero(
    app, db_session, capsys, monkeypatch, tmp_path
):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")
    _write_csv(tmp_path)

    exit_code = cli_import.main(["--games-dir", str(tmp_path), "--team", "Alpha"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "Summary: Imported 1 | Skipped 0 | Errors 0" in out
    # Re-running an already-imported folder is a success, not a failure.
    assert cli_import.main(
        ["--games-dir", str(tmp_path), "--team", "Alpha"]
    ) == 0
    assert "Summary: Imported 0 | Skipped 1 | Errors 0" in capsys.readouterr().out


def test_env_var_selects_the_team(app, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")
    bravo = _make_team("Bravo", "bravo")
    _write_csv(tmp_path)
    monkeypatch.setenv(cli_import.TEAM_ID_ENV_VAR, str(bravo.id))

    exit_code = cli_import.main(["--games-dir", str(tmp_path)])

    assert exit_code == 0
    assert Game.query.one().team_id == bravo.id


def test_invalid_env_team_id_is_rejected(
    app, db_session, monkeypatch, tmp_path
):
    monkeypatch.setattr(cli_import, "create_app", lambda *a, **k: app)
    _make_team("Alpha", "alpha")
    monkeypatch.setenv(cli_import.TEAM_ID_ENV_VAR, "not-a-number")

    exit_code = cli_import.main(["--games-dir", str(tmp_path)])

    assert exit_code == 2


# ---------------------------------------------------------------------------
# csv_processor: the reason for an unreadable file must reach the CLI
# ---------------------------------------------------------------------------


def test_process_game_reports_its_error(tmp_path):
    from core.csv_processor import CSVProcessor

    bad = tmp_path / "Raw_70-60_02-02-2025_S.csv"
    bad.write_bytes(b"\xff\xfe\x00garbage")
    info = CSVProcessor.parse_filename(bad.name)
    assert info is not None

    errors = []
    assert CSVProcessor.process_game(str(bad), info, errors) is None
    assert errors and "codec" in errors[0]

    # Legacy two-argument call still works and simply returns None.
    assert CSVProcessor.process_game(str(bad), info) is None
