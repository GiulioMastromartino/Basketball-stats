from core.models import Game, GameEvent, Organization, PlayerStat, Team


def _make_game(db_session, team_id, opponent="Rivals", team_score=85, opponent_score=78):
    game = Game(
        date="10-03-2026",
        opponent=opponent,
        team_score=team_score,
        opponent_score=opponent_score,
        result="W" if team_score > opponent_score else "L",
        game_type="Season",
        sort_date="2026-03-10",
        source="MANUAL",
        team_id=team_id,
    )
    db_session.add(game)
    db_session.flush()
    return game


def test_recap_synthetic_game_has_five_bullets_with_winner_and_top_scorer(
    auth_client, db_session, default_team
):
    game = _make_game(db_session, default_team.id)
    db_session.add_all(
        [
            PlayerStat(
                game_id=game.id,
                player_name="Top Scorer",
                minutes="28:00",
                points=30,
                fgm=11,
                fga=18,
                tpm=4,
                tpa=7,
                ftm=4,
                fta=5,
                oreb=2,
                dreb=5,
                reb=7,
                ast=6,
                stl=2,
                blk=1,
                tov=2,
                pf=2,
                plus_minus=10,
            ),
            PlayerStat(
                game_id=game.id,
                player_name="Role Player",
                minutes="20:00",
                points=8,
                fgm=3,
                fga=8,
                tpm=1,
                tpa=3,
                ftm=1,
                fta=2,
                oreb=1,
                dreb=2,
                reb=3,
                ast=2,
                stl=0,
                blk=0,
                tov=1,
                pf=1,
                plus_minus=3,
            ),
        ]
    )
    # Margin swing: dip then surge, plus Q4 clutch window data.
    db_session.add_all(
        [
            GameEvent(
                game_id=game.id,
                event_type="OPP_SCORE",
                detail='{"points": 2}',
                quarter=1,
                timestamp=100,
                time_remaining="08:00",
                score_margin=4,
                game_seconds=120,
            ),
            GameEvent(
                game_id=game.id,
                event_type="OPP_SCORE",
                detail='{"points": 6}',
                quarter=2,
                timestamp=200,
                time_remaining="06:00",
                score_margin=-4,
                game_seconds=840,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_3PT",
                player_name="Top Scorer",
                quarter=3,
                timestamp=300,
                time_remaining="04:00",
                score_margin=8,
                game_seconds=1360,
                shot_attempt="made",
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Top Scorer",
                quarter=4,
                timestamp=400,
                time_remaining="02:00",
                score_margin=3,
                game_seconds=2280,
                shot_attempt="made",
            ),
        ]
    )
    db_session.commit()

    response = auth_client.get(f"/reports/recap/{game.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["game_id"] == game.id
    bullets = data["bullets"]
    assert len(bullets) == 5
    assert all(isinstance(b, str) and b.strip() for b in bullets)
    joined = " ".join(bullets)
    assert "85" in joined and "78" in joined
    assert "Top Scorer" in joined


def test_recap_sparse_game_returns_five_neutral_bullets(
    auth_client, db_session, default_team
):
    game = _make_game(
        db_session, default_team.id, opponent="Ghosts", team_score=70, opponent_score=60
    )
    db_session.commit()

    response = auth_client.get(f"/reports/recap/{game.id}")
    assert response.status_code == 200
    data = response.get_json()
    bullets = data["bullets"]
    assert len(bullets) == 5
    assert all(isinstance(b, str) and b.strip() for b in bullets)
    # Sparse game: no player stats, no events -> neutral degradation lines.
    joined = " ".join(bullets).lower()
    assert "no individual player stats" in joined
    assert "not available" in joined or "not recorded" in joined


def test_recap_early_events_only_never_count_as_clutch(
    auth_client, db_session, default_team
):
    # Truncated event list (Q1-Q2 only) with a close margin must not be
    # promoted into a clutch finish: the window is anchored to regulation.
    game = _make_game(
        db_session, default_team.id, opponent="Early Only", team_score=80, opponent_score=70
    )
    db_session.add_all(
        [
            GameEvent(
                game_id=game.id,
                event_type="OPP_SCORE",
                detail='{"points": 2}',
                quarter=1,
                timestamp=100,
                time_remaining="08:00",
                score_margin=2,
                game_seconds=120,
            ),
            GameEvent(
                game_id=game.id,
                event_type="SHOT_2PT",
                player_name="Top Scorer",
                quarter=2,
                timestamp=200,
                time_remaining="06:00",
                score_margin=3,
                game_seconds=840,
                shot_attempt="made",
            ),
        ]
    )
    db_session.commit()

    response = auth_client.get(f"/reports/recap/{game.id}")
    assert response.status_code == 200
    bullets = response.get_json()["bullets"]
    assert len(bullets) == 5
    clutch = bullets[4].lower()
    assert "within 5 points in the last 5 minutes" not in clutch
    assert "final margin 10" in clutch


def test_recap_cross_team_returns_404(auth_client, db_session, default_org):
    other_team = Team(name="Other Team", organization_id=default_org.id, slug="other-team")
    db_session.add(other_team)
    db_session.flush()
    game = _make_game(db_session, other_team.id, opponent="Strangers")
    db_session.commit()

    response = auth_client.get(f"/reports/recap/{game.id}")
    assert response.status_code == 404


def test_recap_unknown_game_returns_404(auth_client, db_session, default_team):
    response = auth_client.get("/reports/recap/999999")
    assert response.status_code == 404
