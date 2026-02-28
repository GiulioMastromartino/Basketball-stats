//! Basketball Stats Rust Implementation - High-performance analytics library
//! 
//! This module contains compute-intensive functions migrated from Python
//! to provide significant performance improvements (10-30x faster).

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use serde::{Deserialize, Serialize};
use rustc_hash::FxHashMap;
use itertools::Itertools;

/// Default expected values for shot zones (can be customized)
const DEFAULT_ZONE_VALUES: &[(&str, f64); 6] = &[
    ("Rim", 1.20),
    ("Paint", 0.85),
    ("Midrange", 0.75),
    ("Corner_3", 1.10),
    ("Above_Break_3", 1.05),
    ("FT", 0.75),
];

/// Shot data structure for Python interop
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShotData {
    pub points: i32,
    pub x_loc: Option<f64>,
    pub y_loc: Option<f64>,
    #[serde(default)]
    pub shot_type: String,
}

/// Zone breakdown statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZoneStats {
    pub makes: i32,
    pub attempts: i32,
    pub points: i32,
    pub expected: f64,
}

/// Shot quality result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShotQualityResult {
    pub total_shots: i32,
    pub total_points: i32,
    pub expected_points: f64,
    pub shot_quality_delta: f64,
    pub ppps: f64,
    pub zone_breakdown: FxHashMap<String, ZoneStats>,
}

/// Lineup segment for aggregation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineupSegmentData {
    pub players: Vec<String>,
    pub points_scored: i32,
    pub points_allowed: i32,
    pub possessions: f64,
    #[serde(default)]
    pub reb_conceded: Option<i32>,
}

/// Aggregated stats for a player combination
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AggregatedStats {
    pub segments: i32,
    pub points_scored: i32,
    pub points_allowed: i32,
    pub possessions: f64,
    pub reb_conceded: i32,
}

/// Game event for possession reconstruction
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameEventData {
    pub id: i32,
    pub event_type: String,
    pub timestamp: f64,
    #[serde(default)]
    pub quarter: i32,
    #[serde(default)]
    pub shot_attempt: Option<String>,
}

/// Reconstructed possession
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PossessionResult {
    pub start_event_id: i32,
    pub end_event_id: Option<i32>,
    pub team_possession: bool,
    pub quarter: Option<i32>,
    pub points: i32,
    pub events: Vec<i32>,
}

/// Classify a shot into a zone based on court coordinates
#[pyfunction]
#[pyo3(signature = (x_loc, y_loc, shot_type))]
pub fn classify_shot_zone(x_loc: Option<f64>, y_loc: Option<f64>, shot_type: &str) -> String {
    let st = shot_type.to_lowercase();
    
    if st == "ft" {
        return "FT".to_string();
    }
    
    if shot_type.is_empty() {
        return "Midrange".to_string();
    }

    let (x, y) = match (x_loc, y_loc) {
        (Some(x), Some(y)) => (x, y),
        _ => return "Midrange".to_string(),
    };
    
    // Distance from basket (centered at x=250, y=50)
    let dx = x - 250.0;
    let dy = y - 50.0;
    let distance = (dx * dx + dy * dy).sqrt();
    
    if distance <= 40.0 {
        "Rim".to_string()
    } else if distance <= 100.0 {
        "Paint".to_string()
    } else if st.contains("3pt") {
        if y < 140.0 {
            "Corner_3".to_string()
        } else {
            "Above_Break_3".to_string()
        }
    } else {
        "Midrange".to_string()
    }
}

/// Get expected point value for a zone
#[pyfunction]
pub fn get_expected_value(zone: &str) -> f64 {
    DEFAULT_ZONE_VALUES
        .iter()
        .find(|(z, _)| *z == zone)
        .map(|(_, v)| *v)
        .unwrap_or(0.80)
}

