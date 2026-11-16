"""Halftime PDF payload parsing (legacy tracker + v2/canonical events)."""

import json

from core.halftime_summary import build_halftime_summary


def _legacy_payload(**overrides):
    payload = {
        "opponent": "Rivals",
        "date": "2026-09-18",
        "team_score": 30,
        "opp_score": 24,
        "player_stats": {
            "Anna": {
                "points": 20, "fgm": 8, "fga": 14, "tpm": 2, "tpa": 5,
                "ftm": 2, "fta": 2, "oreb": 1, "dreb": 3, "ast": 3,
                "stl": 0, "blk": 0, "tov": 1, "pf": 1,
                "minutes_seconds": 960,
                "quarter_minutes": {"1": 480, "2": 480},
                "plus_minus": 6,
            },
            "Bea": {
                "points": 10, "fgm": 4, "fga": 9, "tpm": 0, "tpa": 2,
                "ftm": 2, "fta": 4, "oreb": 2, "dreb": 1, "ast": 1,
                "stl": 1, "blk": 0, "tov": 0, "pf": 2,
                "minutes_seconds": 720,
                "quarter_minutes": {"1": 360, "2": 360},
                "plus_minus": -2,
            },
        },
        # The legacy tracker never emits SHOT_2PT/SHOT_3PT events.
        "game_events": [
            {"type": "FT", "player": "Anna", "quarter": 1,
             "detail": {"ftm": 2, "fta": 2}},
            {"type": "FT", "player": "Bea", "quarter": 2,
             "detail": {"ftm": 2, "fta": 4}},
            {"type": "REBOUND_DEFENSIVE", "player": "Bea", "quarter": 1},
            {"type": "STEAL", "player": "Bea", "quarter": 2},
            {"type": "FOUL_PERSONAL", "player": "Anna", "quarter": 1},
        ],
        "shot_locations": [
            *[{"shooter": "Anna", "type": "2pt", "points": 2,
               "result": "made", "quarter": 1, "assister": "Bea"}] * 5,
            {"shooter": "Anna", "type": "3pt", "points": 3,
             "result": "made", "quarter": 1, "assister": None},
            *[{"shooter": "Bea", "type": "2pt", "points": 2,
               "result": "made", "quarter": 2, "assister": "Anna"}] * 2,
            {"shooter": "Anna", "type": "3pt", "points": 0,
             "result": "missed", "quarter": 2, "assister": None},
            # Q3 shots are outside the halftime window.
            {"shooter": "Anna", "type": "3pt", "points": 3,
             "result": "made", "quarter": 3},
        ],
    }
    payload.update(overrides)
    return payload


class TestLegacyPayload:
    def test_quarter_breakdown_uses_shot_locations(self):
        summary = build_halftime_summary(_legacy_payload())
        q1 = summary["quarterly_stats"]["1"]
        q2 = summary["quarterly_stats"]["2"]

        assert q1["pts"] == 15  # 5x2 + 1x3 + 2 FT
        assert q1["fgm"] == 6
        assert q1["fga"] == 6
        assert q1["tpm"] == 1
        assert q1["tpa"] == 1
        assert q1["ftm"] == 2
        assert q1["fta"] == 2
        assert q1["reb"] == 1
        assert q1["ast"] == 5
        assert q1["pf"] == 1

        assert q2["pts"] == 6  # 2x2 + 2 FT
        assert q2["fgm"] == 2
        assert q2["fga"] == 3
        assert q2["tpm"] == 0
        assert q2["tpa"] == 1
        assert q2["ftm"] == 2
        assert q2["fta"] == 4
        assert q2["stl"] == 1
        assert q2["ast"] == 2

    def test_scoring_average_and_leaders(self):
        summary = build_halftime_summary(_legacy_payload())
        assert summary["stats"][0]["player_name"] == "Anna"
        assert summary["stats"][0]["minutes"] == "16:00"
        assert summary["stats"][0]["q1_minutes"] == "8:00"
        assert summary["stats"][0]["reb"] == 4
        assert summary["top_performers"]["points"]["player_name"] == "Anna"
        assert summary["team_aggregates"]["fg_pct"] == 12 / 23 * 100


