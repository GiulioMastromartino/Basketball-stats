"""Opponent scout auto-report slice: builder + route tests."""

from urllib.parse import quote

from flask import render_template

from core.models import Game, PlayerStat, ShotEvent, Team
from core.scout_report import build_scout


def _make_game(
    db_session, team_id, opponent, date, sort_date, team_score, opp_score, result
):
    game = Game(
        date=date,
        opponent=opponent,
        team_score=team_score,
        opponent_score=opp_score,
        result=result,
        game_type="Season",
        sort_date=sort_date,
        source="MANUAL",
        team_id=team_id,
    )
    db_session.add(game)
    db_session.flush()
    return game


def _make_stat(
    db_session,
    game_id,
    name,
    points=10,
    fgm=4,
    fga=8,
    tpm=1,
    tpa=3,
    ftm=1,
    fta=2,
    oreb=1,
    dreb=3,
    ast=2,
    tov=1,
):
    stat = PlayerStat(
        game_id=game_id,
        player_name=name,
        minutes="20:00",
        points=points,
        fgm=fgm,
        fga=fga,
        tpm=tpm,
        tpa=tpa,
        ftm=ftm,
        fta=fta,
        oreb=oreb,
        dreb=dreb,
        reb=oreb + dreb,
        ast=ast,
        stl=1,
        blk=0,
        tov=tov,
        pf=1,
        plus_minus=0,
    )
    db_session.add(stat)
    return stat


def _seed_scout_games(db_session, team_id, opponent="Scout Opp"):
    games = [
        _make_game(
            db_session, team_id, opponent, "01-03-2026", "2026-03-01", 80, 70, "W"
        ),
        _make_game(
            db_session, team_id, opponent, "05-03-2026", "2026-03-05", 70, 75, "L"
        ),
        _make_game(
            db_session, team_id, opponent, "09-03-2026", "2026-03-09", 90, 80, "W"
        ),
    ]
    # Star is consistently great, Role is mediocre, Bench warms the pine.
    for game in games:
        _make_stat(
            db_session,
            game.id,
            "Star Player",
            points=25,
            fgm=10,
            fga=18,
            tpm=3,
            tpa=6,
            ftm=2,
            fta=2,
        )
        _make_stat(
            db_session,
            game.id,
            "Role Player",
            points=8,
            fgm=3,
            fga=10,
            tpm=1,
            tpa=4,
            ftm=1,
            fta=2,
        )
    db_session.add(
        ShotEvent(
            game_id=games[0].id,
            player_name="Star Player",
            shot_type="2pt",
            result="made",
            points=2,
            x_loc=250.0,
            y_loc=100.0,
            quarter=1,
        )
    )
    db_session.commit()
    return games


def test_build_scout_record_and_averages(db_session, default_team):
    _seed_scout_games(db_session, default_team.id)

    ctx = build_scout("scout opp", default_team.id, 5)

    assert ctx["has_data"] is True
    assert ctx["opponent"] == "Scout Opp"
    assert ctx["record"]["wins"] == 2
    assert ctx["record"]["losses"] == 1
    assert len(ctx["record"]["games"]) == 3
    # Most recent meeting first.
    assert ctx["record"]["games"][0]["date"] == "09-03-2026"

    assert ctx["averages"] is not None
    # (25 + 8) * 3 games / 3 games per game.
    assert ctx["averages"]["pts"] == 33.0
    # FG: (10 + 3) * 3 = 39 makes on (18 + 10) * 3 = 84 attempts.
    assert ctx["averages"]["fg_pct"] == round(39 / 84 * 100, 1)
    assert ctx["averages"]["reb"] == 8.0
    assert ctx["averages"]["ast"] == 4.0
    assert ctx["averages"]["tov"] == 2.0