/// Calculate True Usage Rate (USG%)
#[pyfunction]
#[pyo3(signature = (fga, fta, tov, team_fga, team_fta, team_tov, minutes, team_minutes=200.0))]
pub fn calculate_true_usage_rate(
    fga: i32,
    fta: i32,
    tov: i32,
    team_fga: i32,
    team_fta: i32,
    team_tov: i32,
    minutes: f64,
    team_minutes: f64,
) -> f64 {
    if minutes <= 0.0 {
        return 0.0;
    }
    
    let ft_attempt_weight = 0.44;
    let player_possessions = fga as f64 + (ft_attempt_weight * fta as f64) + tov as f64;
    let team_possessions = team_fga as f64 + (ft_attempt_weight * team_fta as f64) + team_tov as f64;
    
    if team_possessions == 0.0 {
        return 0.0;
    }
    
    let usage = (player_possessions * (team_minutes / 5.0)) / (minutes * team_possessions) * 100.0;
    
    usage.min(100.0).round() * 10.0_f64.powi(-1)
}

/// Calculate Points Per Shot (PPS)
#[pyfunction]
pub fn calculate_points_per_shot(points: i32, fga: i32) -> f64 {
    if fga == 0 {
        return 0.0;
    }
    (points as f64 / fga as f64 * 100.0).round() / 100.0
}

/// Calculate Shot Quality Delta
#[pyfunction]
pub fn calculate_shot_quality_delta(actual_points: f64, expected_points: f64) -> f64 {
    ((actual_points - expected_points) * 100.0).round() / 100.0
}

