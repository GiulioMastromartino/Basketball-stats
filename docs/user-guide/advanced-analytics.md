# Analytics & Reports

Advanced analytics engine providing deep insights into player performance, lineup efficiency, shot quality, and clutch performance.

---

## Analytics Dashboard

Access the analytics dashboard at `/analytics` after logging in.

### Sections

| Tab | Description |
|-----|-------------|
| **Team Overview** | Season summary, top performers, scoring trends |
| **Player Comparison** | Select 2+ players to compare stats side-by-side |
| **Progression** | Per-game stat trends for individual players |
| **Consistency** | Leaderboard ranked by consistency index |
| **Shooting** | Shooting efficiency breakdown by player and zone |
| **Roles** | Player role classification based on statistical profile |

---

## Advanced Metrics

### True Shooting % (TS%)

Measures shooting efficiency accounting for field goals, 3-pointers, and free throws.

```
TS% = PTS / (2 × (FGA + 0.44 × FTA))
```

| Range | Rating |
|-------|--------|
| 60%+ | Excellent |
| 55–60% | Good |
| 50–55% | Average |
| <50% | Below average |

### Effective FG% (eFG%)

Adjusts FG% for the fact that 3-pointers are worth more than 2-pointers.

```
eFG% = (FGM + 0.5 × 3PM) / FGA
```

### True Usage Rate (USG%)

Percentage of team plays used by a player while on the court.

```
USG% = ((FGA + 0.44 × FTA + TOV) × (Team Minutes / 5)) / (Minutes × Team Possessions) × 100
```

| Range | Role |
|-------|------|
| 20%+ | High usage (primary scorer) |
| 15–20% | Average usage |
| <15% | Low usage (role player) |

### Points Per Shot (PPS)

Simple efficiency metric measuring points scored per field goal attempt.

```
PPS = Points / FGA
```

| Range | Rating |
|-------|--------|
| 1.10+ | Excellent |
| 1.00–1.10 | Good |
| <1.00 | Below average |

### Game Score

Holistic measure of a player's single-game productivity (similar to NBA's Game Score).

```
Game Score = PTS + 0.4 × FG - 0.7 × FGA - 0.4 × (FTA - FT) + 0.7 × OREB + 0.3 × DREB
             + STL + 0.7 × AST + 0.7 × BLK - 0.4 × PF - TOV
```

### Net Rating

Points scored minus points allowed per 100 possessions.

```
Net Rating = ORtg - DRtg
```

| Range | Impact |
|-------|--------|
| +15+ | Elite impact |
| +5 to +15 | Positive impact |
| -5 to +5 | Neutral |
| < -5 | Negative impact |

---

## Shot Quality Model

Assigns expected point values to different court zones. Calculated in Rust via PyO3 for performance.

| Zone | Expected Value |
|------|---------------|
| Rim | 1.20 pts |
| Paint (non-rim) | 0.85 pts |
| Midrange | 0.75 pts |
| Corner 3 | 1.10 pts |
| Above Break 3 | 1.05 pts |
| Free Throw | 0.75 pts |

### Shot Quality Delta

```
Shot Quality Delta = Actual Points - Expected Points
```

- **Positive** = "Tough shot maker" (outperforming expectations)
- **Negative** = "Poor shot selection" (underperforming expectations)

---

## Lineup Analytics

### On/Off Court Splits

Compare team performance when a player is on vs off the court:

| Metric | Description |
|--------|-------------|
| **ORtg** | Points scored per 100 possessions |
| **DRtg** | Points allowed per 100 possessions |
| **Net Rating** | ORtg - DRtg |
| **Net Differential** | On Court Net - Off Court Net |

Positive differential = player has a positive impact on team performance.

### Duo Compatibility

Shows how two-player combinations perform together:

- **Synergy Factor** — Combined net rating when both players are on court
- **Compatibility Matrix** — Color-coded grid (green = positive, red = negative)

### Trio Combinations

Three-player lineup combinations ranked by net rating.

### 5-Man Lineup Rankings

Full 5-man units ranked by Net Rating with minimum possession threshold.

### Rotation Analysis

Visualize substitution patterns and player minute distributions across a game.

---

## Shot Charts

### Court Mapping

Shots plotted using `x_loc` and `y_loc` coordinates:
- Court dimensions: 0–500 (x), 0–470 (y)
- Basket located at (250, 50)

### Visualization Types

| Type | Description |
|------|-------------|
| **Shot Markers** | Individual makes (green) and misses (red) |
| **Hexbin Heatmap** | Grouped by zone with FG% coloring |
| **Zone Efficiency** | Aggregated stats by court zone |

### Filtering

Filter shot charts by:
- **Player** — View individual shot profiles
- **Game Type** — Season, Friendly, or Playoff
- **Play Type** — Shots from specific plays (e.g., "Pick & Roll")

---

## Four Factors (Dean Oliver)

| Factor | Weight | Description |
|--------|--------|-------------|
| **Effective FG%** | 40% | Shooting efficiency (eFG%) |
| **Turnover %** | 25% | Turnovers per possession |
| **Offensive Rebound %** | 20% | OREB rate |
| **Free Throw Rate** | 15% | FTA / FGA |

Each factor is displayed with your team's value vs. opponent value and a composite score.

---

## Clutch Performance

Stats filtered for "Crunch Time" situations:
- Score within 5 points
- Less than 5 minutes remaining in the 4th quarter or overtime

Available views:
- **Player Clutch Stats** — Individual performance in clutch situations
- **Team Clutch Summary** — Aggregate clutch performance
- **Clutch Leaders** — Top performers ranked by clutch points

---

## Related

- [Live Game Tracking](live-game.md) — Tag plays and track shots
- [PDF Exports](pdf-exports.md) — Generate report PDFs
- [Architecture](../technical/architecture.md) — Analytics pipeline details
