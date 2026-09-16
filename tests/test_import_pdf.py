"""Import-wizard tests: preview-first PDF flow mirroring the CSV wizard.

Covers CSVProcessor.build_preview_pdf (same preview-dict shape as the CSV
``build_preview`` so the wizard UI renders unchanged) plus the
``parse_game_pdf_bytes`` seam in core/parser.py. Backend route wiring
(POST /upload-game/preview-pdf et al.) is a follow-up TODO owned by the
routes agent, so these tests exercise the preview builder directly.
"""
import os

import pytest

from core.csv_processor import CSVProcessor

HEADER = ["Name", "MIN", "PTS", "FGM", "FGA", "FG%", "3PM", "3PA", "3P%",
          "FTM", "FTA", "FT%", "OREB", "DREB", "REB", "AST", "TOV", "STL",
          "BLK", "PF"]
ROW1 = ["John Doe", "24:30", "18", "7", "14", "50.0", "2", "5", "40.0",
        "2", "3", "66.7", "1", "4", "5", "3", "2", "1", "2", "3"]
ROW2 = ["Jane Smith", "28:15", "22", "9", "16", "56.2", "3", "7", "42.9",
        "1", "2", "50.0", "2", "5", "7", "4", "3", "1", "0", "2"]


def _player(name="John Doe", **overrides):
    base = {"name": name, "minutes": "24:30", "points": 18, "fgm": 7,
            "fga": 14, "fg_percent": 50.0, "tpm": 2, "tpa": 5,
            "tp_percent": 40.0, "ftm": 2, "fta": 3, "ft_percent": 66.7,
            "oreb": 1, "dreb": 4, "reb": 5, "ast": 3, "tov": 2, "stl": 1,
            "blk": 2, "pf": 3, "plus_minus": 0}
    base.update(overrides)
    return base


def _descriptor(players, **info):
    base = {"opponent": "Lakers", "date": "15/03/2025",
            "sort_date": "2025-03-15", "team_score": 95,
            "opponent_score": 88, "result": "W", "game_type": "Season",
            "players": players}
    base.update(info)
    return base


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


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


# --- valid PDF -> preview with players ---------------------------------------

def test_valid_pdf_bytes_preview_with_players(tmp_path):
    pdf_path = tmp_path / "game.pdf"
    _make_box_pdf(pdf_path)
    preview = CSVProcessor.build_preview_pdf(
        _read_bytes(pdf_path), filename="game.pdf")
    assert preview["valid"] is True
    assert preview["player_rows"] == 2
    assert preview["columns_missing"] == []
    assert preview["row_errors"] == []
    assert preview["game_info"]["opponent"] == "Lakers"
    assert preview["game_info"]["sort_date"] == "2025-03-15"
    names = {r["Name"] for r in preview["rows"]}
    assert names == {"John Doe", "Jane Smith"}


def test_valid_pdf_path_input(tmp_path):
    pdf_path = tmp_path / "game.pdf"
    _make_box_pdf(pdf_path)
    preview = CSVProcessor.build_preview_pdf(
        str(pdf_path), filename="game.pdf")
    assert preview["valid"] is True
    assert preview["player_rows"] == 2


def test_pdf_preview_matches_csv_preview_shape(tmp_path):
    """Same dict shape as the CSV preview so the wizard UI works unchanged."""
    from core.csv_processor import CSVProcessor as P
    pdf_path = tmp_path / "game.pdf"
    _make_box_pdf(pdf_path)
    pdf_preview = P.build_preview_pdf(
        _read_bytes(pdf_path), filename="game.pdf")
    csv_text = "\n".join([",".join(HEADER), ",".join(ROW1),
                          ",".join(ROW2)]) + "\n"
    csv_preview = P.build_preview(
        csv_text, "Lakers_95-88_15-03-2025_S.csv")
    assert csv_preview["valid"] is True
    assert set(pdf_preview.keys()) == set(csv_preview.keys())
    for key in ("filename", "game_info", "columns_found", "columns_missing",
                "row_errors", "rows", "total_rows", "player_rows", "valid"):
        assert key in pdf_preview


def test_parse_bytes_seam_reuses_parser(tmp_path):
    from core.parser import parse_game_pdf, parse_game_pdf_bytes
    pdf_path = tmp_path / "game.pdf"
    _make_box_pdf(pdf_path)
    raw = _read_bytes(pdf_path)
    via_bytes = parse_game_pdf_bytes(raw)
    via_path = parse_game_pdf(str(pdf_path))
    assert via_bytes["players"] == via_path["players"]
    assert via_bytes["opponent"] == via_path["opponent"] == "Lakers"


# --- malformed PDF -> clean error preview (never raises) ---------------------