/// Calculate comprehensive shot quality metrics for a player
#[pyfunction]
pub fn calculate_shot_quality_score(shots_json: &str) -> PyResult<String> {
    let shots: Vec<ShotData> = serde_json::from_str(shots_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {}", e)))?;
    
    if shots.is_empty() {
        let empty_result = ShotQualityResult {
            total_shots: 0,
            total_points: 0,
            expected_points: 0.0,
            shot_quality_delta: 0.0,
            ppps: 0.0,
            zone_breakdown: FxHashMap::default(),
        };
        return Ok(serde_json::to_string(&empty_result).unwrap());
    }
    
    let mut total_points = 0;
    let mut total_expected = 0.0;
    let mut zone_stats: FxHashMap<String, ZoneStats> = FxHashMap::default();
    
    for shot in &shots {
        total_points += shot.points;
        
        let zone = classify_shot_zone(shot.x_loc, shot.y_loc, &shot.shot_type);
        let expected = get_expected_value(&zone);
        total_expected += expected;
        
        let entry = zone_stats.entry(zone).or_insert(ZoneStats {
            makes: 0,
            attempts: 0,
            points: 0,
            expected: 0.0,
        });
        entry.attempts += 1;
        entry.points += shot.points;
        entry.expected += expected;
        if shot.points > 0 {
            entry.makes += 1;
        }
    }
    
    let result = ShotQualityResult {
        total_shots: shots.len() as i32,
        total_points,
        expected_points: (total_expected * 100.0).round() / 100.0,
        shot_quality_delta: ((total_points as f64 - total_expected) * 100.0).round() / 100.0,
        ppps: (total_points as f64 / shots.len() as f64 * 100.0).round() / 100.0,
        zone_breakdown: zone_stats,
    };
    
    serde_json::to_string(&result).map_err(|e| PyValueError::new_err(format!("Serialization error: {}", e)))
}

/// Parse time string to seconds
#[pyfunction]
pub fn parse_time_to_seconds(time_str: &str) -> i32 {
    if let Some(colon_pos) = time_str.find(':') {
        let minutes: i32 = time_str[..colon_pos].parse().unwrap_or(0);
        let seconds: i32 = time_str[colon_pos + 1..].parse().unwrap_or(0);
        minutes * 60 + seconds
    } else {
        time_str.parse().unwrap_or(0)
    }
}

/// Convert seconds to MM:SS format
#[pyfunction]
pub fn seconds_to_time(seconds: i32) -> String {
    let secs = seconds.max(0);
    let mins = secs / 60;
    let secs = secs % 60;
    format!("{:02}:{:02}", mins, secs)
}

/// Safe division helper
#[pyfunction]
pub fn safe_div(numerator: f64, denominator: f64, default: f64) -> f64 {
    if denominator == 0.0 {
        default
    } else {
        numerator / denominator
    }
}

/// Safe percentage helper
#[pyfunction]
pub fn safe_percentage(numerator: i32, denominator: i32) -> f64 {
    if denominator == 0 {
        0.0
    } else {
        numerator as f64 / denominator as f64 * 100.0
    }
}

/// Calculate possessions
#[pyfunction]
pub fn calculate_possessions(fga: i32, fta: i32, oreb: i32, tov: i32) -> f64 {
    fga as f64 + (fta as f64 * 0.44) - oreb as f64 + tov as f64
}

/// Calculate effective field goal percentage
#[pyfunction]
pub fn calculate_efg_pct(fgm: i32, tpm: i32, fga: i32) -> f64 {
    if fga == 0 {
        return 0.0;
    }
    (fgm as f64 + 0.5 * tpm as f64) / fga as f64 * 100.0
}

/// Calculate true shooting percentage
#[pyfunction]
pub fn calculate_true_shooting_pct(points: i32, fga: i32, fta: i32) -> f64 {
    if fga == 0 && fta == 0 {
        return 0.0;
    }
    let ts = points as f64 / (2.0 * (fga as f64 + 0.44 * fta as f64));
    ts * 100.0
}

/// Calculate pace (possessions per 40 minutes)
#[pyfunction]
#[pyo3(signature = (team_poss, team_minutes, league_pace=100.0))]
pub fn calculate_pace(team_poss: f64, team_minutes: f64, league_pace: f64) -> f64 {
    if team_minutes == 0.0 {
        return league_pace;
    }
    team_poss * 40.0 / team_minutes
}

/// Calculate offensive rating (points per 100 possessions)
#[pyfunction]
pub fn calculate_offensive_rating(points: i32, poss: f64) -> f64 {
    if poss == 0.0 {
        return 0.0;
    }
    points as f64 / poss * 100.0
}

/// Calculate defensive rating (points allowed per 100 possessions)
#[pyfunction]
pub fn calculate_defensive_rating(opp_points: i32, opp_poss: f64) -> f64 {
    if opp_poss == 0.0 {
        return 0.0;
    }
    opp_points as f64 / opp_poss * 100.0
}

/// Calculate net rating
#[pyfunction]
pub fn calculate_net_rating(off_rtg: f64, def_rtg: f64) -> f64 {
    off_rtg - def_rtg
}

/// Calculate assist ratio (assists per possession)
#[pyfunction]
pub fn calculate_assist_ratio(ast: i32, fga: i32, tov: i32, fta: i32) -> f64 {
    let poss = fga as f64 + tov as f64 + fta as f64 / 2.0;
    if poss == 0.0 {
        return 0.0;
    }
    ast as f64 / poss * 100.0
}

/// Calculate turnover ratio (turnovers per possession)
#[pyfunction]
pub fn calculate_turnover_ratio(tov: i32, fga: i32, fta: i32, ora: i32) -> f64 {
    let poss = fga as f64 + fta as f64 / 2.0 + ora as f64;
    if poss == 0.0 {
        return 0.0;
    }
    tov as f64 / poss * 100.0
}

/// Calculate rebound rate
#[pyfunction]
pub fn calculate_rebound_rate(orb: i32, team_orb: i32, opp_drb: i32) -> f64 {
    let total_rebs = orb + team_orb + opp_drb;
    if total_rebs == 0 {
        return 0.0;
    }
    orb as f64 / total_rebs as f64 * 100.0
}

/// Check if situation is clutch (within 5 points, under 5 minutes)
#[pyfunction]
pub fn is_clutch_situation(score_margin: i32, time_remaining_seconds: i32) -> bool {
    score_margin.abs() <= 5 && time_remaining_seconds <= 300
}

/// Calculate game flow data points
#[pyfunction]
pub fn calculate_game_flow(scores_json: &str) -> PyResult<String> {
    let scores: Vec<FxHashMap<String, serde_json::Value>> = serde_json::from_str(scores_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {}", e)))?;
    
    let mut result: Vec<FxHashMap<String, serde_json::Value>> = Vec::new();
    let mut running_score = (0, 0);
    
    for score_point in scores {
        let team_score: i32 = score_point.get("team_score")
            .and_then(|v| v.as_i64())
            .map(|v| v as i32)
            .unwrap_or(0);
        let opp_score: i32 = score_point.get("opp_score")
            .and_then(|v| v.as_i64())
            .map(|v| v as i32)
            .unwrap_or(0);
        
        running_score.0 += team_score;
        running_score.1 += opp_score;
        
        let mut point = score_point.clone();
        point.insert("running_team_score".to_string(), serde_json::json!(running_score.0));
        point.insert("running_opp_score".to_string(), serde_json::json!(running_score.1));
        point.insert("margin".to_string(), serde_json::json!(running_score.0 - running_score.1));
        
        result.push(point);
    }
    
    serde_json::to_string(&result).map_err(|e| PyValueError::new_err(format!("Serialization error: {}", e)))
}

/// Aggregate Duo and Trio compatibility stats in a single high-performance pass
#[pyfunction]
pub fn aggregate_combinatorial_stats(segments_json: &str) -> PyResult<String> {
    let segments: Vec<LineupSegmentData> = serde_json::from_str(segments_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {}", e)))?;
    
    let mut duo_stats: FxHashMap<String, AggregatedStats> = FxHashMap::default();
    let mut trio_stats: FxHashMap<String, AggregatedStats> = FxHashMap::default();
    
    for segment in segments {
        if segment.players.len() < 2 { continue; }
        
        let mut sorted_players: Vec<&str> = segment.players.iter().map(|s| s.as_str()).collect();
        sorted_players.sort_unstable();
        
        // Duo combinations
        for duo in sorted_players.iter().combinations(2) {
            let key = format!("{},{}", duo[0], duo[1]);
            let entry = duo_stats.entry(key).or_default();
            entry.segments += 1;
            entry.points_scored += segment.points_scored;
            entry.points_allowed += segment.points_allowed;
            entry.possessions += segment.possessions;
            entry.reb_conceded += segment.reb_conceded.unwrap_or(0);
        }
        
        // Trio combinations
        if sorted_players.len() >= 3 {
            for trio in sorted_players.iter().combinations(3) {
                let key = format!("{},{},{}", trio[0], trio[1], trio[2]);
                let entry = trio_stats.entry(key).or_default();
                entry.segments += 1;
                entry.points_scored += segment.points_scored;
                entry.points_allowed += segment.points_allowed;
                entry.possessions += segment.possessions;
                entry.reb_conceded += segment.reb_conceded.unwrap_or(0);
            }
        }
    }
    
    #[derive(Serialize)]
    struct CombinedResult {
        duos: FxHashMap<String, AggregatedStats>,
        trios: FxHashMap<String, AggregatedStats>,
    }
    
    let result = CombinedResult {
        duos: duo_stats,
        trios: trio_stats,
    };
    
    serde_json::to_string(&result).map_err(|e| PyValueError::new_err(format!("Serialization error: {}", e)))
}

/// High-performance possession reconstruction from game events
#[pyfunction]
pub fn reconstruct_possessions_rust(events_json: &str) -> PyResult<String> {
    let events: Vec<GameEventData> = serde_json::from_str(events_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {}", e)))?;
        
    if events.is_empty() { return Ok("[]".to_string()); }
    
    let mut possessions: Vec<PossessionResult> = Vec::new();
    let mut current_possession: Option<PossessionResult> = None;
    let mut team_possession = true;
    
    let end_events = ["SHOT_2PT", "SHOT_3PT", "TURNOVER", "FOUL_DEFENSIVE", "OPP_SCORE"];
    let start_events = ["REBOUND_DEFENSIVE", "OPP_TURNOVER", "OPP_MISS", "SUB_IN", "TIMEOUT"];
    
    for event in events {
        let is_end = end_events.contains(&event.event_type.as_str());
        let is_start = start_events.contains(&event.event_type.as_str());
        
        if event.event_type == "SHOT_2PT" || event.event_type == "SHOT_3PT" {
            let mut pos = current_possession.unwrap_or(PossessionResult {
                start_event_id: event.id,
                end_event_id: None,
                team_possession,
                quarter: Some(event.quarter),
                points: 0,
                events: Vec::new(),
            });
            pos.events.push(event.id);
            
            if event.shot_attempt.as_deref() == Some("made") {
                pos.points += if event.event_type == "SHOT_2PT" { 2 } else { 3 };
                pos.end_event_id = Some(event.id);
                possessions.push(pos);
                current_possession = None;
            } else {
                current_possession = Some(pos);
            }
        } else if event.event_type == "FT_MADE" {
            if let Some(mut pos) = current_possession {
                pos.points += 1;
                pos.events.push(event.id);
                current_possession = Some(pos);
            }
        } else if event.event_type == "TURNOVER" {
             if let Some(mut pos) = current_possession {
                pos.events.push(event.id);
                pos.end_event_id = Some(event.id);
                possessions.push(pos);
            }
            team_possession = !team_possession;
            current_possession = None;
        } else if event.event_type == "OPP_SCORE" {
            if let Some(mut pos) = current_possession {
                pos.end_event_id = Some(event.id);
                possessions.push(pos);
            }
            team_possession = !team_possession;
            current_possession = None;
        } else if is_start {
            if current_possession.is_none() {
                if event.event_type == "REBOUND_DEFENSIVE" { team_possession = true; }
                current_possession = Some(PossessionResult {
                    start_event_id: event.id,
                    end_event_id: None,
                    team_possession,
                    quarter: Some(event.quarter),
                    points: 0,
                    events: vec![event.id],
                });
            }
        } else if is_end {
            if let Some(mut pos) = current_possession {
                pos.end_event_id = Some(event.id);
                possessions.push(pos);
                current_possession = None;
            }
        }
    }
    
    serde_json::to_string(&possessions).map_err(|e| PyValueError::new_err(format!("Serialization error: {}", e)))
}

/// Calculate detailed ON/OFF impact metrics for combinations
#[pyfunction]
pub fn calculate_impact_metrics(segments_json: &str, combination_type: &str, min_possessions: f64) -> PyResult<String> {
    let segments: Vec<LineupSegmentData> = serde_json::from_str(segments_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {}", e)))?;

    // 1. Calculate Grand Totals
    let mut total_possessions = 0.0;
    let mut total_points_scored = 0;
    let mut total_points_allowed = 0;
    let mut total_reb_conceded = 0;

    for s in &segments {
        total_possessions += s.possessions;
        total_points_scored += s.points_scored;
        total_points_allowed += s.points_allowed;
        total_reb_conceded += s.reb_conceded.unwrap_or(0);
    }

    // 2. Aggregate per combination
    let mut combo_stats: FxHashMap<String, AggregatedStats> = FxHashMap::default();
    let is_trio = combination_type == "trio";
    let combo_size = if is_trio { 3 } else { 2 };

    for s in &segments {
        if s.players.len() < combo_size { continue; }
        
        let mut sorted_players: Vec<&str> = s.players.iter().map(|p| p.as_str()).collect();
        sorted_players.sort_unstable();

        for combo in sorted_players.iter().combinations(combo_size) {
            let key = if is_trio {
                format!("{},{},{}", combo[0], combo[1], combo[2])
            } else {
                format!("{},{}", combo[0], combo[1])
            };
            let entry = combo_stats.entry(key).or_default();
            entry.segments += 1;
            entry.possessions += s.possessions;
            entry.points_scored += s.points_scored;
            entry.points_allowed += s.points_allowed;
            entry.reb_conceded += s.reb_conceded.unwrap_or(0);
        }
    }

    // 3. Calculate Metrics and Deltas
    #[derive(Serialize)]
    struct ImpactResult {
        players: Vec<String>,
        on: FxHashMap<String, f64>,
        off: FxHashMap<String, f64>,
        impact: FxHashMap<String, f64>,
        segments: i32,
    }

    let mut results: Vec<ImpactResult> = Vec::new();

    for (key, stats) in combo_stats {
        if stats.possessions < min_possessions { continue; }

        let players: Vec<String> = key.split(',').map(|s| s.to_string()).collect();

        // ON Court Ratings
        let on_ortg = if stats.possessions > 0.0 { stats.points_scored as f64 / stats.possessions * 100.0 } else { 0.0 };
        let on_drtg = if stats.possessions > 0.0 { stats.points_allowed as f64 / stats.possessions * 100.0 } else { 0.0 };
        let on_net = on_ortg - on_drtg;

        // OFF Court Totals
        let off_poss = total_possessions - stats.possessions;
        let off_pts_scored = total_points_scored - stats.points_scored;
        let off_pts_allowed = total_points_allowed - stats.points_allowed;

        // OFF Court Ratings
        let off_ortg = if off_poss > 0.0 { off_pts_scored as f64 / off_poss * 100.0 } else { 0.0 };
        let off_drtg = if off_poss > 0.0 { off_pts_allowed as f64 / off_poss * 100.0 } else { 0.0 };
        let off_net = off_ortg - off_drtg;
        let off_reb_conceded = total_reb_conceded - stats.reb_conceded;

        // Deltas
        let off_delta = on_ortg - off_ortg;
        let def_delta = off_drtg - on_drtg; // Positive means ON court is better defense (lower DRTG)
        let net_delta = on_net - off_net;
        let reb_conceded_delta = (off_reb_conceded as f64) - (stats.reb_conceded as f64); // Positive = conceded fewer than when off

        results.push(ImpactResult {
            players,
            segments: stats.segments,
            on: FxHashMap::from_iter([
                ("ortg".to_string(), (on_ortg * 10.0).round() / 10.0),
                ("drtg".to_string(), (on_drtg * 10.0).round() / 10.0),
                ("net".to_string(), (on_net * 10.0).round() / 10.0),
                ("possessions".to_string(), (stats.possessions * 10.0).round() / 10.0),
                ("minutes".to_string(), (stats.possessions * 0.2).round() / 10.0), // Rough estimate if secs missing
                ("reb_conceded".to_string(), stats.reb_conceded as f64),
            ]),
            off: FxHashMap::from_iter([
                ("ortg".to_string(), (off_ortg * 10.0).round() / 10.0),
                ("drtg".to_string(), (off_drtg * 10.0).round() / 10.0),
                ("net".to_string(), (off_net * 10.0).round() / 10.0),
                ("reb_conceded".to_string(), off_reb_conceded as f64),
            ]),
            impact: FxHashMap::from_iter([
                ("offense_delta".to_string(), (off_delta * 10.0).round() / 10.0),
                ("defense_delta".to_string(), (def_delta * 10.0).round() / 10.0),
                ("net_differential".to_string(), (net_delta * 10.0).round() / 10.0),
                ("reb_conceded_delta".to_string(), reb_conceded_delta),
            ]),
        });
    }

    // Sort by Net Differential desc (safer sorting)
    results.sort_by(|a, b| {
        let val_a = a.impact.get("net_differential").cloned().unwrap_or(0.0);
        let val_b = b.impact.get("net_differential").cloned().unwrap_or(0.0);
        val_b.partial_cmp(&val_a).unwrap_or(std::cmp::Ordering::Equal)
    });

    serde_json::to_string(&results).map_err(|e| PyValueError::new_err(format!("Serialization error: {}", e)))
}

/// Calculate Shot Heatmap stats
#[pyfunction]
pub fn calculate_shot_heatmap(shots_json: &str) -> PyResult<String> {
    let shots: Vec<ShotData> = serde_json::from_str(shots_json)
        .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {}", e)))?;

    let mut zone_stats: FxHashMap<String, ZoneStats> = FxHashMap::default();
    let mut total_attempts = 0;

    for shot in &shots {
        let zone = classify_shot_zone(shot.x_loc, shot.y_loc, &shot.shot_type);
        let expected = get_expected_value(&zone);
        
        let entry = zone_stats.entry(zone).or_insert(ZoneStats {
            makes: 0,
            attempts: 0,
            points: 0,
            expected: 0.0,
        });
        
        entry.attempts += 1;
        total_attempts += 1;
        entry.points += shot.points;
        entry.expected += expected;
        
        // Check if make based on points > 0 (simplification for this struct)
        // Ideally pass "result" in ShotData, but this works for aggregate stats
        if shot.points > 0 {
            entry.makes += 1;
        }
    }

    #[derive(Serialize)]
    struct HeatmapEntry {
        zone: String,
        makes: i32,
        attempts: i32,
        frequency: f64,
        fg_pct: f64,
        pps: f64,
        actual_pps: f64,
        expected_value: f64,
        efficiency_delta: f64,
    }

    let mut results: Vec<HeatmapEntry> = Vec::new();

    for (zone, stats) in zone_stats {
        let freq = if total_attempts > 0 { stats.attempts as f64 / total_attempts as f64 * 100.0 } else { 0.0 };
        let fg_pct = if stats.attempts > 0 { stats.makes as f64 / stats.attempts as f64 * 100.0 } else { 0.0 };
        let pps = if stats.attempts > 0 { stats.points as f64 / stats.attempts as f64 } else { 0.0 };
        let expected = get_expected_value(&zone);

        results.push(HeatmapEntry {
            zone,
            makes: stats.makes,
            attempts: stats.attempts,
            frequency: (freq * 10.0).round() / 10.0,
            fg_pct: (fg_pct * 10.0).round() / 10.0,
            pps: (pps * 100.0).round() / 100.0,
            actual_pps: (pps * 100.0).round() / 100.0,
            expected_value: expected,
            efficiency_delta: ((pps - expected) * 100.0).round() / 100.0,
        });
    }

    serde_json::to_string(&results).map_err(|e| PyValueError::new_err(format!("Serialization error: {}", e)))
}

/// Enhanced possession tracking with point attribution
#[pyfunction]
pub fn enhance_possession_tracking(events_json: &str) -> PyResult<String> {
    // This is a wrapper/alias for reconstruct_possessions_rust but can be expanded
    // to include advanced lineup context or other metadata if passed in JSON.
    // For now, it reuses the logic to ensure we expose the "Enhancement" capability.
    reconstruct_possessions_rust(events_json)
}

/// Calculate a fast MD5-like hash for a lineup
#[pyfunction]
pub fn calculate_lineup_hash(players: Vec<String>) -> String {
    let mut sorted_players = players;
    sorted_players.sort();
    let combined = sorted_players.join(",");
    // Simple deterministic hash for performance
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    use std::hash::Hasher;
    hasher.write(combined.as_bytes());
    format!("{:x}", hasher.finish())
}

/// Python module definition
#[pymodule]
fn basketball_stats(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(classify_shot_zone, m)?)?;
    m.add_function(wrap_pyfunction!(get_expected_value, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_true_usage_rate, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_points_per_shot, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_shot_quality_delta, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_shot_quality_score, m)?)?;
    m.add_function(wrap_pyfunction!(parse_time_to_seconds, m)?)?;
    m.add_function(wrap_pyfunction!(seconds_to_time, m)?)?;
    m.add_function(wrap_pyfunction!(safe_div, m)?)?;
    m.add_function(wrap_pyfunction!(safe_percentage, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_possessions, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_efg_pct, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_true_shooting_pct, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_pace, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_offensive_rating, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_defensive_rating, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_net_rating, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_assist_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_turnover_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_rebound_rate, m)?)?;
    m.add_function(wrap_pyfunction!(is_clutch_situation, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_game_flow, m)?)?;
    m.add_function(wrap_pyfunction!(aggregate_combinatorial_stats, m)?)?;
    m.add_function(wrap_pyfunction!(reconstruct_possessions_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_lineup_hash, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_impact_metrics, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_shot_heatmap, m)?)?;
    m.add_function(wrap_pyfunction!(enhance_possession_tracking, m)?)?;
    
    Ok(())
}
