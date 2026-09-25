//! Basketball Stats Rust Implementation - High-performance analytics library
//! 
//! This module contains compute-intensive functions migrated from Python
//! to provide significant performance improvements (10-30x faster).

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::{PyAny, PyDict, PyList};
use serde::{Deserialize, Serialize};
use rustc_hash::FxHashMap;
use std::collections::HashMap;
use itertools::Itertools;
use rayon::prelude::*;

/// Default expected values for shot zones (can be customized)
const DEFAULT_ZONE_VALUES: &[(&str, f64); 6] = &[
    ("Rim", 1.20),
    ("Paint", 0.85),
    ("Midrange", 0.75),
    ("Corner_3", 1.10),
    ("Above_Break_3", 1.05),
    ("FT", 0.75),
];

/// Shot data structure for Python interop.
///
/// Extracted directly from Python dicts via FromPyObject (no JSON bridge).
/// The Python wrapper normalizes payloads so every key is present; only
/// nullability varies, hence Option types (None -> sensible default).
#[derive(Debug, Clone, Serialize, Deserialize, FromPyObject)]
#[pyo3(from_item_all)]
pub struct ShotData {
    #[serde(default)]
    pub points: i32,
    #[serde(default)]
    pub x_loc: Option<f64>,
    #[serde(default)]
    pub y_loc: Option<f64>,
    #[serde(default)]
    pub shot_type: Option<String>,
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
    pub zone_breakdown: HashMap<String, ZoneStats>,
}

/// Lineup segment for aggregation
#[derive(Debug, Clone, Serialize, Deserialize, FromPyObject)]
#[pyo3(from_item_all)]
pub struct LineupSegmentData {
    pub players: Vec<String>,
    pub points_scored: i32,
    pub points_allowed: i32,
    pub possessions: f64,
    #[serde(default)]
    pub reb_conceded: Option<i32>,
    #[serde(default)]
    pub duration_seconds: i32,
}

/// Aggregated stats for a player combination
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AggregatedStats {
    pub segments: i32,
    pub points_scored: i32,
    pub points_allowed: i32,
    pub possessions: f64,
    pub reb_conceded: i32,
    #[serde(default)]
    pub duration_seconds: i32,
}

/// Totals across all segments (grand totals for on/off math)
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SegmentTotals {
    pub segments: i32,
    pub points_scored: i32,
    pub points_allowed: i32,
    pub possessions: f64,
    pub reb_conceded: i32,
    pub duration_seconds: i32,
}

