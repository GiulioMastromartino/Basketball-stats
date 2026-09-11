"""
Shared pytest fixtures for basketball stats tests.

This module provides centralized fixtures for:
- Flask application setup
- Database management
- Test client with authentication
- Test data factories
- Mocking utilities
"""

import pytest
import json
from datetime import datetime

# Import app factory and database
from web import create_app, db
from core.models import (
    User,
    Organization,
    Team,
    OrganizationMembership,
    TeamAssignment,
    Game,
    PlayerStat,
    ShotEvent,
    GameEvent,
    Play,
    PlayType,
    PlaySequence,
    LineupSegment,
    Possession,
    ShotZone,
)


# =============================================================================
# Application Fixtures
# =============================================================================


@pytest.fixture(scope="session")
def app():
    """Create application for testing session."""
    test_app = create_app("testing")
    yield test_app


@pytest.fixture(scope="function")
def client(app):
    """Create test client with fresh database for each test."""
    test_client = app.test_client()
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    yield test_client
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture(scope="function")
def db_session(app):
    """Provide database session for tests that need direct DB access."""
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    yield db.session
    db.session.rollback()
    db.drop_all()
    ctx.pop()


# =============================================================================
# User Fixtures
# =============================================================================


@pytest.fixture
def default_org(db_session):
    """Create a default organization for testing (idempotent)."""
    org = Organization.query.filter_by(slug="test-org").first()
    if org is None:
        org = Organization(name="Test Org", slug="test-org")
        db_session.add(org)
        db_session.commit()
    return org


@pytest.fixture
def default_team(db_session, default_org):
    """Create a default team for testing (idempotent)."""
    team = Team.query.filter_by(
        organization_id=default_org.id, slug="test-team"
    ).first()
    if team is None:
        team = Team(name="Test Team", organization_id=default_org.id, slug="test-team")
        db_session.add(team)
        db_session.commit()
    return team


@pytest.fixture(autouse=True)
def _assign_default_team(db_session):
    """Single-team test context: backfill team_id on rows created without one.

    Most unit tests predate multi-tenancy and create Game/Lineup/Play rows
    without a team. Production always sets the team from the session; this
    listener reproduces that default in tests only. It is purely reactive
    (fills NULL team_id at flush time) so tests that manage their own
    orgs/teams are unaffected. Skipped when the multi-tenant tables do
    not exist (e.g. legacy-schema migration tests).
    """
    from sqlalchemy import event, inspect

    try:
        has_teams = inspect(db.engine).has_table("teams")
    except Exception:
        has_teams = False
    if not has_teams:
        yield
        return

    # Provision a fallback team once per test (distinct slugs so tests that
    # manage their own "test-org"/"test-team" never collide with it).
    org = Organization.query.filter_by(slug="auto-test-org").first()
    if org is None:
        org = Organization(name="Auto Test Org", slug="auto-test-org")
        db_session.add(org)
        db_session.flush()
    team = Team.query.filter_by(
        organization_id=org.id, slug="auto-test-team"
    ).first()
    if team is None:
        team = Team(
            name="Auto Test Team",
            organization_id=org.id,
            slug="auto-test-team",
        )
        db_session.add(team)
        db_session.flush()
    fallback_team_id = team.id

    @event.listens_for(db_session, "before_flush")
    def _fill_team_id(session, flush_context, instances):
        for obj in session.new:
            if (
                hasattr(obj, "__table__")
                and "team_id" in obj.__table__.columns
                and getattr(obj, "team_id") is None
            ):
                obj.team_id = fallback_team_id

    try:
        yield
    finally:
        event.remove(db_session, "before_flush", _fill_team_id)


@pytest.fixture
def editor_user(db_session, default_org, default_team):
    """Create an editor user for testing."""
    user = User(username="test_editor", email="editor@test.com", organization_id=default_org.id)
    user.set_password("password123")
    db_session.add(user)
    db_session.flush()
    membership = OrganizationMembership(user_id=user.id, organization_id=default_org.id, is_gm=False)
    db_session.add(membership)
    ta = TeamAssignment(user_id=user.id, team_id=default_team.id, is_coach=False)
    db_session.add(ta)
    db_session.commit()
    return user


@pytest.fixture
def admin_user(db_session, default_org, default_team):
    """Create an admin (GM) user for testing."""
    user = User(username="test_admin", email="admin@test.com", organization_id=default_org.id)
    user.set_password("admin123")
    db_session.add(user)
    db_session.flush()
    membership = OrganizationMembership(user_id=user.id, organization_id=default_org.id, is_gm=True)
    db_session.add(membership)
    ta = TeamAssignment(user_id=user.id, team_id=default_team.id, is_coach=True)
    db_session.add(ta)
    db_session.commit()
    return user


