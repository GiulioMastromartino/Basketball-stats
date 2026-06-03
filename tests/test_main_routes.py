import unittest
import json
from web import create_app, db
from core.models import User, Organization, Team, OrganizationMembership, TeamAssignment, Game, PlayerStat
from core.services.analytics_service import AnalyticsService


class TestMainRoutes(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

        # Create default org and team
        org = Organization(name="Test Org", slug="test-org")
        db.session.add(org)
        db.session.flush()
        team = Team(name="Test Team", organization_id=org.id, slug="test-team")
        db.session.add(team)
        db.session.flush()
        self.team_id = team.id

        # Create test user
        self.username = "main_test_user"
        self.password = "password"
        user = User(
            username=self.username,
            email="main@example.com",
            organization_id=org.id,
        )
        user.set_password(self.password)
        db.session.add(user)
        db.session.flush()
        membership = OrganizationMembership(user_id=user.id, organization_id=org.id, is_gm=False)
        db.session.add(membership)
        ta = TeamAssignment(user_id=user.id, team_id=team.id)
        db.session.add(ta)

        # Create dummy game
        game = Game(
            team_id=team.id,
            date="01/01/2024",
            opponent="TestOpp",
            team_score=100,
            opponent_score=90,
            result="W",
            game_type="Season",
            sort_date="2024-01-01",
            source="MANUAL",
        )
        db.session.add(game)
        db.session.commit()
        self.game_id = game.id

        # Add stats
        p_stat = PlayerStat(
            game_id=game.id,
            player_name="Player1",
            minutes="20:00",
            points=10,
            fgm=5,
            fga=10,
            reb=5,
            ast=2,
            tov=1,
            stl=1,
            blk=0,
            pf=2,
            oreb=2,
            dreb=3,
            tpm=0,
            tpa=0,
            ftm=0,
            fta=0,
            fg_percent=50.0,
            tp_percent=0,
            ft_percent=0,
            plus_minus=0,
        )
        second_stat = PlayerStat(
            game_id=game.id,
            player_name="Player2",
            minutes="15:00",
            points=8,
            fgm=3,
            fga=8,
            reb=4,
            ast=1,
            tov=2,
            stl=0,
            blk=1,
            pf=1,
            oreb=1,
            dreb=3,
            tpm=1,
            tpa=3,
            ftm=1,
            fta=2,
            fg_percent=37.5,
            tp_percent=33.3,
            ft_percent=50.0,
            plus_minus=0,
        )
        db.session.add(p_stat)
        db.session.add(second_stat)
        db.session.commit()

        # Login
        self.client.post(
            "/auth/login",
            data={"username": self.username, "password": self.password},
            follow_redirects=True,
        )

        # Set current team in session
        with self.client.session_transaction() as sess:
            sess['current_team_id'] = team.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TestOpp", response.data)
        # Look for score components separately since formatting may vary
        self.assertIn(b"100", response.data)
        self.assertIn(b"90", response.data)

    def test_game_detail(self):
        response = self.client.get(f"/game/{self.game_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Player1", response.data)
        self.assertIn(b"10", response.data)  # Points

    def test_player_detail(self):
        response = self.client.get("/player/Player1")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Player1", response.data)
        # Check for actual content on page instead of specific string
        self.assertIn(b"Points", response.data)

    def test_players_table_team_total_and_exclusion(self):
        response = self.client.get("/players?view=table")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"TEAM TOTAL", response.data)
        self.assertIn(b"18.0", response.data)

        excluded_response = self.client.get(
            "/players?view=table&exclude_player=Player1"
        )
        self.assertEqual(excluded_response.status_code, 200)
        self.assertIn(b"team total excludes Player1", excluded_response.data)
        self.assertIn(b"without Player1", excluded_response.data)
        self.assertIn(b"8.0", excluded_response.data)

    def test_players_cards_team_total_and_exclusion(self):
        response = self.client.get("/players?view=cards")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Team Total", response.data)
        self.assertIn(b"18.0", response.data)

        excluded_response = self.client.get(
            "/players?view=cards&exclude_player=Player2"
        )
        self.assertEqual(excluded_response.status_code, 200)
        self.assertIn(b"team total excludes Player2", excluded_response.data)
        self.assertIn(b"without Player2", excluded_response.data)
        self.assertIn(b"10.0", excluded_response.data)

    def test_team_detail_page(self):
        response = self.client.get(
            "/team-detail?game_type=Season&exclude_player=Player2"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Team Total", response.data)
        self.assertIn(b"without Player2", response.data)
        self.assertIn(b"Download Report", response.data)
        self.assertIn(b"+10.0", response.data)

    def test_opponent_detail_page_renders_summary_and_matchups(self):
        second_game = Game(
            team_id=self.team_id,
            date="15/01/2024",
            opponent="TestOpp",
            team_score=88,
            opponent_score=92,
            result="L",
            game_type="Friendly",
            sort_date="2024-01-15",
            source="MANUAL",
        )
        other_opponent = Game(
            team_id=self.team_id,
            date="20/01/2024",
            opponent="OtherOpp",
            team_score=77,
            opponent_score=70,
            result="W",
            game_type="Season",
            sort_date="2024-01-20",
            source="MANUAL",
        )
        db.session.add(second_game)
        db.session.add(other_opponent)
        db.session.commit()

        db.session.add_all(
            [
                PlayerStat(
                    game_id=second_game.id,
                    player_name="Scorer B",
                    minutes="24:00",
                    points=20,
                    fgm=8,
                    fga=15,
                    reb=6,
                    ast=4,
                    tov=2,
                    stl=1,
                    blk=0,
                    pf=2,
                    oreb=2,
                    dreb=4,
                    tpm=2,
                    tpa=5,
                    ftm=2,
                    fta=2,
                    fg_percent=53.3,
                    tp_percent=40.0,
                    ft_percent=100.0,
                    plus_minus=0,
                ),
                PlayerStat(
                    game_id=second_game.id,
                    player_name="Creator B",
                    minutes="18:00",
                    points=7,
                    fgm=3,
                    fga=7,
                    reb=8,
                    ast=5,
                    tov=1,
                    stl=2,
                    blk=1,
                    pf=1,
                    oreb=3,
                    dreb=5,
                    tpm=1,
                    tpa=2,
                    ftm=0,
                    fta=0,
                    fg_percent=42.9,
                    tp_percent=50.0,
                    ft_percent=0,
                    plus_minus=0,
                ),
            ]
        )
        db.session.commit()

        response = self.client.get("/teams/TestOpp")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Opponent Detail", response.data)
        self.assertIn(b"TestOpp", response.data)
        self.assertIn(b"1", response.data)
        self.assertIn(b"win", response.data.lower())
        self.assertIn(b"loss", response.data.lower())
        self.assertIn(b"15/01/2024", response.data)
        self.assertIn(b"01/01/2024", response.data)
        self.assertNotIn(b"OtherOpp", response.data)
        self.assertIn(b"Player1", response.data)
        self.assertIn(b"Scorer B", response.data)
        self.assertIn(b"Full game detail", response.data)

    def test_opponent_detail_page_handles_missing_player_stats(self):
        sparse_game = Game(
            team_id=self.team_id,
            date="11/02/2024",
            opponent="SparseOpp",
            team_score=61,
            opponent_score=59,
            result="W",
            game_type="Season",
            sort_date="2024-02-11",
            source="MANUAL",
        )
        db.session.add(sparse_game)
        db.session.commit()

        response = self.client.get("/teams/SparseOpp")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"SparseOpp", response.data)
        self.assertIn(b"61", response.data)
        self.assertIn(b"59", response.data)
        self.assertIn(b"Advanced", response.data)
        self.assertIn(b"--", response.data)

    def test_teams_page_links_to_opponent_detail(self):
        response = self.client.get("/games-list")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/teams/TestOpp", response.data)

    def test_build_opponent_game_card_includes_top_players_by_gamescore(self):
        game = Game.query.filter_by(opponent="TestOpp").first()

        extra_stats = []
        for idx in range(2, 14):
            extra_stats.append(
                PlayerStat(
                    game_id=game.id,
                    player_name=f"Bench{idx}",
                    minutes="05:00",
                    points=idx,
                    fgm=max(idx // 2, 1),
                    fga=idx + 2,
                    reb=idx % 4,
                    ast=idx % 3,
                    tov=1,
                    stl=0,
                    blk=0,
                    pf=1,
                    oreb=0,
                    dreb=idx % 4,
                    tpm=0,
                    tpa=1,
                    ftm=0,
                    fta=0,
                    fg_percent=0,
                    tp_percent=0,
                    ft_percent=0,
                    plus_minus=0,
                )
            )
        db.session.add_all(extra_stats)
        db.session.commit()

        card = AnalyticsService.build_opponent_game_card(game)

        self.assertIn("top_players_by_gamescore", card)
        self.assertEqual(len(card["top_players_by_gamescore"]), 10)
        self.assertEqual(card["top_players_by_gamescore"][0]["player"], "Player1")
        self.assertIn("fgm", card["top_players_by_gamescore"][0])
        self.assertIn("ts_pct", card["top_players_by_gamescore"][0])
        self.assertIn("ortg", card["top_players_by_gamescore"][0])
        self.assertGreaterEqual(
            card["top_players_by_gamescore"][0]["game_score"],
            card["top_players_by_gamescore"][-1]["game_score"],
        )

    def test_live_game_save(self):
        # The game_service.py expects player_stats to be a DICT, not a list
        # keys are player names, values are stat dicts
        payload = {
            "opponent": "LiveOpponent",
            "date": "2024-02-14",
            "game_type": "Friendly",
            "team_score": 80,
            "opponent_score": 75,
            "player_stats": {
                "PlayerNew": {
                    "minutes": "15:00",
                    "points": 15,
                    "fgm": 7,
                    "fga": 14,
                    "tpm": 1,
                    "tpa": 3,
                    "ftm": 0,
                    "fta": 0,
                    "reb": 5,
                    "ast": 3,
                    "tov": 1,
                    "stl": 2,
                    "blk": 0,
                    "pf": 2,
                    "oreb": 2,
                    "dreb": 3,
                }
            },
            "events": [],
        }

        response = self.client.post(
            "/live-game/save", data=json.dumps(payload), content_type="application/json"
        )

        self.assertEqual(response.status_code, 201)
        data = json.loads(response.data)
        self.assertTrue(data["success"])

        # Verify in DB
        game = Game.query.filter_by(opponent="LiveOpponent").first()
        self.assertIsNotNone(game)
        self.assertEqual(game.team_score, 80)
