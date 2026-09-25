
import hashlib
import pytest
import basketball_stats as rust

def test_rust_classify_shot_zone():
    # FT
    assert rust.classify_shot_zone(250, 190, "ft") == "FT"

    # Rim (near 250, 50)
    assert rust.classify_shot_zone(250, 60, "2pt") == "Rim"

    # Paint (near 250, 50 but further)
    assert rust.classify_shot_zone(250, 120, "2pt") == "Paint"

    # Corner 3 (y < 140 and type 3pt)
    assert rust.classify_shot_zone(30, 50, "3pt") == "Corner_3"

    # Above Break 3 (y >= 140 and type 3pt)
    assert rust.classify_shot_zone(250, 300, "3pt") == "Above_Break_3"

    # None / empty shot_type is Midrange (no TypeError)
    assert rust.classify_shot_zone(250, 60, None) == "Midrange"
    assert rust.classify_shot_zone(None, None, "2pt") == "Midrange"

def test_rust_lineup_hash_matches_md5():
    h = rust.calculate_lineup_hash(["C", "A", "B"])
    assert h == hashlib.md5("A,B,C".encode()).hexdigest()

def test_rust_combinatorial_totals_and_duration():
    segments = [
        {"players": ["A", "B", "C"], "points_scored": 10, "points_allowed": 5,
         "possessions": 10.0, "reb_conceded": 1, "duration_seconds": 300},
        {"players": ["A", "D", "E"], "points_scored": 5, "points_allowed": 10,
         "possessions": 10.0, "reb_conceded": 2, "duration_seconds": 200},
    ]
    res = rust.aggregate_combinatorial_stats(segments)
    assert res["totals"]["points_scored"] == 15
    assert res["totals"]["duration_seconds"] == 500
    assert res["totals"]["reb_conceded"] == 3
    ab = res["duos"]["A,B"]
    assert ab["duration_seconds"] == 300

def test_rust_batch_apis():
    shots = [
        {"points": 2, "x_loc": 250, "y_loc": 60, "shot_type": "2pt"},
        {"points": 0, "x_loc": None, "y_loc": None, "shot_type": None},
    ]
    zones = rust.classify_shot_zones_batch(shots)
    assert zones == ["Rim", "Midrange"]

    poss = rust.calculate_possessions_batch([[10, 5, 3, 2]])
    assert poss == pytest.approx([11.2])

    clutch = rust.batch_is_clutch([[3, 120], [10, 120], [3, 400]])
    assert clutch == [True, False, False]

    details = rust.parse_details_batch(['{"a": 1}', None, {"b": 2}, "nope"])
    assert details == [{"a": 1}, {}, {"b": 2}, {}]

    hexbins = rust.aggregate_hexbins(
        [{"x_loc": 100, "y_loc": 100, "points": 2, "result": "made"}], 50.0)
    assert hexbins[0]["attempts"] == 1 and hexbins[0]["makes"] == 1

def test_rust_safe_percentage_float():
    assert rust.safe_percentage(1.5, 3.0) == pytest.approx(50.0)
    assert rust.safe_percentage(1.0, 0.0) == 0.0

def test_rust_calculate_impact_metrics():
    segments = [
        {
            "players": ["A", "B", "C", "D", "E"],
            "points_scored": 10,
            "points_allowed": 5,
            "possessions": 10.0,
            "reb_conceded": 0,
            "duration_seconds": 300
        },
        {
            "players": ["A", "F", "G", "H", "I"],
            "points_scored": 5,
            "points_allowed": 10,
            "possessions": 10.0,
            "reb_conceded": 0,
            "duration_seconds": 300
        }
    ]

    results = rust.calculate_impact_metrics(segments, "duo", 0.0)
    
    assert len(results) > 0
    # Find duo ["A", "B"]
    duo_ab = next((r for r in results if set(r["players"]) == {"A", "B"}), None)
    assert duo_ab is not None
    assert duo_ab["on"]["ortg"] == 100.0
    assert duo_ab["on"]["drtg"] == 50.0
    assert duo_ab["on"]["net"] == 50.0
    
    # Total possessions = 20. Total pts = 15. Allowed = 15.
    # For A+B ON: poss=10, pts=10, allowed=5.
    # For A+B OFF: poss=10, pts=5, allowed=10.
    # OFF ORtg = 5/10*100 = 50.0. OFF DRtg = 10/10*100 = 100.0. OFF Net = -50.0.
    # Net Delta = 50 - (-50) = 100.0.
    
    assert duo_ab["off"]["ortg"] == 50.0
    assert duo_ab["impact"]["net_differential"] == 100.0

def test_rust_calculate_shot_heatmap():
    shots = [
        {"points": 2, "x_loc": 250, "y_loc": 60, "shot_type": "2pt"}, # Rim Make
        {"points": 0, "x_loc": 250, "y_loc": 60, "shot_type": "2pt"}, # Rim Miss
        {"points": 3, "x_loc": 30, "y_loc": 50, "shot_type": "3pt"},  # Corner 3 Make
    ]
    
    results = rust.calculate_shot_heatmap(shots)
    
    # Results is a list of entries
    rim = next((r for r in results if r["zone"] == "Rim"), None)
    assert rim is not None
    assert rim["attempts"] == 2
    assert rim["makes"] == 1
    assert rim["fg_pct"] == 50.0
    assert rim["pps"] == 1.0
    
    c3 = next((r for r in results if r["zone"] == "Corner_3"), None)
    assert c3 is not None
    assert c3["attempts"] == 1
    assert c3["makes"] == 1
    assert c3["fg_pct"] == 100.0
    assert c3["pps"] == 3.0

def test_wrapper_normalizes_ragged_segments():
    """Wrapper must complete ragged segment dicts before the typed bridge."""
    from core import rust_analytics as ra

    segments = [
        {"players": '["A", "B"]', "points_scored": 6, "points_allowed": 4,
         "possessions": 5.0},  # missing reb_conceded/duration_seconds
        {"players": ["A", "B"], "points_scored": 4, "points_allowed": 6,
         "possessions": 5.0, "reb_conceded": None, "duration_seconds": None},
    ]
    res = ra.aggregate_combinatorial_stats(segments)
    assert res["totals"]["points_scored"] == 10
    assert res["duos"]["A,B"]["possessions"] == pytest.approx(10.0)

    impact = ra.calculate_impact_metrics(segments, "duos", 0.0)
    assert impact and impact[0]["players"] == ["A", "B"]

def test_typed_reconstruct_and_game_flow():
    from core import rust_analytics as ra

    events = [
        {"id": 1, "event_type": "SHOT_2PT", "timestamp": 100.0,
         "quarter": 1, "shot_attempt": "made"},
        {"id": 2, "event_type": "TURNOVER", "timestamp": 200.0,
         "quarter": None, "shot_attempt": None},
    ]
    poss = ra.reconstruct_possessions(events)
    assert poss[0]["points"] == 2
    assert poss[0]["events"] == [1]
    assert poss[0]["quarter"] == 1

    flow = ra.calculate_game_flow([
        {"team_score": 2, "opp_score": 0, "label": "Q1"},
        {"team_score": 0, "opp_score": 3},
    ])
    assert flow[0]["margin"] == 2 and flow[0]["label"] == "Q1"
    assert flow[1]["running_team_score"] == 2
    assert flow[1]["running_opp_score"] == 3
    assert flow[1]["margin"] == -1
