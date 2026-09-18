"""Slice N3 — social PNG cards, comms templates, video export."""

import io
import json

from PIL import Image

from core.comms_templates import TEMPLATES, postgame_context, render
from core.social_cards import render_player_card, render_score_card
from core.models import Player, db


def _assert_png(raw: bytes):
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(raw))
    assert img.size == (1080, 1080)


class TestRenderers:
    def test_score_card(self):
        _assert_png(render_score_card("Sharks", "Rivals", 78, 74,
                                      date="18-09-2026", result="W"))

    def test_player_card(self):
        _assert_png(render_player_card(
            "Anna", "Sharks",
            {"points": 24, "reb": 8, "ast": 5, "stl": 2, "blk": 1},
            date="18-09-2026"))

    def test_empty_inputs_dont_crash(self):
        _assert_png(render_score_card("", "", 0, 0))
        _assert_png(render_player_card(""))


class TestTemplates:
    def test_render_all_tags(self):
        ctx = {"team": "Sharks", "opponent": "Rivals", "score": "78 - 74",
               "result": "W", "date": "18-09-2026",
               "top_scorer": "Anna", "top_points": 24,
               "games_played": 6, "wins": 5, "losses": 1}
        for name in TEMPLATES:
            text = render(name, ctx)
            assert "{{" not in text
            assert "Sharks" in text

    def test_unknown_tags_left_visible(self):
        assert render("postgame_whatsapp", {}) .count("{{") >= 1

    def test_unknown_template_raises(self):
        try:
            render("nope", {})
        except KeyError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected KeyError")

    def test_postgame_context_picks_top_scorer(self, sample_game,
                                               sample_player_stats):
        ctx = postgame_context("Sharks", sample_game, sample_player_stats)
        assert ctx["top_scorer"] == "Jane Smith"
        assert ctx["top_points"] == 22


class TestCardRoutes:
    def test_game_card_png(self, admin_client, sample_game):
        resp = admin_client.get(f"/share/cards/game/{sample_game.id}")
        assert resp.status_code == 200
        assert resp.content_type == "image/png"
        _assert_png(resp.data)

    def test_game_card_404(self, admin_client):
        assert admin_client.get("/share/cards/game/99999").status_code == 404

    def test_player_card_png(self, admin_client, db_session, default_team,
                             sample_game, sample_player_stats):
        player = Player(team_id=default_team.id, name="Jane Smith")
        db_session.add(player)
        db_session.commit()
        resp = admin_client.get(f"/share/cards/player/{player.id}")
        assert resp.status_code == 200
        _assert_png(resp.data)

    def test_comms_preview(self, admin_client, sample_game, sample_player_stats):
        resp = admin_client.post(
            "/share/comms-preview",
            data=json.dumps({"template": "postgame_whatsapp",
                             "game_id": sample_game.id}),
            content_type="application/json")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "Jane Smith" in data["text"]
        assert "{{" not in data["text"]

    def test_comms_preview_unknown_template(self, admin_client, sample_game):
        resp = admin_client.post(
            "/share/comms-preview",
            data=json.dumps({"template": "nope", "game_id": sample_game.id}),
            content_type="application/json")
        assert resp.status_code == 400


class TestVideoExport:
    def test_json(self, admin_client, sample_game, sample_game_events,
                  sample_shot_event):
        resp = admin_client.get(f"/api/v1/games/{sample_game.id}/video-export")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["game_id"] == sample_game.id
        assert data["count"] >= 8  # 7 events + 1 shot
        assert data["events"][0]["quarter"] == 1

    def test_csv(self, admin_client, sample_game, sample_game_events):
        resp = admin_client.get(
            f"/api/v1/games/{sample_game.id}/video-export?format=csv")
        assert resp.status_code == 200
        assert "quarter" in resp.data.decode("utf-8").splitlines()[0]

    def test_bad_format(self, admin_client, sample_game):
        resp = admin_client.get(
            f"/api/v1/games/{sample_game.id}/video-export?format=xml")
        assert resp.status_code == 400

    def test_404(self, admin_client):
        assert admin_client.get(
            "/api/v1/games/99999/video-export").status_code == 404
