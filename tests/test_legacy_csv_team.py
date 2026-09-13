"""Legacy web CSV upload (/upload-game, import_type=csv) must scope the
created Game to the session team.

Regression test: the legacy handler built Game(...) without team_id, so in
production every legacy CSV import died with
``IntegrityError: games.team_id NOT NULL``. (The pytest suite has a
test-only team backfill, so here the same root cause surfaces as the game
landing on the wrong team instead of raising.)
"""
import io

from core.models import Game, PlayerStat

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


def _legacy_upload(client, csv_text=VALID_CSV, filename=FILENAME,
                   follow_redirects=False):
    return client.post(
        "/upload-game",
        data={
            "import_type": "csv",
            "csv_file": (io.BytesIO(csv_text.encode("utf-8")), filename),
        },
        content_type="multipart/form-data",
        follow_redirects=follow_redirects,
    )


def _flashes(client):
    with client.session_transaction() as sess:
        return [(c, m) for c, m in sess.get("_flashes", [])]


def test_legacy_upload_imports_with_session_team(auth_client, default_team):
    """Imported game must carry team_id from the session (not NULL/other)."""
    resp = _legacy_upload(auth_client)
    assert resp.status_code == 302  # redirect to index on completion

    game = Game.query.filter_by(
        sort_date="2025-03-15", opponent="Lakers",
        team_id=default_team.id,
    ).first()
    assert game is not None, (
        f"legacy CSV import did not create a game for team {default_team.id}; "
        f"all games: {[(g.opponent, g.sort_date, g.team_id) for g in Game.query.all()]}"
    )
    assert game.team_score == 95
    assert game.opponent_score == 88
    assert game.result == "W"

    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    assert len(stats) == 2  # Total row skipped
    assert {s.player_name for s in stats} == {"John Doe", "Jane Smith"}

    flashes = " ".join(m for _, m in _flashes(auth_client))
    assert "Successfully imported 1 CSV game" in flashes


def test_legacy_upload_duplicate_handled_as_before(auth_client, default_team):
    """Re-uploading the same CSV must report 'already exists', no new game."""
    first = _legacy_upload(auth_client)
    assert first.status_code == 302
    assert Game.query.filter_by(team_id=default_team.id).count() == 1

    second = _legacy_upload(auth_client)
    assert second.status_code == 302
    flashes = " ".join(m for _, m in _flashes(auth_client))
    assert "already exists" in flashes
    assert Game.query.filter_by(team_id=default_team.id).count() == 1


def test_legacy_upload_unauthenticated_redirect(client):
    """Unauthenticated POST/GET to /upload-game must redirect to login."""
    resp = _legacy_upload(client)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")

    get_resp = client.get("/upload-game")
    assert get_resp.status_code == 302
    assert "/auth/login" in get_resp.headers.get("Location", "")
    assert Game.query.count() == 0
