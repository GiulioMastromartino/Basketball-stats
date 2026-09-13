"""Tests for expiring, revocable, read-only public share links."""

from datetime import datetime, timedelta

from core.models import Game, Organization, Player, PlayerStat, ShareLink, Team, User, db
from web import create_app


def _make_org_team(app, slug_suffix=""):
    org = Organization(name=f"Org{suffix(slug_suffix)}", slug=f"org-{slug_suffix}")
    db.session.add(org)
    db.session.flush()
    team = Team(name=f"Team{suffix(slug_suffix)}", organization_id=org.id,
                slug=f"team-{slug_suffix}")
    db.session.add(team)
    db.session.flush()
    return org, team


def suffix(s):
    return f"-{s}" if s else ""


def _make_user(org, team, username, gm=True):
    from core.models import OrganizationMembership, TeamAssignment
    user = User(username=username, email=f"{username}@t.com",
                organization_id=org.id)
    user.set_password("pw123456")
    db.session.add(user)
    db.session.flush()
    db.session.add(OrganizationMembership(user_id=user.id,
                                         organization_id=org.id, is_gm=gm))
    db.session.add(TeamAssignment(user_id=user.id, team_id=team.id,
                                  is_coach=True))
    db.session.commit()
    return user


def _login(client, user, team):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
        sess["current_team_id"] = team.id
        sess["current_team_name"] = team.name


def _make_game(team, opponent="Opp"):
    g = Game(date="17-02-2024", opponent=opponent, team_score=80,
             opponent_score=70, result="W", game_type="Season",
             sort_date="2024-02-17", source="MANUAL", team_id=team.id)
    db.session.add(g)
    db.session.commit()
    db.session.add(PlayerStat(game_id=g.id, player_name="John Doe",
                              points=20, reb=5, ast=4, minutes="25:00"))
    db.session.commit()
    return g


def _make_player(team, name="John Doe"):
    p = Player(team_id=team.id, name=name, email="secret@example.com")
    db.session.add(p)
    db.session.commit()
    return p


def _setup_two_teams():
    app = create_app("testing")
    client = app.test_client()
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    org_a, team_a = _make_org_team(app, "a")
    org_b, team_b = _make_org_team(app, "b")
    user_a = _make_user(org_a, team_a, "share_user_a")
    game_a = _make_game(team_a)
    player_a = _make_player(team_a)
    game_b = _make_game(team_b, opponent="Other")
    return app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, player_a, game_b


def _teardown(ctx):
    db.session.remove()
    db.drop_all()
    ctx.pop()


def test_create_link_and_fetch_public_game_json():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, g_b = _setup_two_teams()
    try:
        _login(client, user_a, team_a)
        r = client.post("/share", json={"target_type": "game",
                                        "target_id": game_a.id,
                                        "expires_in_days": 7})
        assert r.status_code == 201, r.data
        body = r.get_json()
        assert body["token"] and body["url"].endswith(f"/s/{body['token']}")
        assert len(body["token"]) >= 43  # token_urlsafe(32) entropy

        # Public fetch WITHOUT auth
        with client.session_transaction() as sess:
            sess.clear()
        pub = client.get(f"/s/{body['token']}")
        assert pub.status_code == 200
        payload = pub.get_json()
        assert payload["game"]["opponent"] == game_a.opponent
        assert payload["game"]["team_score"] == 80
        assert payload["game"]["date"] == game_a.date
        assert len(payload["player_totals"]) == 1
        assert payload["player_totals"][0]["player_name"] == "John Doe"
        raw = pub.data.decode()
        assert "secret@example.com" not in raw
    finally:
        _teardown(ctx)