@pytest.mark.parametrize("bad", [
    b"",
    b"   ",
    b"%PDF-1.4 garbage \x00\x01 not a pdf",
    b"\xff\xd8\xff\xe0 fake image bytes",
])
def test_malformed_pdf_clean_error_preview(bad):
    preview = CSVProcessor.build_preview_pdf(bad, filename="broken.pdf")
    assert preview["valid"] is False
    assert preview.get("fatal")


def test_unsupported_and_missing_inputs_never_raise():
    for bad in (None, "", 12345, {"no": "players"}, {"players": []}):
        preview = CSVProcessor.build_preview_pdf(bad, filename="x.pdf")
        assert preview["valid"] is False
        assert preview.get("fatal")


def test_missing_pdf_path_clean_error(tmp_path):
    preview = CSVProcessor.build_preview_pdf(
        str(tmp_path / "does-not-exist.pdf"))
    assert preview["valid"] is False
    assert preview.get("fatal")


# --- missing columns flagged --------------------------------------------------

def test_missing_columns_flagged():
    player = _player()
    del player["ast"]
    preview = CSVProcessor.build_preview_pdf(_descriptor([player]))
    assert preview["valid"] is False
    assert "AST" in preview["columns_missing"]
    assert preview["game_info"]["opponent"] == "Lakers"


# --- mapping fix recovers (shared mapped_frame path) --------------------------

def test_column_map_fix_recovers():
    player = _player()
    player["Punti"] = player.pop("points")  # alternate header, PTS missing
    desc = _descriptor([player])
    first = CSVProcessor.build_preview_pdf(desc)
    assert first["valid"] is False
    assert "PTS" in first["columns_missing"]

    fixed = CSVProcessor.build_preview_pdf(
        desc, column_mapping={"Punti": "PTS"})
    assert fixed["columns_missing"] == []
    assert fixed["valid"] is True
    assert fixed["rows"][0]["PTS"] == 18


def test_conflicting_column_mapping_rejected_cleanly():
    # PTS already present: mapping another header onto it must be a fatal
    # preview (same ValueError path as mapped_frame), not a raise.
    desc = _descriptor([_player()])
    preview = CSVProcessor.build_preview_pdf(
        desc, column_mapping={"MIN": "PTS"})
    assert preview["valid"] is False
    assert "already present" in (preview.get("fatal") or "")


def test_mapped_frame_path_shared():
    """The PDF frame round-trips through mapped_frame (conflict parity)."""
    with pytest.raises(ValueError, match="already present"):
        CSVProcessor.mapped_frame("MIN,PTS\n24:30,18\n", {"MIN": "PTS"})


# --- row-level validation parity with the CSV wizard --------------------------

def test_bad_row_values_flagged():
    player = _player(points="abc", minutes="notatime")
    preview = CSVProcessor.build_preview_pdf(_descriptor([player]))
    assert preview["valid"] is False
    cols = {(e["row"], e["column"]) for e in preview["row_errors"]}
    assert (0, "PTS") in cols
    assert (0, "MIN") in cols


def test_blank_name_row_flagged():
    preview = CSVProcessor.build_preview_pdf(
        _descriptor([_player(name="")]))
    assert preview["valid"] is False
    assert any(e["column"] == "Name" for e in preview["row_errors"])


def test_date_override_fixes_undetected_header_date():
    desc = _descriptor([_player()], date="", sort_date="")
    first = CSVProcessor.build_preview_pdf(desc)
    assert first["valid"] is False
    assert any(e["column"] == "date" for e in first["row_errors"])

    fixed = CSVProcessor.build_preview_pdf(desc, date_override="15-03-2025")
    assert fixed["valid"] is True
    assert fixed["game_info"]["sort_date"] == "2025-03-15"


def test_bad_date_override_flagged():
    desc = _descriptor([_player()])
    preview = CSVProcessor.build_preview_pdf(desc, date_override="not-a-date")
    assert preview["valid"] is False
    assert any(e["column"] == "date_override"
               for e in preview["row_errors"])


def test_commit_path_frame_reuse():
    """frame_to_players over the PDF frame yields import-ready payloads."""
    desc = _descriptor([_player(), _player(name="Jane Smith")])
    df = CSVProcessor._pdf_players_frame(desc, None)
    players = CSVProcessor.frame_to_players(df)
    assert {p["name"] for p in players} == {"John Doe", "Jane Smith"}
    assert players[0]["points"] == 18


def test_never_raises_on_garbage_descriptor():
    preview = CSVProcessor.build_preview_pdf(
        {"players": [{"Name": object(), "MIN": object()}]})
    assert preview["valid"] is False  # fatal or row errors, but no raise
