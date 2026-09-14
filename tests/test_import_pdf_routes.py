"""PDF wizard route wiring: preview/revalidate/commit JSON endpoints."""
import base64
import io
import json
from unittest.mock import patch

from core.models import Game, PlayerStat

HEADER = ["Name", "MIN", "PTS", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%",
          "FTM", "FTA", "FT%", "OREB", "DREB", "REB", "AST", "TOV", "STL",
          "BLK", "PF"]
ROW1 = ["John Doe", "24:30", "18", "7", "14", "50.0", "2", "5", "40.0",
        "2", "3", "66.7", "1", "4", "5", "3", "2", "1", "2", "3"]
ROW2 = ["Jane Smith", "28:15", "22", "9", "16", "56.2", "3", "7", "42.9",
        "1", "2", "50.0", "2", "5", "7", "4", "3", "1", "0", "2"]


def _make_box_pdf(path, opponent="Lakers", date="15/03", year="2025",
                   score="win [95 - 88]", rows=(ROW1, ROW2)):
    """Generate a real box-score PDF (reportlab table + header text)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    table = Table([HEADER] + [list(r) for r in rows], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    doc.build([
        Paragraph(f"{date} - {opponent}", styles["Normal"]),
        Paragraph(score, styles["Normal"]),
        Paragraph(year, styles["Normal"]),
        Spacer(1, 12),
        table,
    ])


def _pdf_b64(tmp_path):
    pdf_path = tmp_path / "game.pdf"
    _make_box_pdf(pdf_path)
    with open(pdf_path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _preview_payload(b64, mapping=None, date="", filename="game.pdf"):
    return {
        "filename": filename,
        "pdf_base64": b64,
        "column_mapping": mapping or {},
        "date_override": date,
    }


def test_preview_pdf_valid_returns_preview_json(auth_client, tmp_path):
    b64 = _pdf_b64(tmp_path)
    resp = auth_client.post("/upload-game/preview-pdf",
                            json=_preview_payload(b64))
    assert resp.status_code == 200, resp.data[:500]
    data = json.loads(resp.data)
    assert data["valid"] is True
    assert data["player_rows"] == 2
    assert data["columns_missing"] == []
    assert data["game_info"]["opponent"] == "Lakers"
    assert data["game_info"]["sort_date"] == "2025-03-15"
    names = {r["Name"] for r in data["rows"]}
    assert names == {"John Doe", "Jane Smith"}


def test_preview_pdf_multipart_file(auth_client, tmp_path):
    pdf_path = tmp_path / "game.pdf"
    _make_box_pdf(pdf_path)
    with open(pdf_path, "rb") as fh:
        raw = fh.read()
    resp = auth_client.post(
        "/upload-game/preview-pdf",
        data={"pdf_file": (io.BytesIO(raw), "game.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert json.loads(resp.data)["valid"] is True


def test_preview_pdf_malformed_never_500(auth_client):
    bad_bodies = [
        {"filename": "x.pdf", "pdf_base64": "", "column_mapping": {},
         "date_override": ""},
        {"filename": "broken.pdf", "pdf_base64":
         base64.b64encode(b"%PDF-1.4 garbage not a pdf").decode(),
         "column_mapping": {}, "date_override": ""},
        {"filename": "broken.pdf", "pdf_base64": "!!!not-base64!!!",
         "column_mapping": {}, "date_override": ""},
        {"filename": "broken.pdf", "column_mapping": {},
         "date_override": ""},
    ]
    for body in bad_bodies:
        resp = auth_client.post("/upload-game/preview-pdf", json=body)
        assert resp.status_code == 400, body
        assert resp.status_code != 500
        assert json.loads(resp.data).get("valid") is False


def test_revalidate_mapping_fix_recovers(auth_client):
    """Alternate header via mocked parse -> mapping fix recovers."""
    from core.csv_processor import CSVProcessor

    def _player(name="John Doe", **overrides):
        base = {"name": name, "minutes": "24:30", "points": 18, "fgm": 7,
                "fga": 14, "fg_percent": 50.0, "tpm": 2, "tpa": 5,
                "tp_percent": 40.0, "ftm": 2, "fta": 3, "ft_percent": 66.7,
                "oreb": 1, "dreb": 4, "reb": 5, "ast": 3, "tov": 2, "stl": 1,
                "blk": 2, "pf": 3, "plus_minus": 0}
        base.update(overrides)
        return base

    player = _player()
    player["Punti"] = player.pop("points")
    descriptor = {"opponent": "Lakers", "date": "15/03/2025",
                  "sort_date": "2025-03-15", "team_score": 95,
                  "opponent_score": 88, "result": "W",
                  "game_type": "Season", "players": [player]}
    fake_b64 = base64.b64encode(b"%PDF-1.4 fake").decode()
    with patch("core.parser.parse_game_pdf_bytes",
               return_value=descriptor):
        first = auth_client.post("/upload-game/revalidate-pdf", json={
            "filename": "game.pdf", "pdf_base64": fake_b64,
            "column_mapping": {}, "date_override": "",
        })
        assert first.status_code == 200
        assert "PTS" in json.loads(first.data)["columns_missing"]

        fixed = auth_client.post("/upload-game/revalidate-pdf", json={
            "filename": "game.pdf", "pdf_base64": fake_b64,
            "column_mapping": {"Punti": "PTS"}, "date_override": "",
        })
        assert fixed.status_code == 200
        data = json.loads(fixed.data)
        assert data["columns_missing"] == []
        assert data["valid"] is True
        # Sanity: same path the unit tests cover directly.
        assert CSVProcessor.build_preview_pdf(
            descriptor, column_mapping={"Punti": "PTS"})["valid"] is True


def test_commit_creates_game_with_session_team(auth_client, default_team,
                                               tmp_path):
    b64 = _pdf_b64(tmp_path)
    resp = auth_client.post("/upload-game/commit-pdf",
                            json=_preview_payload(b64))
    assert resp.status_code == 201, resp.data[:500]
    data = json.loads(resp.data)
    game = Game.query.get(data["game_id"])
    assert game is not None
    assert game.opponent == "Lakers"
    assert game.sort_date == "2025-03-15"
    assert game.team_id == default_team.id
    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    assert len(stats) == 2
    assert {s.player_name for s in stats} == {"John Doe", "Jane Smith"}


def test_commit_invalid_blocked_400(auth_client):
    resp = auth_client.post("/upload-game/commit-pdf", json={
        "filename": "broken.pdf",
        "pdf_base64": base64.b64encode(b"not a pdf at all").decode(),
        "column_mapping": {}, "date_override": "",
    })
    assert resp.status_code == 400
    assert json.loads(resp.data).get("valid") is False
    assert Game.query.count() == 0


def test_commit_duplicate_409(auth_client, tmp_path):
    b64 = _pdf_b64(tmp_path)
    first = auth_client.post("/upload-game/commit-pdf",
                             json=_preview_payload(b64))
    assert first.status_code == 201
    second = auth_client.post("/upload-game/commit-pdf",
                              json=_preview_payload(b64))
    assert second.status_code == 409
    assert "already exists" in json.loads(second.data)["error"]


def test_pdf_wizard_unauthenticated_redirect(client, tmp_path):
    b64 = _pdf_b64(tmp_path)
    for url in ("/upload-game/preview-pdf", "/upload-game/revalidate-pdf",
                "/upload-game/commit-pdf"):
        resp = client.post(url, json=_preview_payload(b64))
        assert resp.status_code == 302, url
        assert "/auth/login" in resp.headers.get("Location", "")
    assert Game.query.count() == 0