def test_create_player_link_and_fetch_public_json_no_email():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, g_b = _setup_two_teams()
    try:
        _login(client, user_a, team_a)
        r = client.post("/share", json={"target_type": "player",
                                        "target_id": p_a.id})
        assert r.status_code == 201, r.data
        token = r.get_json()["token"]
        with client.session_transaction() as sess:
            sess.clear()
        pub = client.get(f"/s/{token}")
        assert pub.status_code == 200
        payload = pub.get_json()
        assert payload["player"]["name"] == "John Doe"
        assert payload["season_averages"]["games_played"] == 1
        assert payload["season_averages"]["points"] == 20.0
        assert "email" not in pub.data.decode().lower() or \
            "secret@example.com" not in pub.data.decode()
        assert "secret@example.com" not in pub.data.decode()
    finally:
        _teardown(ctx)


def test_expired_link_returns_404():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, g_b = _setup_two_teams()
    try:
        _login(client, user_a, team_a)
        r = client.post("/share", json={"target_type": "game",
                                        "target_id": game_a.id})
        token = r.get_json()["token"]
        link = ShareLink.query.filter_by(token=token).first()
        link.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.session.commit()
        with client.session_transaction() as sess:
            sess.clear()
        assert client.get(f"/s/{token}").status_code == 404
    finally:
        _teardown(ctx)


def test_revoked_link_returns_404_and_delete_revokes():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, g_b = _setup_two_teams()
    try:
        _login(client, user_a, team_a)
        r = client.post("/share", json={"target_type": "game",
                                        "target_id": game_a.id})
        link_id = r.get_json()["id"]
        token = r.get_json()["token"]
        d = client.delete(f"/share/{link_id}")
        assert d.status_code == 200
        assert d.get_json()["revoked"] is True
        with client.session_transaction() as sess:
            sess.clear()
        assert client.get(f"/s/{token}").status_code == 404
    finally:
        _teardown(ctx)


def test_cross_team_create_denied_and_unknown_target_404():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, game_b = _setup_two_teams()
    try:
        _login(client, user_a, team_a)
        # game_b belongs to team_b → 404 (no cross-team leak, no 403 oracle)
        r = client.post("/share", json={"target_type": "game",
                                        "target_id": game_b.id})
        assert r.status_code == 404
        # unknown target → 404
        r2 = client.post("/share", json={"target_type": "game",
                                         "target_id": 999999})
        assert r2.status_code == 404
        r3 = client.post("/share", json={"target_type": "bogus",
                                         "target_id": game_a.id})
        assert r3.status_code == 400
        r4 = client.post("/share", json={"target_type": "game",
                                         "target_id": game_a.id,
                                         "expires_in_days": 31})
        assert r4.status_code == 400
        # unknown token → 404
        with client.session_transaction() as sess:
            sess.clear()
        assert client.get("/s/does-not-exist-token").status_code == 404
    finally:
        _teardown(ctx)


def test_tokens_unique_and_unguessable():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, g_b = _setup_two_teams()
    try:
        _login(client, user_a, team_a)
        tokens = set()
        for _ in range(5):
            r = client.post("/share", json={"target_type": "game",
                                            "target_id": game_a.id})
            assert r.status_code == 201
            t = r.get_json()["token"]
            assert t not in tokens
            assert len(t) >= 43
            tokens.add(t)
        assert ShareLink.query.count() == 5
    finally:
        _teardown(ctx)


def test_revoke_other_team_link_denied():
    app, client, ctx, org_a, team_a, org_b, team_b, user_a, game_a, p_a, g_b = _setup_two_teams()
    try:
        # link owned by team_a
        _login(client, user_a, team_a)
        r = client.post("/share", json={"target_type": "game",
                                        "target_id": game_a.id})
        link_id = r.get_json()["id"]
        # user from org_b tries to revoke
        user_b = _make_user(org_b, team_b, "share_user_b")
        _login(client, user_b, team_b)
        d = client.delete(f"/share/{link_id}")
        assert d.status_code == 404
        link = ShareLink.query.get(link_id)
        assert link.revoked is False
    finally:
        _teardown(ctx)