def _canonical_payload():
    return {
        "opponent": "Rivals",
        "date": "2026-09-18",
        "team_score": 14,
        "opp_score": 9,
        "player_stats": {"Anna": {"points": 8}, "Bea": {"points": 6}},
        "game_events": [
            {"event_type": "SHOT_2PT", "player_name": "Anna",
             "shot_attempt": "made", "quarter": 1, "team": "HOME"},
            {"event_type": "SHOT_3PT", "player_name": "Anna",
             "shot_attempt": "made", "quarter": 1, "team": "HOME"},
            {"event_type": "SHOT_2PT", "player_name": "Bea",
             "shot_attempt": "missed", "quarter": 2, "team": "HOME"},
            {"event_type": "SHOT_2PT", "player_name": "Bea",
             "shot_attempt": "made", "quarter": 2, "team": "HOME"},
            {"event_type": "SHOT_2PT", "player_name": "Bea",
             "shot_attempt": "made", "quarter": 2, "team": "HOME"},
            {"event_type": "FT_MADE", "player_name": "Bea", "quarter": 2,
             "team": "HOME"},
            {"event_type": "FT_MISS", "player_name": "Anna", "quarter": 2,
             "team": "HOME"},
            {"event_type": "ASSIST", "player_name": "Bea", "quarter": 1,
             "team": "HOME"},
            {"event_type": "REBOUND", "player_name": "Bea", "quarter": 1,
             "team": "HOME"},
            {"event_type": "STEAL", "player_name": "Anna", "quarter": 2,
             "team": "HOME"},
            {"event_type": "BLOCK", "player_name": "Bea", "quarter": 2,
             "team": "HOME"},
            {"event_type": "TURNOVER", "player_name": "Anna", "quarter": 1,
             "team": "HOME"},
            {"event_type": "TECH_FOUL", "player_name": "Anna", "quarter": 2,
             "team": "HOME",
             "detail": json.dumps({"play_id": None, "pf": 1})},
            {"event_type": "FOUL", "player_name": "Bea", "quarter": 1,
             "team": "HOME"},
            # Opponent shot: must not leak into the team summary.
            {"event_type": "SHOT_3PT", "player_name": "Opp",
             "shot_attempt": "made", "quarter": 1, "team": "AWAY"},
        ],
        # Duplicate locations must be ignored when shot events exist.
        "shot_locations": [
            {"shooter": "Anna", "type": "3pt", "result": "made",
             "points": 3, "quarter": 1},
            {"shooter": "Bea", "type": "2pt", "result": "made",
             "points": 2, "quarter": 2},
        ],
    }


class TestCanonicalPayload:
    def test_event_types_fill_quarter_breakdown(self):
        summary = build_halftime_summary(_canonical_payload())
        q1 = summary["quarterly_stats"]["1"]
        q2 = summary["quarterly_stats"]["2"]

        assert q1 == {
            "pts": 5, "fgm": 2, "fga": 2, "tpm": 1, "tpa": 1,
            "ftm": 0, "fta": 0, "tov": 1, "pf": 1, "reb": 1,
            "ast": 1, "stl": 0, "blk": 0,
        }
        assert q2 == {
            "pts": 5, "fgm": 2, "fga": 3, "tpm": 0, "tpa": 0,
            "ftm": 1, "fta": 2, "tov": 0, "pf": 1, "reb": 0,
            "ast": 0, "stl": 1, "blk": 1,
        }

    def test_shot_locations_do_not_double_count_events(self):
        summary = build_halftime_summary(_canonical_payload())
        assert summary["quarterly_stats"]["1"]["fga"] == 2
        assert summary["quarterly_stats"]["2"]["fga"] == 3


class TestMalformedPayload:
    def test_bad_rows_and_types_do_not_raise(self):
        summary = build_halftime_summary(
            {
                "team_score": "many",
                "opp_score": None,
                "player_stats": {
                    "Anna": None,
                    "Bea": {
                        "points": None, "fgm": "8", "fga": "10",
                        "ftm": "2", "fta": 2, "minutes": "12:30",
                    },
                    "Cee": "junk",
                },
                "game_events": {"bad": "shape"},
                "shot_locations": "nope",
            }
        )
        assert summary["team_score"] == 0
        assert summary["opp_score"] == 0
        bea = next(row for row in summary["stats"] if row["player_name"] == "Bea")
        assert bea["minutes"] == "12:30"
        assert bea["points"] == 18  # derived from fgm/tpm/ftm
        assert bea["fg_percent"] == 80.0

    def test_json_detail_with_null_is_parsed(self):
        summary = build_halftime_summary(
            {
                "player_stats": {"Anna": {}},
                "game_events": [
                    {"event_type": "FT", "quarter": 1,
                     "detail": json.dumps({"ftm": 2, "fta": 3,
                                           "play_id": None})},
                ],
            }
        )
        assert summary["quarterly_stats"]["1"]["ftm"] == 2
        assert summary["quarterly_stats"]["1"]["fta"] == 3
        assert summary["quarterly_stats"]["1"]["pts"] == 2

    def test_empty_payload_returns_zeroed_context(self):
        summary = build_halftime_summary({})
        assert summary["stats"] == []
        assert summary["top_performers"] == {}
        assert summary["quarterly_stats"]["1"]["pts"] == 0
        assert summary["team_aggregates"]["fg_pct"] == 0


class TestRoute:
    def test_pdf_route_uses_normalized_summary(self, auth_client, monkeypatch):
        import weasyprint

        captured = {}

        def fake_render(template, **kwargs):
            captured.update(kwargs)
            return "<html></html>"

        class FakeHTML:
            def __init__(self, *args, **kwargs):
                pass

            def write_pdf(self):
                return b"%PDF-1.4"

        monkeypatch.setattr("web.routes.reports.render_template", fake_render)
        monkeypatch.setattr(weasyprint, "HTML", FakeHTML)

        resp = auth_client.post(
            "/reports/live/halftime-pdf", json=_legacy_payload()
        )

        assert resp.status_code == 200
        assert captured["team_score"] == 30
        assert captured["opp_score"] == 24
        assert captured["quarterly_stats"]["1"]["pts"] == 15
        assert captured["stats"][0]["player_name"] == "Anna"

    def test_pdf_route_rejects_non_object_payload(self, auth_client):
        resp = auth_client.post("/reports/live/halftime-pdf", json=["nope"])
        assert resp.status_code == 400

