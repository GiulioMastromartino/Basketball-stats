"""Legacy web PDF upload (/upload-game, import_type=pdf) must scope the
created Game to the session team.

Regression test: the PDF handler built Game(...) without team_id, so in
production every PDF import died with
``IntegrityError: games.team_id NOT NULL``. (The pytest suite has a
test-only team backfill, so here the same root cause surfaces as the game
landing on the wrong team instead of raising.)

Why mock parse_game_pdf: driving a real PDF through pdfplumber table
extraction in-test is brittle (requires a pixel-perfect box-score PDF and
couples the test to pdfplumber heuristics). team_id wiring happens
strictly downstream of parsing (parsed dict -> Game(...)), so mocking at
the ``web.routes.main.parse_game_pdf`` seam is the tightest stable seam
that still exercises the full HTTP handler, duplicate check, PlayerStat
fan-out, and session team scoping.
"""
import io
from unittest.mock import patch

from core.models import Game, PlayerStat

PARSED_PDF = {
    "date": "15/03/2025",
    "sort_date": "2025-03-15",
    "opponent": "Lakers",
    "team_score": 95,
    "opponent_score": 88,
    "result": "W",
    "game_type": "Season",
    "players": [
        {
            "name": "John Doe",
            "minutes": "24:30",
            "points": 18,
            "fgm": 7,
            "fga": 14,
            "fg_percent": 50.0,
            "tpm": 2,
            "tpa": 5,
            "tp_percent": 40.0,
            "ftm": 2,
            "fta": 3,
            "ft_percent": 66.7,
            "oreb": 1,
            "dreb": 4,
            "reb": 5,
            "ast": 3,
            "tov": 2,
            "stl": 1,
            "blk": 2,
            "pf": 3,
            "plus_minus": 0,
            "reb_conceded": 0,
        },
        {
            "name": "Jane Smith",
            "minutes": "28:15",
            "points": 22,
            "fgm": 9,
            "fga": 16,
            "fg_percent": 56.2,
            "tpm": 3,
            "tpa": 7,
            "tp_percent": 42.9,
            "ftm": 1,
            "fta": 2,
            "ft_percent": 50.0,
            "oreb": 2,
            "dreb": 5,
            "reb": 7,
            "ast": 4,
            "tov": 3,
            "stl": 1,
            "blk": 0,
            "pf": 2,
            "plus_minus": 0,
            "reb_conceded": 0,
        },
    ],
}

FAKE_PDF_BYTES = b"%PDF-1.4 fake pdf content for upload handler test"


def _legacy_pdf_upload(client, follow_redirects=False):
    with patch("web.routes.main.parse_game_pdf", return_value=dict(PARSED_PDF)):
        return client.post(
            "/upload-game",
            data={
                "import_type": "pdf",
                "pdf_file": (io.BytesIO(FAKE_PDF_BYTES), "game.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=follow_redirects,
        )


def _flashes(client):
    with client.session_transaction() as sess:
        return [(c, m) for c, m in sess.get("_flashes", [])]


def test_legacy_pdf_upload_imports_with_session_team(auth_client, default_team):
    """Imported PDF game must carry team_id from the session."""
    resp = _legacy_pdf_upload(auth_client)
    # Success redirects to the new game detail page
    assert resp.status_code == 302
    assert "/game/" in resp.headers.get("Location", "")

    game = Game.query.filter_by(
        sort_date="2025-03-15",
        opponent="Lakers",
        team_id=default_team.id,
    ).first()
    assert game is not None, (
        f"legacy PDF import did not create a game for team {default_team.id}; "
        f"all games: {[(g.opponent, g.sort_date, g.team_id) for g in Game.query.all()]}"
    )
    assert game.team_score == 95
    assert game.opponent_score == 88
    assert game.result == "W"

    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    assert len(stats) == 2
    assert {s.player_name for s in stats} == {"John Doe", "Jane Smith"}

    flashes = " ".join(m for _, m in _flashes(auth_client))
    assert "Successfully imported game (PDF)" in flashes


def test_legacy_pdf_upload_unauthenticated_redirect(client):
    """Unauthenticated POST/GET to /upload-game must redirect to login."""
    resp = _legacy_pdf_upload(client)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers.get("Location", "")

    get_resp = client.get("/upload-game")
    assert get_resp.status_code == 302
    assert "/auth/login" in get_resp.headers.get("Location", "")
    assert Game.query.count() == 0
