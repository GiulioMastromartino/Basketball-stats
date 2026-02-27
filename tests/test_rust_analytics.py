
import json
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

def test_rust_calculate_impact_metrics():
    segments = [
        {
            "players": ["A", "B", "C", "D", "E"],
            "points_scored": 10,
            "points_allowed": 5,
            "possessions": 10.0,
            "duration_seconds": 300
        },
        {
            "players": ["A", "F", "G", "H", "I"],
            "points_scored": 5,
            "points_allowed": 10,
            "possessions": 10.0,
            "duration_seconds": 300
        }
    ]
    
    res_json = rust.calculate_impact_metrics(json.dumps(segments), "duo", 0.0)
    results = json.loads(res_json)
    
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
    
    res_json = rust.calculate_shot_heatmap(json.dumps(shots))
    results = json.loads(res_json)
    
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
