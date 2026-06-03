# Advanced Analytics Guide

This guide covers the advanced analytics features available in Basketball Stats.

## Table of Contents

1. [Advanced Analytics Dashboard](#advanced-analytics-dashboard)
2. [Player Statistics](#player-statistics)
3. [Lineup Analytics](#lineup-analytics)
4. [Shot Charts](#shot-charts)
5. [PDF Reports](#pdf-reports)

---

## Advanced Analytics Dashboard

Access the advanced analytics dashboard at `/advanced-analytics` after logging in.

### Features

- **Shot Charts Tab**: Visualize shot locations on a basketball court
- **Lineup Tab**: Analyze 5-man lineup efficiency and duo compatibility
- **Clutch Tab**: View performance in high-pressure situations
- **Four Factors Tab**: Dean Oliver's Four Factors analysis
- **Player Stats Tab**: Advanced individual metrics

---

## Player Statistics

### True Usage Rate (USG%)

Measures the percentage of team plays used by a player while on the court.

**Formula**: `USG% = ((FGA + 0.44*FTA + TOV) * (Team Minutes / 5)) / (Minutes * Team Possessions) * 100`

**Interpretation**:
- 20%+ = High usage (primary scorer)
- 15-20% = Average usage
- <15% = Low usage (role player)

### Points Per Shot (PPS)

Simple efficiency metric measuring points scored per field goal attempt.

**Formula**: `PPS = Points / FGA`

**Interpretation**:
- 1.10+ = Excellent efficiency
- 1.00-1.10 = Good efficiency
- <1.00 = Below average

### Shot Quality Model

Assigns expected point values to different court zones:

| Zone | Expected Value |
|------|---------------|
| Rim | 1.20 pts |
| Paint (non-rim) | 0.85 pts |
| Midrange | 0.75 pts |
| Corner 3 | 1.10 pts |
| Above Break 3 | 1.05 pts |
| Free Throw | 0.75 pts |

**Shot Quality Delta** = Actual Points - Expected Points

- Positive = "Tough shot maker" (outperforming expectations)
- Negative = "Poor shot selection" (underperforming expectations)

### Clutch Performance

Stats filtered for "Crunch Time" situations:
- Score within 5 points
- Less than 5 minutes remaining

---

## Lineup Analytics

### On/Off Court Splits

Compare team performance when a player is on vs off the court:

- **ORtg**: Points scored per 100 possessions
- **DRtg**: Points allowed per 100 possessions
- **Net Rating**: ORtg - DRtg

**Net Differential** = On Court Net - Off Court Net

Positive differential indicates the player has a positive impact.

### Duo Compatibility

Shows how two-player combinations perform together:

- **Synergy Factor**: Combined net rating when both players are on court
- **Compatibility Matrix**: Color-coded grid showing positive (green) vs negative (red) pairings

### Lineup Efficiency Rankings

5-man units ranked by Net Rating with minimum possession threshold.

---

## Shot Charts

### Court Mapping

Shots are plotted using x_loc and y_loc coordinates:
- Court dimensions: 0-500 (x), 0-470 (y)
- Basket located at (250, 50)

### Visualization Types

1. **Shot Markers**: Individual makes (green) and misses (red)
2. **Hexbin Heatmap**: Grouped by zone with FG% coloring
3. **Zone Efficiency**: Aggregated stats by court zone

### Filtering

Filter shot charts by:
- Player
- Game type (Season/Friendly)
- Play type (e.g., "Pick & Roll")

---

## PDF Reports

### Visual Game Report

**Endpoint**: `/reports/games/<game_id>/visual.pdf`

Contains:
- Score Worm (lead changes throughout game)
- Quarterly Scoring Breakdown
- Four Factors Dashboard
- Top Performers
- Team Totals

### Lineup Analysis Report

**Endpoint**: `/reports/lineup/report.pdf`

Contains:
- Top 5-Man Lineups by Net Rating
- Duo Compatibility Matrix
- Top Trio Combinations

### Player Scouting Card

**Endpoint**: `/reports/player/<player_name>/scouting.pdf`

Contains:
- Primary Stats (PPG, RPG, APG, FG%)
- Advanced Metrics (USG%, PPS, TS%, eFG%)
- Shot Quality Analysis
- Zone Efficiency (Hot Zones)
- Consistency Index

### Season Trend Report

**Endpoint**: `/reports/season/trends.pdf`

Contains:
- Rolling Averages (5-game, 10-game)
- Consistency Index (Coefficient of Variation)
- Performance variance visualization

### Clutch Time Report

**Endpoint**: `/reports/clutch/report.pdf`

Contains:
- Top Clutch Performers
- Team Clutch Summary
- Complete Clutch Statistics Table

---

## API Endpoints

All advanced analytics endpoints are under `/api/advanced/`:

### Player Stats
- `GET /player/<name>/advanced` - Full advanced stats
- `GET /player/<name>/usage` - Usage rate
- `GET /player/<name>/pps` - Points per shot

### Clutch
- `GET /clutch/<game_id>` - Game clutch stats
- `GET /clutch/season` - Season-wide clutch stats

### Lineup
- `GET /lineup/on-off/<player>` - On/off court splits
- `GET /lineup/duos` - Duo compatibility
- `GET /lineup/trios` - Trio compatibility
- `GET /lineup/rankings` - Lineup efficiency rankings
- `GET /rotation/<game_id>` - Rotation analysis

### Shots
- `GET /shots/chart` - Shot chart data
- `GET /shots/heatmap` - Zone heatmap
- `GET /shots/hexbin` - Hexbin data
- `GET /shots/by-play/<play_id>` - Shots by play type

### Other
- `GET /plays/rankings` - Play effectiveness rankings
- `GET /four-factors` - Dean Oliver's Four Factors
- `GET /zones` - Shot zone definitions

---

## Database Migration

To enable advanced analytics features, run the migration:

```bash
# Using SQLite CLI
sqlite3 basketball_stats.db < migrations/advanced_analytics_migration.sql

# Or using Python
python -c "
import sqlite3
conn = sqlite3.connect('basketball_stats.db')
with open('migrations/advanced_analytics_migration.sql', 'r') as f:
    conn.executescript(f.read())
conn.close()
"
```

This creates the following tables:
- `lineup_segments` - Track 5-player units
- `possessions` - Distinct possession tracking
- `shot_zones` - Expected values by zone
- `player_lineup_stats` - Player stats during lineup segments
