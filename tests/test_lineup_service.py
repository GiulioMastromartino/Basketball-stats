"""
Unit tests for core/services/lineup_service.py.

Tests lineup segment building, event linking, stat calculation, and feature gating.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime

from core.models import (
    db,
    Game,
    GameEvent,
    Lineup,
    LineupSegment,
    PlayerLineupStats,
)
from core.services.lineup_service import (
    build_lineup_segments,
    process_game_lineups,
    populate_player_lineup_stats,
    generate_lineup_hash,
    get_or_create_lineup,
    update_lineup_cached_stats,
    calculate_segment_stats,
    link_events_to_segments,
)


def create_game_event(
    game_id,
    event_type,
    timestamp,
    player_name=None,
    quarter=1,
    shot_attempt=None,
    detail=None,
    game_seconds=None,
    possession_number=None,
    lineup_segment_id=None,
):
    """Helper function to create GameEvent objects."""
    event = GameEvent(
        game_id=game_id,
        event_type=event_type,
        player_name=player_name,
        timestamp=timestamp,
        quarter=quarter,
        shot_attempt=shot_attempt,
        detail=detail,
        game_seconds=game_seconds,
        possession_number=possession_number,
        lineup_segment_id=lineup_segment_id,
    )
    return event


class TestBuildLineupSegments:
    """Tests for build_lineup_segments function."""

    @pytest.mark.integration
    def test_with_explicit_starting_lineup(self, db_session, sample_game):
        """When starting_lineup is provided, use it directly."""
        starting_five = ["Player A", "Player B", "Player C", "Player D", "Player E"]

        events = [
            create_game_event(
                sample_game.id, "SHOT_2PT", 100, "Player A", shot_attempt="made"
            ),
            create_game_event(
                sample_game.id, "SHOT_3PT", 200, "Player B", shot_attempt="missed"
            ),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        segment_ids = build_lineup_segments(
            sample_game.id, events, starting_lineup=starting_five
        )

        assert len(segment_ids) == 1
        segment = LineupSegment.query.get(segment_ids[0])
        assert segment is not None
        assert sorted(segment.players) == sorted(starting_five)

    @pytest.mark.integration
    def test_infers_starters_from_events_before_sub_in(self, db_session, sample_game):
        """Infers starters from first 5 players with events before first SUB_IN."""
        starters = ["Starter1", "Starter2", "Starter3", "Starter4", "Starter5"]

        events = []
        ts = 0
        for starter in starters:
            events.append(
                create_game_event(
                    sample_game.id, "SHOT_2PT", ts, starter, shot_attempt="made"
                )
            )
            ts += 10

        events.append(create_game_event(sample_game.id, "SUB_IN", ts + 100, "Bench1"))
        events.append(
            create_game_event(sample_game.id, "SUB_OUT", ts + 101, "Starter1")
        )

        for e in events:
            db_session.add(e)
        db_session.commit()

        events_sorted = sorted(events, key=lambda x: x.timestamp)
        segment_ids = build_lineup_segments(
            sample_game.id, events_sorted, starting_lineup=None
        )

        assert len(segment_ids) >= 1
        first_segment = LineupSegment.query.get(segment_ids[0])
        assert sorted(first_segment.players) == sorted(starters)

    @pytest.mark.integration
    def test_returns_empty_if_less_than_5_starters_inferred(
        self, db_session, sample_game
    ):
        """Returns [] if can't identify 5 starters."""
        events = [
            create_game_event(
                sample_game.id, "SHOT_2PT", 0, "Player1", shot_attempt="made"
            ),
            create_game_event(
                sample_game.id, "SHOT_2PT", 10, "Player2", shot_attempt="made"
            ),
            create_game_event(
                sample_game.id, "SHOT_2PT", 20, "Player3", shot_attempt="made"
            ),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        segment_ids = build_lineup_segments(
            sample_game.id, events, starting_lineup=None
        )

        assert segment_ids == []

    @pytest.mark.integration
    def test_handles_unmatched_sub_out(self, db_session, sample_game):
        """Continues when SUB_OUT has no matching SUB_IN."""
        starting_five = ["P1", "P2", "P3", "P4", "P5"]

        events = [
            create_game_event(sample_game.id, "SHOT_2PT", 0, "P1", shot_attempt="made"),
            create_game_event(sample_game.id, "SUB_OUT", 50, "P1"),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()


        # Should not crash on unmatched SUB_OUT, just log a warning
        segment_ids = build_lineup_segments(
            sample_game.id, events, starting_lineup=starting_five
        )


        assert len(segment_ids) == 1
        segment = LineupSegment.query.get(segment_ids[0])
        assert segment is not None

    @pytest.mark.integration
    def test_rollback_on_error(self, db_session, sample_game):
        """Existing segments preserved if error occurs during processing."""
        starting_five = ["P1", "P2", "P3", "P4", "P5"]

        existing_segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=["Old1", "Old2", "Old3", "Old4", "Old5"],
            lineup_hash=generate_lineup_hash(["Old1", "Old2", "Old3", "Old4", "Old5"]),
        )
        db_session.add(existing_segment)
        db_session.commit()
        existing_id = existing_segment.id

        events = [
            create_game_event(sample_game.id, "SHOT_2PT", 0, "P1"),
        ]

        with patch(
            "core.services.lineup_service.get_or_create_lineup",
            side_effect=Exception("Simulated error"),
        ):
            with pytest.raises(Exception):
                build_lineup_segments(
                    sample_game.id, events, starting_lineup=starting_five
                )

        db_session.rollback()
        old_segment = LineupSegment.query.get(existing_id)
        assert old_segment is not None


class TestProcessGameLineups:
    """Tests for process_game_lineups orchestrator."""

    @pytest.mark.integration
    def test_creates_segments_links_events_populates_stats(
        self, db_session, sample_game
    ):
        """Full pipeline creates segments, links events, calculates stats."""
        starting_five = ["P1", "P2", "P3", "P4", "P5"]

        events = [
            create_game_event(
                sample_game.id,
                "SHOT_2PT",
                0,
                "P1",
                shot_attempt="made",
                game_seconds=0,
                possession_number=1,
            ),
            create_game_event(
                sample_game.id,
                "SHOT_3PT",
                100,
                "P2",
                shot_attempt="made",
                game_seconds=10,
                possession_number=2,
            ),
            create_game_event(
                sample_game.id,
                "FT_MADE",
                150,
                "P3",
                game_seconds=15,
                possession_number=3,
            ),
            create_game_event(
                sample_game.id, "OPP_SCORE", 200, None, detail="2", game_seconds=20
            ),
            create_game_event(sample_game.id, "SUB_OUT", 300, "P1"),
            create_game_event(sample_game.id, "SUB_IN", 301, "Bench1"),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        events_sorted = sorted(events, key=lambda x: x.timestamp)
        process_game_lineups(
            sample_game.id, events_sorted, starting_lineup=starting_five
        )

        segments = LineupSegment.query.filter_by(game_id=sample_game.id).all()
        assert len(segments) >= 1

        updated_events = GameEvent.query.filter_by(game_id=sample_game.id).all()
        linked_events = [e for e in updated_events if e.lineup_segment_id is not None]
        assert len(linked_events) > 0

        player_stats = (
            PlayerLineupStats.query.join(LineupSegment)
            .filter(LineupSegment.game_id == sample_game.id)
            .all()
        )
        assert len(player_stats) >= 5

    @pytest.mark.integration
    def test_early_return_if_no_segments_created(self, db_session, sample_game):
        """Returns early if build_lineup_segments returns empty list."""
        events = [
            create_game_event(sample_game.id, "SHOT_2PT", 0, "P1"),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        process_game_lineups(sample_game.id, events, starting_lineup=None)

        segments = LineupSegment.query.filter_by(game_id=sample_game.id).all()
        assert segments == []

    @pytest.mark.integration
    def test_updates_lineup_cached_stats(self, db_session, sample_game):
        """Lineup table is updated with aggregated stats."""
        starting_five = ["P1", "P2", "P3", "P4", "P5"]

        events = [
            create_game_event(
                sample_game.id,
                "SHOT_2PT",
                0,
                "P1",
                shot_attempt="made",
                possession_number=1,
            ),
            create_game_event(
                sample_game.id,
                "SHOT_2PT",
                50,
                "P2",
                shot_attempt="made",
                possession_number=2,
            ),
            create_game_event(
                sample_game.id, "OPP_SCORE", 100, None, detail="2", possession_number=3
            ),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        events_sorted = sorted(events, key=lambda x: x.timestamp)
        process_game_lineups(
            sample_game.id, events_sorted, starting_lineup=starting_five
        )

        lineup = Lineup.query.filter_by(
            lineup_hash=generate_lineup_hash(starting_five)
        ).first()

        assert lineup is not None
        assert lineup.points_scored == 4
        assert lineup.points_allowed == 2
        assert lineup.total_possessions > 0


class TestPopulatePlayerLineupStats:
    """Tests for stat aggregation in populate_player_lineup_stats."""

    @pytest.mark.integration
    def test_aggregates_shots_free_throws_turnovers(self, db_session, sample_game):
        """Core stats (shots, FT, TOV) are counted correctly."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=players,
            lineup_hash=generate_lineup_hash(players),
        )
        db_session.add(segment)
        db_session.flush()

        events = [
            create_game_event(
                sample_game.id,
                "SHOT_2PT",
                10,
                "P1",
                shot_attempt="made",
                lineup_segment_id=segment.id,
            ),
            create_game_event(
                sample_game.id,
                "SHOT_2PT",
                20,
                "P1",
                shot_attempt="missed",
                lineup_segment_id=segment.id,
            ),
            create_game_event(
                sample_game.id,
                "SHOT_3PT",
                30,
                "P2",
                shot_attempt="made",
                lineup_segment_id=segment.id,
            ),
            create_game_event(
                sample_game.id, "FT_MADE", 40, "P3", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id, "FT_MISS", 45, "P3", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id, "TURNOVER", 50, "P4", lineup_segment_id=segment.id
            ),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        populate_player_lineup_stats(segment.id)

        p1_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P1"
        ).first()
        assert p1_stats is not None
        assert p1_stats.fga == 2
        assert p1_stats.fgm == 1
        assert p1_stats.points == 2

        p2_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P2"
        ).first()
        assert p2_stats.fga == 1
        assert p2_stats.tpa == 1
        assert p2_stats.tpm == 1
        assert p2_stats.points == 3

        p3_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P3"
        ).first()
        assert p3_stats.fta == 2
        assert p3_stats.ftm == 1
        assert p3_stats.points == 1

        p4_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P4"
        ).first()
        assert p4_stats.tov == 1

    @pytest.mark.integration
    def test_aggregates_rebounds_assists_steals_blocks(self, db_session, sample_game):
        """Extended stats (REB, AST, STL, BLK) are counted correctly."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=players,
            lineup_hash=generate_lineup_hash(players),
        )
        db_session.add(segment)
        db_session.flush()

        events = [
            create_game_event(
                sample_game.id, "OREB", 10, "P1", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id, "DREB", 20, "P2", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id, "AST", 30, "P3", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id, "STL", 40, "P4", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id, "BLK", 50, "P5", lineup_segment_id=segment.id
            ),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        populate_player_lineup_stats(segment.id)

        p1_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P1"
        ).first()
        assert p1_stats.oreb == 1

        p2_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P2"
        ).first()
        assert p2_stats.dreb == 1

        p3_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P3"
        ).first()
        assert p3_stats.ast == 1

        p4_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P4"
        ).first()
        assert p4_stats.stl == 1

        p5_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P5"
        ).first()
        assert p5_stats.blk == 1

    @pytest.mark.integration
    def test_handles_oreb_dreb_event_types(self, db_session, sample_game):
        """Both OREB/DREB and REBOUND_OFFENSIVE/DEFENSIVE event types work."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        segment = LineupSegment(
            game_id=sample_game.id,
            start_timestamp=0,
            end_timestamp=100,
            quarter=1,
            players=players,
            lineup_hash=generate_lineup_hash(players),
        )
        db_session.add(segment)
        db_session.flush()

        events = [
            create_game_event(
                sample_game.id, "OREB", 10, "P1", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id,
                "REBOUND_OFFENSIVE",
                20,
                "P2",
                lineup_segment_id=segment.id,
            ),
            create_game_event(
                sample_game.id, "DREB", 30, "P3", lineup_segment_id=segment.id
            ),
            create_game_event(
                sample_game.id,
                "REBOUND_DEFENSIVE",
                40,
                "P4",
                lineup_segment_id=segment.id,
            ),
        ]
        for e in events:
            db_session.add(e)
        db_session.commit()

        populate_player_lineup_stats(segment.id)

        p1_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P1"
        ).first()
        assert p1_stats.oreb == 1

        p2_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P2"
        ).first()
        assert p2_stats.oreb == 1

        p3_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P3"
        ).first()
        assert p3_stats.dreb == 1

        p4_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=segment.id, player_name="P4"
        ).first()
        assert p4_stats.dreb == 1


class TestFeatureActivation:
    """Tests for lineup feature gating in game_service."""

    @pytest.mark.integration
    def test_processes_when_schema_version_gte_2(self, db_session):
        """Lineups processed when schema_version >= 2."""
        from core.services.game_service import create_game_from_live_data

        data = {
            "schema_version": 2,
            "date": "2024-02-17",
            "opponent": "Test Team",
            "team_score": 75,
            "opponent_score": 70,
            "game_type": "Season",
            "starting_lineup": ["P1", "P2", "P3", "P4", "P5"],
            "game_events": [
                {
                    "type": "SHOT_2PT",
                    "player": "P1",
                    "timestamp": 100,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
            ],
        }

        game = create_game_from_live_data(data)

        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert len(segments) >= 1, "Lineup segments should be created with schema_version=2"


# =============================================================================
# Lineup API Integration Tests (End-to-End)
# =============================================================================


class TestLineupAPIIntegration:
    """End-to-end tests for lineup feature from game creation to API retrieval."""

    @pytest.fixture
    def lineup_test_payload(self):
        """Create a payload with lineup tracking enabled."""
        return {
            "opponent": "Lineup API Test Team",
            "team_score": 85,
            "opponent_score": 78,
            "date": "2024-02-17",
            "schema_version": 2,
            "features": {"LINEUP_TRACKING": True},
            "starting_lineup": ["Alice", "Bob", "Carol", "Dave", "Eve"],
            "player_stats": {
                "Alice": {
                    "points": 15,
                    "fgm": 6,
                    "fga": 12,
                    "tpm": 1,
                    "tpa": 3,
                    "ftm": 2,
                    "fta": 2,
                    "oreb": 1,
                    "dreb": 3,
                    "ast": 4,
                    "stl": 2,
                    "blk": 1,
                },
                "Bob": {
                    "points": 12,
                    "fgm": 5,
                    "fga": 10,
                    "tpm": 0,
                    "tpa": 2,
                    "ftm": 2,
                    "fta": 3,
                    "oreb": 2,
                    "dreb": 2,
                    "ast": 3,
                    "stl": 1,
                    "blk": 0,
                },
                "Carol": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 8,
                    "tpm": 0,
                    "tpa": 0,
                    "ftm": 2,
                    "fta": 2,
                    "oreb": 0,
                    "dreb": 4,
                    "ast": 5,
                    "stl": 0,
                    "blk": 2,
                },
                "Dave": {
                    "points": 8,
                    "fgm": 3,
                    "fga": 6,
                    "tpm": 1,
                    "tpa": 2,
                    "ftm": 1,
                    "fta": 2,
                    "oreb": 1,
                    "dreb": 2,
                    "ast": 2,
                    "stl": 3,
                    "blk": 0,
                },
                "Eve": {
                    "points": 6,
                    "fgm": 2,
                    "fga": 5,
                    "tpm": 0,
                    "tpa": 1,
                    "ftm": 2,
                    "fta": 2,
                    "oreb": 0,
                    "dreb": 3,
                    "ast": 1,
                    "stl": 1,
                    "blk": 1,
                },
                "Frank": {
                    "points": 10,
                    "fgm": 4,
                    "fga": 7,
                    "tpm": 0,
                    "tpa": 1,
                    "ftm": 2,
                    "fta": 2,
                    "oreb": 1,
                    "dreb": 2,
                    "ast": 2,
                    "stl": 1,
                    "blk": 0,
                },
            },
            "game_events": [
                # Starters record events first
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "Alice",
                    "timestamp": 1000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "Bob",
                    "timestamp": 1100,
                    "quarter": 1,
                    "shot_attempt": "missed",
                },
                {
                    "event_type": "OREB",
                    "player_name": "Carol",
                    "timestamp": 1150,
                    "quarter": 1,
                },
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "Carol",
                    "timestamp": 1200,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
                {
                    "event_type": "AST",
                    "player_name": "Dave",
                    "timestamp": 1200,
                    "quarter": 1,
                },
                {
                    "event_type": "STL",
                    "player_name": "Eve",
                    "timestamp": 2000,
                    "quarter": 1,
                },
                {
                    "event_type": "BLK",
                    "player_name": "Alice",
                    "timestamp": 2500,
                    "quarter": 1,
                },
                # First substitution
                {
                    "event_type": "SUB_OUT",
                    "player_name": "Eve",
                    "timestamp": 10000,
                    "quarter": 1,
                },
                {
                    "event_type": "SUB_IN",
                    "player_name": "Frank",
                    "timestamp": 10001,
                    "quarter": 1,
                },
                # Frank records some stats
                {
                    "event_type": "SHOT_2PT",
                    "player_name": "Frank",
                    "timestamp": 11000,
                    "quarter": 1,
                    "shot_attempt": "made",
                },
                {
                    "event_type": "DREB",
                    "player_name": "Frank",
                    "timestamp": 12000,
                    "quarter": 1,
                },
                # Second substitution
                {
                    "event_type": "SUB_OUT",
                    "player_name": "Dave",
                    "timestamp": 20000,
                    "quarter": 2,
                },
                {
                    "event_type": "SUB_IN",
                    "player_name": "Eve",
                    "timestamp": 20001,
                    "quarter": 2,
                },
            ],
        }

    @pytest.mark.integration
    def test_full_pipeline_creates_lineups(self, db_session, lineup_test_payload):
        """Game creation with lineup flag creates lineup segments and stats."""
        from core.models import Lineup, LineupSegment, PlayerLineupStats, GameEvent
        from core.services.game_service import create_game_from_live_data

        game = create_game_from_live_data(lineup_test_payload)

        # Verify game created
        assert game is not None
        assert game.opponent == "Lineup API Test Team"

        # Verify lineup segments created
        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert len(segments) >= 1, "At least one lineup segment should be created"

        # Verify first segment has correct starters
        first_segment = segments[0]
        assert "Alice" in first_segment.players
        assert "Bob" in first_segment.players
        assert "Carol" in first_segment.players
        assert "Dave" in first_segment.players
        assert "Eve" in first_segment.players

        # Verify events are linked to segments
        linked_events = GameEvent.query.filter(
            GameEvent.game_id == game.id, GameEvent.lineup_segment_id.isnot(None)
        ).all()
        assert len(linked_events) > 0, "Events should be linked to lineup segments"

        # Verify player lineup stats created
        player_stats = PlayerLineupStats.query.filter(
            PlayerLineupStats.lineup_segment_id.in_([s.id for s in segments])
        ).all()
        assert len(player_stats) > 0, "Player lineup stats should be created"

        # Verify Lineup records created (aggregated)
        lineups = Lineup.query.filter(
            Lineup.id.in_([s.lineup_id for s in segments if s.lineup_id])
        ).all()
        assert len(lineups) >= 1, "Lineup records should be created"

    @pytest.mark.integration
    def test_stat_aggregation_in_lineups(self, db_session, lineup_test_payload):
        """Player stats are correctly aggregated in lineup segments."""
        from core.models import PlayerLineupStats
        from core.services.game_service import create_game_from_live_data

        game = create_game_from_live_data(lineup_test_payload)

        # Find Alice's stats in first segment
        segments = (
            LineupSegment.query.filter_by(game_id=game.id)
            .order_by(LineupSegment.start_timestamp)
            .all()
        )
        first_segment = segments[0]

        alice_stats = PlayerLineupStats.query.filter_by(
            lineup_segment_id=first_segment.id, player_name="Alice"
        ).first()

        assert alice_stats is not None
        # Alice made a shot (2pts), had a block
        assert alice_stats.points >= 2
        assert alice_stats.blk >= 1

    @pytest.mark.integration
    def test_lineup_hash_consistency(self, db_session, lineup_test_payload):
        """Same player combinations share the same Lineup record."""
        from core.models import Lineup, LineupSegment
        from core.services.game_service import create_game_from_live_data
        from core.services.lineup_service import generate_lineup_hash

        game = create_game_from_live_data(lineup_test_payload)

        segments = LineupSegment.query.filter_by(game_id=game.id).all()

        # Group segments by lineup_hash
        hash_groups = {}
        for segment in segments:
            h = segment.lineup_hash
            if h not in hash_groups:
                hash_groups[h] = []
            hash_groups[h].append(segment)

        # Each unique hash should have consistent players
        for h, segs in hash_groups.items():
            players_set = set(segs[0].players)
            for seg in segs[1:]:
                assert set(seg.players) == players_set, (
                    "Same hash should mean same players"
                )

    @pytest.mark.integration
    def test_does_not_process_on_sub_events_alone(self, db_session):
        """Lineups NOT processed based solely on sub events (non-retroactive)."""
        from core.services.game_service import create_game_from_live_data

        data = {
            "schema_version": 1,
            "features": {"LINEUP_TRACKING": False},
            "date": "2024-02-19",
            "opponent": "Test Team 4",
            "team_score": 70,
            "opponent_score": 68,
            "game_type": "Season",
            "game_events": [
                {
                    "type": "SUB_IN",
                    "player": "Starter1",
                    "timestamp": 0,
                    "quarter": 1,
                },
                {
                    "type": "SUB_IN",
                    "player": "Starter2",
                    "timestamp": 1,
                    "quarter": 1,
                },
                {
                    "type": "SUB_IN",
                    "player": "Starter3",
                    "timestamp": 2,
                    "quarter": 1,
                },
                {
                    "type": "SUB_IN",
                    "player": "Starter4",
                    "timestamp": 3,
                    "quarter": 1,
                },
                {
                    "type": "SUB_IN",
                    "player": "Starter5",
                    "timestamp": 4,
                    "quarter": 1,
                },
                {
                    "type": "SHOT_2PT",
                    "player": "Starter1",
                    "timestamp": 100,
                    "quarter": 1,
                },
            ],
        }

        game = create_game_from_live_data(data)

        segments = LineupSegment.query.filter_by(game_id=game.id).all()
        assert segments == []
