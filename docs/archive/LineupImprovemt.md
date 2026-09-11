# Lineup Improvement Plan: Duo and Trio Analytics

## Objective
Enhance the existing Lineups interface to include sub-pages for 2-player (Duos) and 3-player (Trios) combinations. The primary metric for ranking will be the **Net Rating Differential**: the performance of the team when the combination is on the court (ON) versus when they are not (OFF).

## 1. Backend Architecture (Rust Engine)
Since calculating combinations for every segment across all games is data-intensive, we will utilize the high-performance Rust analytics engine.

### Rust Implementation (`basketball_stats_rust/src/lib.rs`)
- **Optimization**: Update `aggregate_combinatorial_stats` to track not just the combinations but also the **Total Team Stats** (Possessions, Points Scored, Points Allowed) for the games being analyzed.
- **Aggregation**: For every `LineupSegment`:
    - Aggregate stats for all $C(5, 2)$ duos and $C(5, 3)$ trios.
    - Store total game-wide stats to allow for the subtraction method: $OFF\_Stats = Total\_Stats - ON\_Stats$.
- **Efficiency**: Ensure the Rust implementation remains O(N) where N is the number of segments, using HashMaps for combinatorial lookups.

### Python Integration (`core/advanced_analytics.py`)
- **Metric Calculation**: Implement the "Net Rating Differential" logic:
    - $ON\_NetRating = (ON\_PointsScored - ON\_PointsAllowed) / ON\_Possessions * 100$
    - $OFF\_NetRating = (Total\_PointsScored - ON\_PointsScored - (Total\_PointsAllowed - ON\_PointsAllowed)) / (Total\_Possessions - ON\_Possessions) * 100$
    - $Net\_Diff = ON\_NetRating - OFF\_NetRating$
- **Filtering**:
    - Minimum possession threshold (e.g., 20 possessions) to ensure statistical significance.
    - Filter for $ON\_NetRating > OFF\_NetRating$.
    - Return only the **Top 10** results sorted by Net Rating.

## 2. API Design
Create a new endpoint: `GET /api/advanced/lineups/combinations`
- **Parameters**: `type` (duo|trio), `min_possessions`, `game_type`.
- **Response**: List of combinations including ON stats, OFF stats, and the resulting Differential.

## 3. Frontend Implementation (`web/templates/lineups.html`)
- **UI Structure**:
    - Replace the single grid with a Tabbed Interface:
        - **5-Man Lineups** (Existing)
        - **Top 10 Duos** (New)
        - **Top 10 Trios** (New)
- **Visualization**:
    - Use a simplified card view for Duos/Trios.
    - Explicitly display the "Synergy" metric (the Net Differential).
    - Provide a "Compare" view showing the combination's impact on Offensive vs Defensive rating separately.

## 4. Execution Steps
1. **Modify Rust `lib.rs`**: Include total stat aggregation in combinatorial results.
2. **Update Python Wrapper**: Expose the new total stat fields to `advanced_analytics.py`.
3. **Develop API**: Create the endpoint in `advanced_analytics_api.py`.
4. **UI Update**: Add tabs and AJAX loading for combinations in `lineups.html`.
5. **Validation**: Test with a large game set (e.g., the 10+ games in `/Games`) to ensure performance remains high.
