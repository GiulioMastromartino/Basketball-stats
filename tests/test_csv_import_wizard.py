"""Import-wizard tests: preview-first CSV flow with inline fix + commit."""
import json

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


def _preview(client, content, filename=FILENAME, mapping=None, date=""):
    return client.post("/upload-game/preview", json={
        "content": content,
        "filename": filename,
        "column_mapping": mapping or {},
        "date_override": date,
    })


def test_preview_flags_missing_column(auth_client):
    header = HEADER.replace(",AST", "")
    rows = [r for r in (ROW1, ROW2, TOTAL)]
    # Drop the AST value (index 15) from each row to stay aligned.
    body = "\n".join(
        [header] + [",".join(r.split(",")[:15] + r.split(",")[16:])
                    for r in rows]) + "\n"
    resp = _preview(auth_client, body)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is False
    assert "AST" in data["columns_missing"]
    assert data["game_info"]["opponent"] == "Lakers"


def test_preview_flags_bad_row_values(auth_client):
    bad_row = ROW1.replace(",18,", ",abc,", 1).replace("24:30", "notatime")
    body = "\n".join([HEADER, bad_row, ROW2, TOTAL]) + "\n"
    resp = _preview(auth_client, body)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is False
    assert data["row_errors"], "expected per-row errors"
    cols = {(e["row"], e["column"]) for e in data["row_errors"]}
    assert (0, "PTS") in cols
    assert (0, "MIN") in cols


def test_column_map_fix_recovers(auth_client):
    header = HEADER.replace("PTS", "Punti")
    body = "\n".join([header, ROW1, ROW2, TOTAL]) + "\n"
    first = _preview(auth_client, body)
    assert first.status_code == 200
    assert "PTS" in json.loads(first.data)["columns_missing"]

    fixed = auth_client.post("/upload-game/revalidate", json={
        "content": body,
        "filename": FILENAME,
        "column_mapping": {"Punti": "PTS"},
        "date_override": "",
    })
    assert fixed.status_code == 200
    data = json.loads(fixed.data)
    assert data["columns_missing"] == []
    assert data["valid"] is True


def test_successful_commit_creates_game(auth_client, db_session):
    resp = auth_client.post("/upload-game/commit", json={
        "content": VALID_CSV,
        "filename": FILENAME,
        "column_mapping": {},
        "date_override": "",
    })
    assert resp.status_code == 201
    data = json.loads(resp.data)
    game = Game.query.get(data["game_id"])
    assert game is not None
    assert game.opponent == "Lakers"
    assert game.sort_date == "2025-03-15"
    stats = PlayerStat.query.filter_by(game_id=game.id).all()
    assert len(stats) == 2  # Total row skipped
    assert {s.player_name for s in stats} == {"John Doe", "Jane Smith"}


def test_malformed_file_rejected_cleanly(auth_client):
    for bad in ["", "   \n  ", '"""unbalanced quotes,,,\nfoo,"bar\n' * 5]:
        resp = auth_client.post("/upload-game/commit", json={
            "content": bad,
            "filename": FILENAME,
            "column_mapping": {},
            "date_override": "",
        })
        assert resp.status_code in (200, 400, 409), resp.status_code
        assert resp.status_code != 500
        data = json.loads(resp.data)
        assert data.get("valid") is False

    # Preview endpoint likewise never 500s.
    resp = _preview(auth_client, "")
    assert resp.status_code == 400
    assert json.loads(resp.data)["valid"] is False


def test_blank_name_row_flagged_not_silently_skipped(auth_client):
    bad_row = "," + ROW1.split(",", 1)[1]  # empty Name
    body = "\n".join([HEADER, bad_row, ROW2, TOTAL]) + "\n"
    resp = _preview(auth_client, body)
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["valid"] is False
    assert any(e["column"] == "Name" for e in data["row_errors"])


def test_conflicting_column_mapping_rejected_cleanly(auth_client):
    # PTS already exists: mapping another header onto it must 400, not 500.
    resp = _preview(auth_client, VALID_CSV, mapping={"MIN": "PTS"})
    assert resp.status_code == 400
    assert json.loads(resp.data)["valid"] is False


def test_duplicate_commit_reports_conflict(auth_client):
    first = auth_client.post("/upload-game/commit", json={
        "content": VALID_CSV, "filename": FILENAME,
        "column_mapping": {}, "date_override": "",
    })
    assert first.status_code == 201
    second = auth_client.post("/upload-game/commit", json={
        "content": VALID_CSV, "filename": FILENAME,
        "column_mapping": {}, "date_override": "",
    })
    assert second.status_code == 409
    assert "already exists" in json.loads(second.data)["error"]
