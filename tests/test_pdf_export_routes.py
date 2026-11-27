"""Regression tests for the PDF export blueprint URL prefix (audit bug 5).

``pdf_export_bp`` is mounted with ``url_prefix="/api/pdf"`` (see
``register_blueprints`` in ``web/__init__.py``).  The rules inside the
blueprint used to spell that prefix out a second time, and Flask
concatenates the two, so the public URLs became::

    /api/pdf/api/pdf/game/<game_id>
    /api/pdf/api/pdf/player/<player_id>
    /api/pdf/api/pdf/team

The canonical URLs (``/api/pdf/game/<game_id>`` and friends) returned 404
and, because the templates build the links with
``url_for('pdf_export.export_game_pdf')`` / ``url_for('pdf_export.export_team_pdf')``,
the rendered HTML of /players and /game/<id> linked to the doubled path.

These tests pin the single-prefix URLs down.
"""

from flask import url_for

from core.models import Player


def _rule_strings(app):
    """All URL rule paths known to the application."""
    return {str(rule) for rule in app.url_map.iter_rules()}


# --- URL map -----------------------------------------------------------------


def test_pdf_export_rules_use_a_single_api_pdf_prefix(app):
    rules = _rule_strings(app)

    assert "/api/pdf/game/<int:game_id>" in rules
    assert "/api/pdf/player/<int:player_id>" in rules
    assert "/api/pdf/team" in rules


def test_pdf_export_rules_are_not_double_prefixed(app):
    doubled = sorted(r for r in _rule_strings(app) if "/api/pdf/api/pdf" in r)
    assert doubled == [], f"doubled PDF export rules still registered: {doubled}"


def test_url_for_builds_the_canonical_pdf_urls(app):
    with app.test_request_context():
        assert url_for("pdf_export.export_game_pdf", game_id=7) == "/api/pdf/game/7"
        assert url_for("pdf_export.export_player_pdf", player_id=3) == "/api/pdf/player/3"
        assert url_for("pdf_export.export_team_pdf") == "/api/pdf/team"


# --- HTTP --------------------------------------------------------------------


def test_game_pdf_is_served_from_the_canonical_url(
    auth_client, sample_game, sample_player_stats
):
    response = auth_client.get(f"/api/pdf/game/{sample_game.id}")

    assert response.status_code == 200, response.status_code
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 1000


def test_team_pdf_is_served_from_the_canonical_url(auth_client, sample_game):
    response = auth_client.get("/api/pdf/team")

    assert response.status_code == 200, response.status_code
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 1000


def test_player_pdf_is_served_from_the_canonical_url(
    auth_client, db_session, default_team, sample_game, sample_player_stats
):
    player = Player(team_id=default_team.id, name="John Doe")
    db_session.add(player)
    db_session.commit()

    response = auth_client.get(f"/api/pdf/player/{player.id}")

    assert response.status_code == 200, response.status_code
    assert response.content_type == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) > 1000


def test_doubled_pdf_url_is_not_served(auth_client, sample_game):
    """The accidental doubled path must not linger in the URL map."""
    response = auth_client.get(f"/api/pdf/api/pdf/game/{sample_game.id}")

    assert response.status_code == 404
