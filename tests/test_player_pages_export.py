"""Regression tests for the player pages / player PDF export fixes (A1-A4).

Covers:
- A1: the player detail page never depends on Chart.js / window.load /
  requestAnimationFrame to become visible (courtside tablets lose the CDN).
- A2: the player header exposes exactly one export action.
- A3: every player-PDF URL funnels through the single reports generator.
- A4: /players/pages.zip skips players without stats instead of 500ing.
"""

import io
import zipfile

from core.models import (
    Game,
    Organization,
    OrganizationMembership,
    Player,
    PlayerStat,
    Team,
    TeamAssignment,
    User,
    db,
)
from flask import url_for
from web import create_app


def _setup():
    app = create_app("testing")
    client = app.test_client()
    ctx = app.app_context()
    ctx.push()
    db.create_all()

    org = Organization(name="Player Pages Org", slug="player-pages-org")
    db.session.add(org)
    db.session.flush()
    team = Team(name="Player Pages Team", organization_id=org.id,
                slug="player-pages-team")
    db.session.add(team)
    db.session.flush()

    user = User(username="player_pages_user", email="pp@t.com",
                organization_id=org.id)
    user.set_password("pw123456")
    db.session.add(user)
    db.session.flush()
    db.session.add(OrganizationMembership(user_id=user.id,
                                          organization_id=org.id,
                                          is_gm=False))
    db.session.add(TeamAssignment(user_id=user.id, team_id=team.id,
                                  is_coach=True))

    game = Game(date="17-02-2024", opponent="PagesOpp", team_score=80,
                opponent_score=70, result="W", game_type="Season",
                sort_date="2024-02-17", source="MANUAL", team_id=team.id)
    db.session.add(game)
    db.session.commit()
    db.session.add(PlayerStat(game_id=game.id, player_name="PagesPlayer",
                              points=20, reb=5, ast=4, minutes="25:00"))
    db.session.commit()
    player = Player(team_id=team.id, name="PagesPlayer")
    db.session.add(player)
    db.session.commit()
    return app, client, ctx, user, team, player


def _teardown(ctx):
    db.session.remove()
    db.drop_all()
    ctx.pop()


def _login(client, user, team):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["current_team_id"] = team.id
        sess["current_team_name"] = team.name


def _pdf_text(pdf_bytes):
    """Extract the text of a PDF so layouts can be compared byte-safely."""
    from pdfminer.high_level import extract_text

    return extract_text(io.BytesIO(pdf_bytes))


# --- A1 ----------------------------------------------------------------------


def test_player_page_does_not_depend_on_cdn_or_load_event():
    app, client, ctx, user, team, player = _setup()
    try:
        _login(client, user, team)
        response = client.get("/player/PagesPlayer")
        assert response.status_code == 200, response.status_code
        html = response.data.decode()

        # Content is painted, never hidden behind the overlay.
        assert 'id="playerPage" class="container-fluid"' in html
        assert '<div id="playerPage" class="container-fluid page-hidden">' not in html

        # Charts degrade to an inline note instead of hiding the page.
        assert 'data-chart-fallback' in html
        assert 'Charts unavailable' in html

        # The CDN script can never block first paint, and the reveal no
        # longer waits for window.load / rAF / Chart.js.
        assert 'cdn.jsdelivr.net/npm/chart.js" defer' in html
        assert 'requestAnimationFrame(' not in html
        assert 'DOMContentLoaded' in html
        assert 'revealPlayerPage();' in html
    finally:
        _teardown(ctx)


# --- A2 ----------------------------------------------------------------------


def test_player_header_has_a_single_export_action():
    app, client, ctx, user, team, player = _setup()
    try:
        _login(client, user, team)
        html = client.get("/player/PagesPlayer").data.decode()

        export_links = [line for line in html.splitlines()
                        if "report.pdf" in line and "href=" in line]
        assert len(export_links) == 1, export_links
        assert "Download PDF Report" in html

        for duplicate in ("Professional Report", "Download Detail", "Export PDF"):
            assert duplicate not in html
    finally:
        _teardown(ctx)


# --- A3 ----------------------------------------------------------------------


def test_every_player_pdf_url_uses_the_same_generator():
    app, client, ctx, user, team, player = _setup()
    try:
        _login(client, user, team)
        with app.test_request_context():
            legacy_id_url = url_for("pdf_export.export_player_pdf",
                                    player_id=player.id)
            name_url = url_for("reports.player_report_pdf",
                               player_name="PagesPlayer")
            legacy_name_url = url_for("analytics.player_report_pdf",
                                      player_name="PagesPlayer")

        for url in (name_url, legacy_id_url):
            response = client.get(url)
            assert response.status_code == 200, (url, response.status_code)
            assert response.content_type == "application/pdf", url
            assert response.data.startswith(b"%PDF"), url
            assert len(response.data) > 1000, url

        # The analytics URL keeps working as a redirect onto that generator.
        redirected = client.get(legacy_name_url, follow_redirects=False)
        assert redirected.status_code == 301
        assert "/reports/player/PagesPlayer/report.pdf" in redirected.headers["Location"]

        # Same layout from both entry points (PDF bytes carry a creation
        # timestamp, so compare the rendered pages' text instead).
        by_name = client.get(name_url)
        by_id = client.get(legacy_id_url)
        assert _pdf_text(by_name.data) == _pdf_text(by_id.data)
    finally:
        _teardown(ctx)


# --- A4 ----------------------------------------------------------------------


def test_players_pages_zip_skips_players_without_stats():
    app, client, ctx, user, team, player = _setup()
    try:
        _login(client, user, team)
        # Active roster player without any stats in this scope.
        db.session.add(Player(team_id=team.id, name="RosterOnlyPlayer",
                              active=True))
        db.session.commit()

        response = client.get("/players/pages.zip")
        assert response.status_code == 200, response.status_code

        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            names = archive.namelist()
            assert "Team_Total_Page.pdf" in names
            assert "PagesPlayer_page.pdf" in names
            assert "RosterOnlyPlayer_page.pdf" not in names
            readme = archive.read("README.txt").decode()
        assert "RosterOnlyPlayer" in readme
    finally:
        _teardown(ctx)