/// Game event for possession reconstruction
#[derive(Debug, Clone, Serialize, Deserialize, FromPyObject)]
#[pyo3(from_item_all)]
pub struct GameEventData {
    pub id: i32,
    pub event_type: String,
    pub timestamp: f64,
    #[serde(default)]
    pub quarter: Option<i32>,
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

/// Per-zone heatmap output row
#[derive(Debug, Clone)]
pub struct HeatmapEntry {
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

/// Per-hexbin aggregation output row
#[derive(Debug, Clone)]
pub struct HexBin {
    x: i32,
    y: i32,
    attempts: i32,
    makes: i32,
    fg_pct: f64,
    points: i32,
}

/// Combined duo/trio aggregation output
#[derive(Debug, Clone)]
pub struct CombinedResult {
    pub duos: HashMap<String, AggregatedStats>,
    pub trios: HashMap<String, AggregatedStats>,
    pub totals: SegmentTotals,
}

/// Per-combination ON/OFF impact output
#[derive(Debug, Clone)]
pub struct ImpactResult {
    pub players: Vec<String>,
    pub on: HashMap<String, f64>,
    pub off: HashMap<String, f64>,
    pub impact: HashMap<String, f64>,
    pub segments: i32,
}

/// Convert output structs into Python dicts (pyo3 0.22 has no output
/// derive macro, so conversion is explicit). Shapes match the old
/// JSON-bridge outputs key-for-key.
fn zone_stats_to_py(py: Python<'_>, z: &ZoneStats) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("makes", z.makes)?;
    d.set_item("attempts", z.attempts)?;
    d.set_item("points", z.points)?;
    d.set_item("expected", z.expected)?;
    Ok(d.to_object(py))
}

fn str_map_to_py(py: Python<'_>, m: &HashMap<String, f64>) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    for (k, v) in m {
        d.set_item(k.as_str(), *v)?;
    }
    Ok(d.to_object(py))
}

fn aggregated_stats_to_py(py: Python<'_>, s: &AggregatedStats) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("segments", s.segments)?;
    d.set_item("points_scored", s.points_scored)?;
    d.set_item("points_allowed", s.points_allowed)?;
    d.set_item("possessions", s.possessions)?;
    d.set_item("reb_conceded", s.reb_conceded)?;
    d.set_item("duration_seconds", s.duration_seconds)?;
    Ok(d.to_object(py))
}

fn segment_totals_to_py(py: Python<'_>, t: &SegmentTotals) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("segments", t.segments)?;
    d.set_item("points_scored", t.points_scored)?;
    d.set_item("points_allowed", t.points_allowed)?;
    d.set_item("possessions", t.possessions)?;
    d.set_item("reb_conceded", t.reb_conceded)?;
    d.set_item("duration_seconds", t.duration_seconds)?;
    Ok(d.to_object(py))
}

fn possession_to_py(py: Python<'_>, p: &PossessionResult) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("start_event_id", p.start_event_id)?;
    d.set_item("end_event_id", p.end_event_id)?;
    d.set_item("team_possession", p.team_possession)?;
    d.set_item("quarter", p.quarter)?;
    d.set_item("points", p.points)?;
    d.set_item("events", p.events.clone())?;
    Ok(d.to_object(py))
}

fn heatmap_entry_to_py(py: Python<'_>, e: &HeatmapEntry) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("zone", e.zone.clone())?;
    d.set_item("makes", e.makes)?;
    d.set_item("attempts", e.attempts)?;
    d.set_item("frequency", e.frequency)?;
    d.set_item("fg_pct", e.fg_pct)?;
    d.set_item("pps", e.pps)?;
    d.set_item("actual_pps", e.actual_pps)?;
    d.set_item("expected_value", e.expected_value)?;
    d.set_item("efficiency_delta", e.efficiency_delta)?;
    Ok(d.to_object(py))
}

fn hexbin_to_py(py: Python<'_>, h: &HexBin) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("x", h.x)?;
    d.set_item("y", h.y)?;
    d.set_item("attempts", h.attempts)?;
    d.set_item("makes", h.makes)?;
    d.set_item("fg_pct", h.fg_pct)?;
    d.set_item("points", h.points)?;
    Ok(d.to_object(py))
}

fn shot_quality_to_py(py: Python<'_>, r: &ShotQualityResult) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("total_shots", r.total_shots)?;
    d.set_item("total_points", r.total_points)?;
    d.set_item("expected_points", r.expected_points)?;
    d.set_item("shot_quality_delta", r.shot_quality_delta)?;
    d.set_item("ppps", r.ppps)?;
    let zb = PyDict::new_bound(py);
    for (zone, stats) in &r.zone_breakdown {
        zb.set_item(zone.as_str(), zone_stats_to_py(py, stats)?)?;
    }
    d.set_item("zone_breakdown", zb)?;
    Ok(d.to_object(py))
}

fn combined_result_to_py(py: Python<'_>, r: &CombinedResult) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    let duos = PyDict::new_bound(py);
    for (k, v) in &r.duos {
        duos.set_item(k.as_str(), aggregated_stats_to_py(py, v)?)?;
    }
    let trios = PyDict::new_bound(py);
    for (k, v) in &r.trios {
        trios.set_item(k.as_str(), aggregated_stats_to_py(py, v)?)?;
    }
    d.set_item("duos", duos)?;
    d.set_item("trios", trios)?;
    d.set_item("totals", segment_totals_to_py(py, &r.totals)?)?;
    Ok(d.to_object(py))
}

fn impact_result_to_py(py: Python<'_>, r: &ImpactResult) -> PyResult<PyObject> {
    let d = PyDict::new_bound(py);
    d.set_item("players", r.players.clone())?;
    d.set_item("on", str_map_to_py(py, &r.on)?)?;
    d.set_item("off", str_map_to_py(py, &r.off)?)?;
    d.set_item("impact", str_map_to_py(py, &r.impact)?)?;
    d.set_item("segments", r.segments)?;
    Ok(d.to_object(py))
}

/// Shot payload for hexbin aggregation
#[derive(Debug, Clone, Deserialize, FromPyObject)]
#[pyo3(from_item_all)]
pub struct HexShot {
    #[serde(default)]
    pub x_loc: Option<f64>,
    #[serde(default)]
    pub y_loc: Option<f64>,
    #[serde(default)]
    pub points: i32,
    #[serde(default)]
    pub result: Option<String>,
}

/// Normalize combination type: accepts "duo", "duos", "trio", "trios" (case-insensitive).
fn normalize_combo_is_trio(combination_type: &str) -> bool {
    let t = combination_type.trim().to_lowercase();
    let t = t.strip_suffix('s').unwrap_or(&t);
    t == "trio"
}

fn classify_zone_inner(x_loc: Option<f64>, y_loc: Option<f64>, shot_type: Option<&str>) -> String {
    let st_owned: String = shot_type.unwrap_or("").to_lowercase();

    if st_owned.is_empty() {
        return "Midrange".to_string();
    }

    if st_owned == "ft" {
        return "FT".to_string();
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
    } else if st_owned.contains("3pt") {
        if y < 140.0 {
            "Corner_3".to_string()
        } else {
            "Above_Break_3".to_string()
        }
    } else {
        "Midrange".to_string()
    }
}

/// Classify a shot into a zone based on court coordinates
#[pyfunction]
#[pyo3(signature = (x_loc, y_loc, shot_type))]
pub fn classify_shot_zone(x_loc: Option<f64>, y_loc: Option<f64>, shot_type: Option<&str>) -> String {
    classify_zone_inner(x_loc, y_loc, shot_type)
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

/// Calculate comprehensive shot quality metrics for a player.
/// Takes Python dicts directly (no JSON bridge).
#[pyfunction]
pub fn calculate_shot_quality_score(py: Python<'_>, shots: Vec<ShotData>) -> PyResult<PyObject> {
    if shots.is_empty() {
        return shot_quality_to_py(py, &ShotQualityResult {
            total_shots: 0,
            total_points: 0,
            expected_points: 0.0,
            shot_quality_delta: 0.0,
            ppps: 0.0,
            zone_breakdown: HashMap::new(),
        });
    }

    let mut total_points = 0;
    let mut total_expected = 0.0;
    let mut zone_stats: FxHashMap<String, ZoneStats> = FxHashMap::default();

    // Parallel zone classification (rayon), serial aggregation (FxHashMap is !Sync).
    let zones: Vec<String> = shots
        .par_iter()
        .map(|s| classify_zone_inner(s.x_loc, s.y_loc, s.shot_type.as_deref()))
        .collect();

    for (shot, zone) in shots.iter().zip(zones.iter()) {
        total_points += shot.points;

        let expected = get_expected_value(zone);
        total_expected += expected;

        let entry = zone_stats.entry(zone.clone()).or_insert(ZoneStats {
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

    shot_quality_to_py(py, &ShotQualityResult {
        total_shots: shots.len() as i32,
        total_points,
        expected_points: (total_expected * 100.0).round() / 100.0,
        shot_quality_delta: ((total_points as f64 - total_expected) * 100.0).round() / 100.0,
        ppps: (total_points as f64 / shots.len() as f64 * 100.0).round() / 100.0,
        zone_breakdown: zone_stats.into_iter().collect(),
    })
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

/// Safe percentage helper (float-tolerant; Rust fast path for hot loops)
#[pyfunction]
pub fn safe_percentage(numerator: f64, denominator: f64) -> f64 {
    if denominator == 0.0 {
        0.0
    } else {
        numerator / denominator * 100.0
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

/// Lenient int coercion mirroring the Python fallback's `int(x or 0)`.
fn py_int(value: Option<Bound<'_, PyAny>>) -> i32 {
    match value {
        None => 0,
        Some(o) => {
            if o.is_none() {
                0
            } else if let Ok(n) = o.extract::<i64>() {
                n as i32
            } else if let Ok(f) = o.extract::<f64>() {
                f as i32
            } else if let Ok(s) = o.extract::<String>() {
                s.trim().parse().unwrap_or(0)
            } else {
                0
            }
        }
    }
}

/// Calculate game flow data points (typed: avoids Value clone per row)
#[pyfunction]
pub fn calculate_game_flow(py: Python<'_>, scores: Vec<Bound<'_, PyAny>>) -> PyResult<Vec<PyObject>> {
    let mut result: Vec<PyObject> = Vec::with_capacity(scores.len());
    let (mut running_team, mut running_opp) = (0i32, 0i32);

    for sp in &scores {
        let base = sp.downcast::<PyDict>().map_err(|_| {
            PyValueError::new_err("game_flow entries must be dicts")
        })?;
        running_team += py_int(base.get_item("team_score")?);
        running_opp += py_int(base.get_item("opp_score")?);

        let out = PyDict::new_bound(py);
        for (k, v) in base.iter() {
            out.set_item(k, v)?;
        }
        out.set_item("running_team_score", running_team)?;
        out.set_item("running_opp_score", running_opp)?;
        out.set_item("margin", running_team - running_opp)?;
        result.push(out.to_object(py));
    }

    Ok(result)
}

/// Aggregate Duo and Trio compatibility stats in a single high-performance pass.
/// Takes Python dicts directly (no JSON bridge); the Python wrapper
/// normalizes payloads so every key is present.
#[pyfunction]
pub fn aggregate_combinatorial_stats(py: Python<'_>, segments: Vec<LineupSegmentData>) -> PyResult<PyObject> {
    let mut duo_stats: HashMap<String, AggregatedStats> = HashMap::new();
    let mut trio_stats: HashMap<String, AggregatedStats> = HashMap::new();
    let mut totals = SegmentTotals::default();

    for segment in &segments {
        totals.segments += 1;
        totals.points_scored += segment.points_scored;
        totals.points_allowed += segment.points_allowed;
        totals.possessions += segment.possessions;
        totals.reb_conceded += segment.reb_conceded.unwrap_or(0);
        totals.duration_seconds += segment.duration_seconds;

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
            entry.duration_seconds += segment.duration_seconds;
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
                entry.duration_seconds += segment.duration_seconds;
            }
        }
    }

    combined_result_to_py(py, &CombinedResult {
        duos: duo_stats,
        trios: trio_stats,
        totals,
    })
}

/// High-performance possession reconstruction from game events.
/// Takes Python dicts directly (no JSON bridge).
#[pyfunction]
pub fn reconstruct_possessions_rust(py: Python<'_>, events: Vec<GameEventData>) -> PyResult<PyObject> {
    if events.is_empty() { return Ok(PyList::empty_bound(py).to_object(py)); }
    
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
                quarter: event.quarter.or(Some(0)),
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
                    quarter: event.quarter.or(Some(0)),
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

    let items: PyResult<Vec<PyObject>> = possessions
        .iter()
        .map(|p| possession_to_py(py, p))
        .collect();
    Ok(items?.to_object(py))
}

/// Calculate detailed ON/OFF impact metrics for combinations.
/// Takes Python dicts directly (no JSON bridge).
#[pyfunction]
pub fn calculate_impact_metrics(py: Python<'_>, segments: Vec<LineupSegmentData>, combination_type: &str, min_possessions: f64) -> PyResult<PyObject> {
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
    let mut combo_stats: HashMap<String, AggregatedStats> = HashMap::new();
    let is_trio = normalize_combo_is_trio(combination_type);
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
            entry.duration_seconds += s.duration_seconds;
        }
    }

    // 3. Calculate Metrics and Deltas
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
            on: HashMap::from_iter([
                ("ortg".to_string(), (on_ortg * 10.0).round() / 10.0),
                ("drtg".to_string(), (on_drtg * 10.0).round() / 10.0),
                ("net".to_string(), (on_net * 10.0).round() / 10.0),
                ("possessions".to_string(), (stats.possessions * 10.0).round() / 10.0),
                ("minutes".to_string(), (stats.duration_seconds as f64 / 60.0 * 10.0).round() / 10.0),
                ("reb_conceded".to_string(), stats.reb_conceded as f64),
            ]),
            off: HashMap::from_iter([
                ("ortg".to_string(), (off_ortg * 10.0).round() / 10.0),
                ("drtg".to_string(), (off_drtg * 10.0).round() / 10.0),
                ("net".to_string(), (off_net * 10.0).round() / 10.0),
                ("reb_conceded".to_string(), off_reb_conceded as f64),
            ]),
            impact: HashMap::from_iter([
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

    let items: PyResult<Vec<PyObject>> = results
        .iter()
        .map(|r| impact_result_to_py(py, r))
        .collect();
    Ok(items?.to_object(py))
}

/// Calculate Shot Heatmap stats.
/// Takes Python dicts directly (no JSON bridge).
#[pyfunction]
pub fn calculate_shot_heatmap(py: Python<'_>, shots: Vec<ShotData>) -> PyResult<PyObject> {
    // Parallel zone classification, serial aggregation.
    let zones: Vec<String> = shots
        .par_iter()
        .map(|s| classify_zone_inner(s.x_loc, s.y_loc, s.shot_type.as_deref()))
        .collect();

    let mut zone_stats: FxHashMap<String, ZoneStats> = FxHashMap::default();
    let total_attempts = shots.len() as i32;

    for (shot, zone) in shots.iter().zip(zones) {
        let expected = get_expected_value(&zone);

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

    let items: PyResult<Vec<PyObject>> = results
        .iter()
        .map(|e| heatmap_entry_to_py(py, e))
        .collect();
    Ok(items?.to_object(py))
}

/// Enhanced possession tracking with point attribution.
/// Currently an alias for reconstruct_possessions_rust (kept for compat).
#[pyfunction]
pub fn enhance_possession_tracking(py: Python<'_>, events: Vec<GameEventData>) -> PyResult<PyObject> {
    reconstruct_possessions_rust(py, events)
}

/// Calculate a stable lineup hash (md5 of sorted comma-joined names).
/// Matches Python hashlib.md5(",".join(sorted(players))) hexdigest.
#[pyfunction]
pub fn calculate_lineup_hash(players: Vec<String>) -> String {
    let mut sorted_players = players;
    sorted_players.sort();
    let combined = sorted_players.join(",");
    format!("{:x}", md5::compute(combined.as_bytes()))
}

/// Batch classify shot zones in one PyO3 crossing.
/// Input: list of ShotData dicts. Output: list of zone strings.
/// (Scalar classify_shot_zone in a loop is faster for trivial predicates;
/// this stays for API compatibility and mid-size payloads.)
#[pyfunction]
pub fn classify_shot_zones_batch(shots: Vec<ShotData>) -> Vec<String> {
    shots
        .par_iter()
        .map(|s| classify_zone_inner(s.x_loc, s.y_loc, s.shot_type.as_deref()))
        .collect()
}

/// Batch possessions: input list of [fga, fta, oreb, tov], output list of floats.
#[pyfunction]
pub fn calculate_possessions_batch(entries: Vec<[f64; 4]>) -> Vec<f64> {
    entries
        .par_iter()
        .map(|e| e[0] + e[1] * 0.44 - e[2] + e[3])
        .collect()
}

/// Batch parse "MM:SS" (or plain seconds) values in one crossing.
/// Input: list of str | int | float | None (anything else -> 0).
/// Output: list of ints.
#[pyfunction]
pub fn parse_times_batch(times: Vec<Bound<'_, PyAny>>) -> Vec<i32> {
    times.iter().map(|t| parse_time_value(Some(t.clone()))).collect()
}

/// Parse one time value (shared by the batch parser).
fn parse_time_value(t: Option<Bound<'_, PyAny>>) -> i32 {
    match t {
        None => 0,
        Some(o) => {
            if o.is_none() {
                0
            } else if let Ok(n) = o.extract::<i64>() {
                n as i32
            } else if let Ok(f) = o.extract::<f64>() {
                f as i32
            } else if let Ok(s) = o.extract::<String>() {
                if let Some(colon) = s.find(':') {
                    let m: i32 = s[..colon].trim().parse().unwrap_or(0);
                    let sec: i32 = s[colon + 1..].trim().parse().unwrap_or(0);
                    m * 60 + sec
                } else if s.trim().is_empty() {
                    0
                } else {
                    s.trim().parse().unwrap_or(0)
                }
            } else {
                0
            }
        }
    }
}

/// Batch clutch check: input list of [margin, seconds_remaining] (lists or
/// tuples of length 2), output list of bools.
#[pyfunction]
pub fn batch_is_clutch(entries: Vec<[i32; 2]>) -> Vec<bool> {
    entries
        .par_iter()
        .map(|e| e[0].abs() <= 5 && e[1] <= 300)
        .collect()
}

/// Convert a serde_json Value into the equivalent Python object.
fn json_value_to_py(py: Python<'_>, v: &serde_json::Value) -> PyResult<PyObject> {
    match v {
        serde_json::Value::Null => Ok(py.None()),
        serde_json::Value::Bool(b) => Ok(b.to_object(py)),
        serde_json::Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Ok(i.to_object(py))
            } else if let Some(u) = n.as_u64() {
                Ok(u.to_object(py))
            } else {
                Ok(n.as_f64().unwrap_or(0.0).to_object(py))
            }
        }
        serde_json::Value::String(s) => Ok(s.to_object(py)),
        serde_json::Value::Array(items) => {
            let list = PyList::empty_bound(py);
            for item in items {
                list.append(json_value_to_py(py, item)?)?;
            }
            Ok(list.to_object(py))
        }
        serde_json::Value::Object(map) => {
            let dict = PyDict::new_bound(py);
            for (k, val) in map {
                dict.set_item(k, json_value_to_py(py, val)?)?;
            }
            Ok(dict.to_object(py))
        }
    }
}

/// Batch parse event detail blobs (JSON strings, dicts, or null) into dicts.
/// Rust serde_json is far faster than Python json.loads + ast.literal_eval per event.
#[pyfunction]
pub fn parse_details_batch(py: Python<'_>, details: Vec<Bound<'_, PyAny>>) -> PyResult<Vec<PyObject>> {
    let mut out: Vec<PyObject> = Vec::with_capacity(details.len());
    for d in &details {
        if d.is_none() {
            out.push(PyDict::new_bound(py).to_object(py));
        } else if let Ok(dict) = d.downcast::<PyDict>() {
            out.push(dict.clone().to_object(py));
        } else if let Ok(s) = d.extract::<String>() {
            if s.is_empty() {
                out.push(PyDict::new_bound(py).to_object(py));
            } else if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&s) {
                if parsed.is_object() {
                    out.push(json_value_to_py(py, &parsed)?);
                } else {
                    out.push(PyDict::new_bound(py).to_object(py));
                }
            } else {
                out.push(PyDict::new_bound(py).to_object(py));
            }
        } else {
            out.push(PyDict::new_bound(py).to_object(py));
        }
    }
    Ok(out)
}

/// Hexbin aggregation for shot charts in one crossing.
/// Input: list of {x_loc, y_loc, points, result} dicts, hex_size float.
/// Output: list of {x, y, attempts, makes, fg_pct, points} dicts.
#[pyfunction]
pub fn aggregate_hexbins(py: Python<'_>, shots: Vec<HexShot>, hex_size: f64) -> PyResult<PyObject> {
    let hs = if hex_size > 0.0 { hex_size } else { 50.0 };
    let half = (hs / 2.0) as i32;
    let hs_i = hs as i32;

    let mut bins: FxHashMap<(i32, i32), (i32, i32, i32)> = FxHashMap::default();
    for s in &shots {
        let (x, y) = match (s.x_loc, s.y_loc) {
            (Some(x), Some(y)) => (x, y),
            _ => continue,
        };
        let hx = (x as i32 / hs_i) * hs_i + half;
        let hy = (y as i32 / hs_i) * hs_i + half;
        let e = bins.entry((hx, hy)).or_insert((0, 0, 0));
        e.0 += 1;
        e.2 += s.points;
        if s.result.as_deref() == Some("made") {
            e.1 += 1;
        }
    }

    let mut out: Vec<HexBin> = Vec::with_capacity(bins.len());
    for ((x, y), (attempts, makes, points)) in bins {
        let fg = if attempts > 0 {
            (makes as f64 / attempts as f64 * 100.0 * 10.0).round() / 10.0
        } else {
            0.0
        };
        out.push(HexBin { x, y, attempts, makes, fg_pct: fg, points });
    }
    out.sort_by_key(|b| std::cmp::Reverse(b.attempts));
    let items: PyResult<Vec<PyObject>> = out
        .iter()
        .map(|h| hexbin_to_py(py, h))
        .collect();
    Ok(items?.to_object(py))
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
    m.add_function(wrap_pyfunction!(classify_shot_zones_batch, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_possessions_batch, m)?)?;
    m.add_function(wrap_pyfunction!(batch_is_clutch, m)?)?;
    m.add_function(wrap_pyfunction!(parse_details_batch, m)?)?;
    m.add_function(wrap_pyfunction!(parse_times_batch, m)?)?;
    m.add_function(wrap_pyfunction!(aggregate_hexbins, m)?)?;
    
    Ok(())
}
