"""UI tests for share buttons on game/player detail pages.

Verifies the Share Links UI slice: each detail page renders a Share button
with the correct data attributes, an expiry select (7/14/30, default 7),
a dismissible result box with Copy button, and error handling — without
changing login-state behaviour.
"""

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
from web import create_app


def _setup():
    app = create_app("testing")
    client = app.test_client()
    ctx = app.app_context()
    ctx.push()
    db.create_all()

    org = Organization(name="Share UI Org", slug="share-ui-org")
    db.session.add(org)
    db.session.flush()
    team = Team(name="Share UI Team", organization_id=org.id,
                slug="share-ui-team")
    db.session.add(team)
    db.session.flush()

    user = User(username="share_ui_user", email="share_ui@t.com",
                organization_id=org.id)
    user.set_password("pw123456")
    db.session.add(user)
    db.session.flush()
    db.session.add(OrganizationMembership(user_id=user.id,
                                         organization_id=org.id,
                                         is_gm=False))
    db.session.add(TeamAssignment(user_id=user.id, team_id=team.id,
                                  is_coach=True))

    game = Game(date="17-02-2024", opponent="ShareOpp", team_score=80,
                opponent_score=70, result="W", game_type="Season",
                sort_date="2024-02-17", source="MANUAL", team_id=team.id)
    db.session.add(game)
    db.session.commit()
    db.session.add(PlayerStat(game_id=game.id, player_name="ShareUiPlayer",
                              points=20, reb=5, ast=4, minutes="25:00"))
    db.session.commit()
    player = Player(team_id=team.id, name="ShareUiPlayer")
    db.session.add(player)
    db.session.commit()
    return app, client, ctx, user, team, game, player


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


def _logout(client):
    with client.session_transaction() as sess:
        sess.clear()


def test_game_page_contains_share_button_with_data_attributes():
    app, client, ctx, user, team, game, player = _setup()
    try:
        _login(client, user, team)
        r = client.get(f"/game/{game.id}")
        assert r.status_code == 200, r.status_code
        html = r.data.decode()
        assert 'data-share-button' in html
        assert 'data-share-target-type="game"' in html
        assert f'data-share-target-id="{game.id}"' in html
        # Expiry select: 7/14/30 options, 7 selected by default.
        assert 'data-share-expiry' in html
        assert 'value="7" selected' in html
        assert 'value="14"' in html
        assert 'value="30"' in html
        # Dismissible result box with Copy button + error container.
        assert 'data-share-result' in html
        assert 'data-share-copy' in html
        assert 'data-share-dismiss' in html
        assert 'data-share-error' in html
        # Posts to /share with the game target; CSRF header sent.
        assert '/share' in html
        assert 'X-CSRFToken' in html
        # XSS-safe rendering: URL inserted via textContent, never innerHTML.
        assert 'textContent' in html
    finally:
        _teardown(ctx)


def test_player_page_contains_share_button_with_data_attributes():
    app, client, ctx, user, team, game, player = _setup()
    try:
        _login(client, user, team)
        r = client.get("/player/ShareUiPlayer")
        assert r.status_code == 200, r.status_code
        html = r.data.decode()
        assert 'data-share-button' in html
        assert 'data-share-target-type="player"' in html
        assert f'data-share-target-id="{player.id}"' in html
        assert 'data-share-expiry' in html
        assert 'value="7" selected' in html
        assert 'value="14"' in html
        assert 'value="30"' in html
        assert 'data-share-result' in html
        assert 'data-share-copy' in html
        assert 'data-share-dismiss' in html
        assert 'data-share-error' in html
        assert '/share' in html
        assert 'X-CSRFToken' in html
        assert 'textContent' in html
    finally:
        _teardown(ctx)


def test_anonymous_game_and_player_pages_do_not_crash():
    """Page convention: detail routes require login — anonymous users are
    redirected (no crash, no share POST attempted server-side)."""
    app, client, ctx, user, team, game, player = _setup()
    try:
        _logout(client)
        game_resp = client.get(f"/game/{game.id}", follow_redirects=False)
        assert game_resp.status_code in (302, 401, 403), game_resp.status_code
        player_resp = client.get("/player/ShareUiPlayer",
                                 follow_redirects=False)
        assert player_resp.status_code in (302, 401, 403), \
            player_resp.status_code
        # Following redirects lands on a real page (login), still no crash.
        assert client.get(f"/game/{game.id}",
                          follow_redirects=True).status_code == 200
        assert client.get("/player/ShareUiPlayer",
                          follow_redirects=True).status_code == 200
    finally:
        _teardown(ctx)
