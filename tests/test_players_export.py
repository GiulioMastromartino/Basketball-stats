"""Tests for the /players/pages.zip export budget and its UI feedback.

The export renders one WeasyPrint PDF per player plus a team page inside a
single synchronous request (103.8s / 1.27 MB for 16 pages on the seeded DB)
while nginx (proxy_read_timeout 120s) and gunicorn (timeout = 120) give up
after 120 seconds. These tests pin down that:

- a selection whose estimated work exceeds the budget is refused *early* with
  an explicit, actionable 422 instead of dying as a 504 gateway timeout;
- a small selection still returns a real ZIP;
- the export stays scoped to the team of the session;
- the Players page tells the user what is going on.
"""

import io
import time
import zipfile

import pytest

from core.models import Game, PlayerStat, Team


def _add_game_with_players(
    db_session, team, player_names, game_type="Season", sort_date="2024-02-17"
):
    """One game with a box score for every given player."""
    game = Game(
        date="17-02-2024",
        opponent="ExportOpp",
        team_score=80,
        opponent_score=70,
        result="W",
        game_type=game_type,
        sort_date=sort_date,
        source="MANUAL",
        team_id=team.id,
    )
    db_session.add(game)
    db_session.flush()
    for name in player_names:
        db_session.add(
            PlayerStat(
                game_id=game.id,
                player_name=name,
                points=10,
                reb=3,
                ast=2,
                minutes="20:00",
            )
        )
    db_session.commit()
    return game


def _export_url(**overrides):
    params = {"game_type": "ALL", "limit": 0, "sort": "ppg", "order": "desc"}
    params.update(overrides)
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"/players/pages.zip?{query}"


# --- the export is refused before it can time out ----------------------------


def test_pages_zip_refuses_a_selection_over_the_budget(
    auth_client, db_session, default_team
):
    """A roster too big for one request gets a fast, explicit error."""
    _add_game_with_players(
        db_session, default_team, [f"Big Roster {i:02d}" for i in range(40)]
    )

    started = time.time()
    response = auth_client.get(_export_url())
    elapsed = time.time() - started

    # An explicit refusal, never a timeout / gateway error.
    assert response.status_code == 422, response.status_code
    assert elapsed < 10, f"the refusal must be immediate, took {elapsed:.1f}s"

    body = response.data.decode()
    assert "too large" in body.lower()
    # ... and it tells the user how to narrow the selection down.
    assert "limit" in body
    assert "game_type" in body
    assert "504" in body
    # No ZIP was produced.
    assert not response.data.startswith(b"PK")


def test_pages_zip_refusal_explains_itself_as_json(
    auth_client, db_session, default_team
):
    _add_game_with_players(
        db_session, default_team, [f"Big Roster {i:02d}" for i in range(40)]
    )

    response = auth_client.get(_export_url(), headers={"Accept": "application/json"})

    assert response.status_code == 422, response.status_code
    payload = response.get_json()
    assert payload["error"] == "export_too_large"
    assert payload["players"] == 40
    assert payload["pages"] == 41  # 40 players + the team total page
    assert payload["estimated_seconds"] > payload["budget_seconds"]
    assert payload["budget_seconds"] <= 120
    assert any("limit" in hint for hint in payload["hints"])
    assert "game_type" in " ".join(payload["hints"])
    assert "limit" in payload["parameters"]
    assert "game_type" in payload["parameters"]


def test_pages_zip_budget_is_configurable(
    auth_client, db_session, default_team, app, monkeypatch
):
    """Deployments (and tests) can tighten the budget of a single request."""
    _add_game_with_players(db_session, default_team, ["Solo Player"])
    monkeypatch.setitem(app.config, "PLAYERS_PAGES_ZIP_BUDGET_SECONDS", 0.5)

    response = auth_client.get(_export_url())

    assert response.status_code == 422, response.status_code
    assert not response.data.startswith(b"PK")


def test_pages_zip_estimate_endpoint_does_not_render_pdfs(
    auth_client, db_session, default_team
):
    """The cheap preview used by the UI never renders a single page."""
    _add_game_with_players(db_session, default_team, ["Preview One"])

    response = auth_client.get(_export_url(estimate=1))

    assert response.status_code == 200, response.status_code
    payload = response.get_json()
    assert payload["players"] == 1
    assert payload["pages"] == 2  # the player page + the team total page
    assert payload["estimated_seconds"] > 0


# --- small selections keep working -------------------------------------------


def test_pages_zip_small_selection_still_returns_a_zip(
    auth_client, db_session, default_team
):
    _add_game_with_players(db_session, default_team, ["Small One", "Small Two"])

    response = auth_client.get(_export_url())

    assert response.status_code == 200, response.status_code
    assert response.content_type == "application/zip"
    assert response.data.startswith(b"PK")

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        names = archive.namelist()
        assert archive.read("Small_One_page.pdf").startswith(b"%PDF")

    assert "Team_Total_Page.pdf" in names
    assert "Small_One_page.pdf" in names
    assert "Small_Two_page.pdf" in names


def test_pages_zip_stays_scoped_to_the_session_team(
    auth_client, db_session, default_team, default_org
):
    """Players of another team never leak into the export."""
    other_team = Team(
        name="Other Export Team",
        organization_id=default_org.id,
        slug="other-export-team",
    )
    db_session.add(other_team)
    db_session.flush()

    _add_game_with_players(db_session, default_team, ["Mine"])
    _add_game_with_players(db_session, other_team, ["Theirs"])

    response = auth_client.get(_export_url())

    assert response.status_code == 200, response.status_code
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        names = archive.namelist()

    assert "Mine_page.pdf" in names
    assert "Theirs_page.pdf" not in names


# --- the page tells the user what is going on --------------------------------


def test_pages_zip_suggested_limit_is_itself_accepted(
    auth_client, db_session, default_team
):
    """A suggested limit must be accepted: the route must never suggest a
    selection that it refuses again with the very same error.

    The suggestion used to count only the roster players that were missing
    from the current listing. A roster player who DID play in the current
    games but has no stats in the last N games was left out, so the route
    suggested a limit whose real export did not fit the budget any more.
    """
    from core.models import Player

    # 40 roster players that played in the OLDER game only ...
    roster_names = [f"Roster {i:02d}" for i in range(40)]
    _add_game_with_players(
        db_session, default_team, roster_names, sort_date="2024-01-01"
    )
    # ... and 5 players in the newest game who are not on the roster.
    _add_game_with_players(
        db_session,
        default_team,
        ["Recent A", "Recent B", "Recent C", "Recent D", "Recent E"],
        sort_date="2024-02-01",
    )
    for name in roster_names:
        db_session.add(Player(team_id=default_team.id, name=name, active=True))
    db_session.commit()

    response = auth_client.get(_export_url(format="json"))

    assert response.status_code == 422, response.status_code
    payload = response.get_json()
    suggested = payload.get("suggested_limit")

    if suggested is None:
        # Nothing fits in the budget: the route must not promise a limit.
        assert payload["suggested_limit"] is None
        return

    second = auth_client.get(_export_url(format="json", limit=suggested))
    assert second.status_code != 422, (
        f"the suggested limit={suggested} is refused again: {second.get_json()}"
    )


def test_players_page_shows_the_export_feedback(auth_client):
    html = auth_client.get("/players").data.decode()

    assert "playersPagesZipBtn" in html
    assert "data-player-count=" in html
    # The status message is announced by screen readers.
    assert 'id="playersPagesZipStatus"' in html
    assert 'aria-live="polite"' in html
    # ... and the button is wired to it.
    assert "playersPagesZipStatus" in html
    assert "Generating" in html