@pytest.fixture
def auth_client(client, editor_user, default_team):
    """Authenticated client as editor user."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(editor_user.id)
        sess['_fresh'] = True
        sess['current_team_id'] = default_team.id
        sess['current_team_name'] = default_team.name
    return client


@pytest.fixture
def admin_client(client, admin_user, default_team):
    """Authenticated client as admin user."""
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_user.id)
        sess['_fresh'] = True
        sess['current_team_id'] = default_team.id
        sess['current_team_name'] = default_team.name
    return client


# =============================================================================
# Game Fixtures
# =============================================================================


@pytest.fixture
def sample_game(db_session, default_team):
    """Create a sample game for testing."""
    game = Game(
        date="17-02-2024",
        opponent="Test Opponents",
        team_score=75,
        opponent_score=68,
        result="W",
        game_type="Season",
        sort_date="2024-02-17",
        source="MANUAL",
        team_id=default_team.id,
    )
    db_session.add(game)
    db_session.commit()
    return game


@pytest.fixture
def sample_games(db_session, default_team):
    """Create multiple sample games for testing aggregations."""
    games = []
    for i in range(3):
        game = Game(
            date=f"{17 + i:02d}-02-2024",
            opponent=f"Opponent {i + 1}",
            team_score=70 + i * 5,
            opponent_score=65 + i * 3,
            result="W",
            game_type="Season",
            sort_date=f"2024-02-{17 + i:02d}",
            source="MANUAL",
            team_id=default_team.id,
        )
        db_session.add(game)
        games.append(game)
    db_session.commit()
    return games


@pytest.fixture
def sample_player_stat(db_session, sample_game):
    """Create a sample player stat for testing."""
    stat = PlayerStat(
        game_id=sample_game.id,
        player_name="John Doe",
        minutes="24:30",
        points=18,
        fgm=7,
        fga=14,
        fg_percent=50.0,
        tpm=2,
        tpa=5,
        tp_percent=40.0,
        ftm=2,
        fta=3,
        ft_percent=66.7,
        oreb=1,
        dreb=4,
        reb=5,
        ast=3,
        stl=2,
        blk=1,
        tov=2,
        pf=3,
        plus_minus=8,
    )
    db_session.add(stat)
    db_session.commit()
    return stat


@pytest.fixture
def sample_player_stats(db_session, sample_game):
    """Create multiple sample player stats for a game."""
    stats_data = [
        ("John Doe", 18, 7, 14, 2, 5, 2, 3, 1, 4, 3, 2, 1, 2, 3, 8),
        ("Jane Smith", 22, 9, 16, 3, 7, 1, 2, 2, 5, 4, 1, 0, 3, 2, 12),
        ("Mike Johnson", 12, 5, 10, 1, 3, 1, 1, 0, 3, 2, 3, 2, 1, 4, -2),
        ("Tom Wilson", 15, 6, 11, 2, 4, 1, 2, 1, 2, 2, 2, 1, 2, 3, 5),
        ("Bob Brown", 8, 3, 8, 0, 1, 2, 4, 1, 3, 1, 0, 0, 1, 2, -1),
    ]

    stats = []
    for data in stats_data:
        stat = PlayerStat(
            game_id=sample_game.id,
            player_name=data[0],
            points=data[1],
            fgm=data[2],
            fga=data[3],
            tpm=data[4],
            tpa=data[5],
            ftm=data[6],
            fta=data[7],
            oreb=data[8],
            dreb=data[9],
            ast=data[10],
            stl=data[11],
            blk=data[12],
            tov=data[13],
            pf=data[14],
            plus_minus=data[15],
            minutes="20:00",
            fg_percent=round(data[2] / data[3] * 100, 1) if data[3] > 0 else 0,
            tp_percent=round(data[4] / data[5] * 100, 1) if data[5] > 0 else 0,
            ft_percent=round(data[6] / data[7] * 100, 1) if data[7] > 0 else 0,
            reb=data[8] + data[9],
        )
        db_session.add(stat)
        stats.append(stat)

    db_session.commit()
    return stats


# =============================================================================
# Shot/Event Fixtures
# =============================================================================


@pytest.fixture
def sample_shot_event(db_session, sample_game):
    """Create a sample shot event for testing."""
    shot = ShotEvent(
        game_id=sample_game.id,
        player_name="John Doe",
        shot_type="2pt",
        result="made",
        points=2,
        x_loc=250.0,
        y_loc=100.0,
        quarter=1,
    )
    db_session.add(shot)
    db_session.commit()
    return shot


@pytest.fixture
def sample_game_events(db_session, sample_game):
    """Create sample game events for timeline testing.

    Events are ordered chronologically:
    1. Starters record game events first (shots, etc.)
    2. Then substitutions occur (SUB_OUT followed by SUB_IN)
    """
    events = []
    starters = ["John Doe", "Jane Smith", "Mike Johnson", "Tom Wilson", "Bob Brown"]
    bench_player = "Sub Player"

    # Starters record events first (they're on the floor to start)
    # These are the actual starting lineup
    for i, player in enumerate(starters):
        event = GameEvent(
            game_id=sample_game.id,
            event_type="SHOT_2PT",
            player_name=player,
            quarter=1,
            timestamp=1000 + i * 100,  # Chronological: 1000, 1100, 1200, 1300, 1400
            time_remaining="09:30",
            score_margin=2,
            game_seconds=30 + i * 10,
            shot_attempt="made" if i % 2 == 0 else "missed",
        )
        db_session.add(event)
        events.append(event)

    # Opponent scores
    event = GameEvent(
        game_id=sample_game.id,
        event_type="OPP_SCORE",
        detail=json.dumps({"points": 2, "shot_type": "2pt", "result": "made"}),
        quarter=1,
        timestamp=5000,
        time_remaining="07:15",
        score_margin=0,
        game_seconds=165,
    )
    db_session.add(event)
    events.append(event)

    # Now a substitution happens - Bob Brown goes out, Sub Player comes in
    event = GameEvent(
        game_id=sample_game.id,
        event_type="SUB_OUT",
        player_name="Bob Brown",
        quarter=1,
        timestamp=10000,
        time_remaining="05:00",
        score_margin=2,
        game_seconds=300,
    )
    db_session.add(event)
    events.append(event)

    event = GameEvent(
        game_id=sample_game.id,
        event_type="SUB_IN",
        player_name=bench_player,
        quarter=1,
        timestamp=10001,
        time_remaining="05:00",
        score_margin=2,
        game_seconds=300,
    )
    db_session.add(event)
    events.append(event)

    db_session.commit()
    return events


@pytest.fixture
def sample_play(db_session):
    """Create a sample play for testing."""
    play_type = PlayType(name="Pick and Roll")
    db_session.add(play_type)
    db_session.commit()

    play = Play(
        name="Horns PnR",
        play_type_id=play_type.id,
        description="Pick and roll from horns set",
    )
    db_session.add(play)
    db_session.commit()
    return play


# =============================================================================
# Mock Fixtures
# =============================================================================


@pytest.fixture
def mock_email_send(mocker):
    """Mock email sending for tests."""
    return mocker.patch("core.services.email_service.mail.send")


@pytest.fixture
def mock_pdf_generation(mocker):
    """Mock WeasyPrint PDF generation."""
    mock_pdf = mocker.MagicMock()
    mock_pdf.write_pdf.return_value = b"fake_pdf_content"
    mocker.patch("weasyprint.HTML", return_value=mock_pdf)
    return mock_pdf


# =============================================================================
# Test Data Fixtures
# =============================================================================


@pytest.fixture
def live_game_payload():
    """Sample payload for live game save endpoint."""
    return {
        "date": "2024-02-17",
        "opponent": "Test Team",
        "team_score": 75,
        "opponent_score": 68,
        "game_type": "Season",
        "player_stats": {
            "John Doe": {
                "points": 18,
                "fgm": 7,
                "fga": 14,
                "tpm": 2,
                "tpa": 5,
                "ftm": 2,
                "fta": 3,
                "oreb": 1,
                "dreb": 4,
                "ast": 3,
                "stl": 2,
                "blk": 1,
                "tov": 2,
                "pf": 3,
                "plus_minus": 8,
                "minutes": "24:30",
            }
        },
        "shot_locations": [
            {
                "shooter": "John Doe",
                "type": "2pt",
                "result": "made",
                "points": 2,
                "x": 250,
                "y": 100,
                "quarter": 1,
                "play_id": None,
            }
        ],
        "game_events": [
            {
                "type": "SHOT_2PT",
                "player": "John Doe",
                "quarter": 1,
                "clockSeconds": 90,
                "time_remaining": "8:30",
                "score_margin": 2,
                "game_seconds": 90,
                "possession_number": 1,
                "timestamp": 1708176000000,
            }
        ],
    }


@pytest.fixture
def sample_csv_content():
    """Sample CSV content for upload testing."""
    return """Player,PTS,FGM,FGA,3PM,3PA,FTM,FTA,OREB,DREB,AST,STL,BLK,TOV,PF,MIN
John Doe,18,7,14,2,5,2,3,1,4,3,2,1,2,3,24:30
Jane Smith,22,9,16,3,7,1,2,2,5,4,1,0,3,2,28:15"""


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def assert_response_json():
    """Helper to assert JSON response structure."""

    def _assert(response, expected_status=200):
        assert response.status_code == expected_status
        data = json.loads(response.data)
        assert data is not None
        return data

    return _assert


@pytest.fixture
def assert_response_success():
    """Helper to assert successful JSON response."""

    def _assert(response):
        data = json.loads(response.data)
        assert response.status_code in [200, 201]
        assert data.get("success", True) is True
        return data

    return _assert