def test_build_scout_top_beaters_ranked_by_game_score(db_session, default_team):
    _seed_scout_games(db_session, default_team.id)

    ctx = build_scout("Scout Opp", default_team.id, 5)

    assert len(ctx["top_beaters"]) == 2
    assert ctx["top_beaters"][0]["player_name"] == "Star Player"
    assert ctx["top_beaters"][1]["player_name"] == "Role Player"
    assert ctx["top_beaters"][0]["avg_gmsc"] > ctx["top_beaters"][1]["avg_gmsc"]
    assert ctx["top_beaters"][0]["games"] == 3


def test_build_scout_zone_summary_skips_gracefully_without_shots(
    db_session, default_team
):
    game = _make_game(
        db_session,
        default_team.id,
        "No Shot Opp",
        "01-03-2026",
        "2026-03-01",
        70,
        60,
        "W",
    )
    _make_stat(db_session, game.id, "Lonely Player")
    db_session.commit()

    ctx = build_scout("No Shot Opp", default_team.id, 5)

    assert ctx["has_data"] is True
    assert ctx["averages"] is not None
    assert ctx["zones"]["has_shot_data"] is False
    assert ctx["zones"]["rows"] == []


def test_build_scout_insufficient_data_opponent(db_session, default_team):
    ctx = build_scout("Nobody Team", default_team.id, 5)

    assert ctx["has_data"] is False
    assert ctx["record"] == {"wins": 0, "losses": 0, "games": []}
    assert ctx["averages"] is None
    assert ctx["top_beaters"] == []
    assert ctx["zones"] == {"has_shot_data": False, "rows": []}
    assert ctx["external"] is None


def test_insufficient_data_template_renders(app, db_session, default_team):
    ctx = build_scout("Nobody Team", default_team.id, 5)
    with app.test_request_context():
        html = render_template("game_scout_pdf.html", **ctx)

    assert html.count("insufficient data") >= 4


def test_scout_route_returns_pdf(auth_client, db_session, default_team):
    _seed_scout_games(db_session, default_team.id)

    response = auth_client.get("/reports/scout/Scout%20Opp")

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    assert response.data[:4] == b"%PDF"


def test_scout_route_unknown_opponent_still_returns_pdf(
    auth_client, db_session, default_team
):
    response = auth_client.get("/reports/scout/Nobody%20Team")

    assert response.status_code == 200
    assert response.content_type == "application/pdf"


def test_scout_route_is_team_scoped(
    app, auth_client, db_session, default_team, default_org
):
    other_team = Team(
        name="Other Team", organization_id=default_org.id, slug="other-team"
    )
    db_session.add(other_team)
    db_session.flush()
    _make_game(
        db_session, other_team.id, "Cross Opp", "01-03-2026", "2026-03-01", 100, 40, "W"
    )
    db_session.commit()

    # Builder isolation: other team's history must not leak.
    assert build_scout("Cross Opp", default_team.id, 5)["has_data"] is False
    assert build_scout("Cross Opp", other_team.id, 5)["has_data"] is True

    # Route runs as the default team: 200, and the other team's 100-40
    # blowout must not appear in the default team's scout context.
    response = auth_client.get(f"/reports/scout/Cross%20Opp?team_id={other_team.id}")
    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    ctx = build_scout("Cross Opp", default_team.id, 5)
    assert ctx["has_data"] is False
    with app.test_request_context():
        html = render_template("game_scout_pdf.html", **ctx)
    assert "insufficient data" in html
    assert "100 - 40" not in html


def test_scout_route_missing_external_cache_never_breaks(
    auth_client, db_session, default_team, tmp_path, monkeypatch
):
    _seed_scout_games(db_session, default_team.id)
    monkeypatch.setenv("EXT_CACHE_PATH", str(tmp_path / "missing.db"))

    response = auth_client.get(f"/reports/scout/{quote('Scout Opp')}?limit=2")

    assert response.status_code == 200
    assert response.content_type == "application/pdf"
    ctx = build_scout("Scout Opp", default_team.id, 2)
    assert len(ctx["record"]["games"]) == 2
    # Missing sidecar file degrades to None instead of raising.
    assert ctx["external"] is None
