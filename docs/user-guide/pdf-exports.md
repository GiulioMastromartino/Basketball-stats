# PDF Exports

Generate professional, publication-ready PDF reports for games, players, teams, lineups, and seasons.

---

## Available Reports

### Game Reports

| Report | Endpoint | Content |
|--------|----------|---------|
| **Game Summary** | `/reports/games/<id>/summary.pdf` | Box score, shooting stats, plays analysis |
| **Advanced Summary** | `/reports/games/<id>/advanced_summary.pdf` | Advanced metrics, efficiency ratings |
| **Visual Game Report** | `/reports/games/<id>/visual.pdf` | Score worm, quarterly flow, Four Factors |
| **Evolution Report** | `/reports/games/<id>/evolution.pdf` | Team performance over time |

### Player Reports

| Report | Endpoint | Content |
|--------|----------|---------|
| **Player Report** | `/reports/player/<name>/report.pdf` | Career stats, performance by play, shot breakdown |
| **Scouting Card** | `/reports/player/<name>/scouting.pdf` | Shot chart, hot zones, advanced metrics, consistency |

### Team Reports

| Report | Endpoint | Content |
|--------|----------|---------|
| **Team Report** | `/reports/team/report.pdf` | Season overview, top performers, plays analysis |
| **Season Trends** | `/reports/season/trends.pdf` | Rolling averages, consistency index, trends |

### Lineup Reports

| Report | Endpoint | Content |
|--------|----------|---------|
| **Lineup Report** | `/reports/lineup/report.pdf` | Top 5-man lineups, duo/trio matrices |

### Clutch Reports

| Report | Endpoint | Content |
|--------|----------|---------|
| **Clutch Time Report** | `/reports/clutch/report.pdf` | Clutch performers, team clutch summary |

### Halftime Summary

| Report | Endpoint | Content |
|--------|----------|---------|
| **Halftime PDF** | `POST /reports/live/halftime-pdf` | First-half box score, +/- summary |

---

## Accessing Reports

### From the Web Interface

Every game, player, and team page has a **Export PDF** button (usually top right of the page):

1. Navigate to the specific game, player, or team page
2. Click the **Export PDF** or **Download Report** button
3. The PDF generates on-the-fly and downloads to your device

### Via Direct URL

Reports are accessible at their direct URLs (requires authentication):

```
https://your-app.com/reports/games/42/visual.pdf
https://your-app.com/reports/player/John%20Smith/scouting.pdf
https://your-app.com/reports/team/report.pdf
```

### Bulk Download

The **Download All** button on the analytics dashboard generates a ZIP bundle containing:
- Team report
- Individual player PDFs for all active players
- Aggregated statistics

---

## Report Details

### Visual Game Report

The most comprehensive game report includes:

- **Score Worm** — Lead changes visualized throughout the game
- **Quarterly Scoring** — Per-quarter points breakdown (bar chart)
- **Four Factors Dashboard** — EFG%, TOV%, OREB%, FTA Rate
- **Top Performers** — Leading scorers, rebounders, playmakers
- **Team Totals** — Aggregated team statistics
- **Advanced Metrics** — TS%, eFG%, Game Score, Net Rating

### Player Scouting Card

A compact one-page player profile:

- **Primary Stats** — PPG, RPG, APG, FG%, 3P%, FT%
- **Advanced Metrics** — USG%, PPS, TS%, eFG%, Game Score
- **Shot Quality Analysis** — Expected vs actual points by zone
- **Zone Efficiency** — Hot zone heatmap with color coding
- **Consistency Index** — Coefficient of variation across games

### Game Summary

Standard box score format:

- Player-by-player stat line (MIN, PTS, REB, AST, STL, BLK, TOV, PF)
- Team totals
- Shooting percentages by player
- + / - column

### Season Trend Report

Longitudinal analysis:

- **Rolling Averages** — 5-game and 10-game rolling windows
- **Consistency Index** — Coefficient of variation for key metrics
- **Performance Variance** — Visualization of highs and lows

### Clutch Time Report

Pressure situation analysis:

- **Crunch Time** — Score within 5 points, under 5 minutes remaining
- **Top Clutch Performers** — Ranked by clutch points and efficiency
- **Team Clutch Summary** — Aggregate clutch performance
- **Complete Clutch Table** — All players with clutch stats

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **PDF is empty** | Ensure the game/player has data. A game with 0 shots cannot generate meaningful charts. |
| **Generation failed** | Check application logs. Common issues: missing font definitions, database timeouts. |
| **PDF won't download** | Check browser pop-up blocker settings. Try right-clicking the Export button and "Save Link As". |
| **Slow generation** | Large games with 50+ shot events may take 2–3 seconds. Reports are cached for 5 minutes. |
| **Missing reports** | Some report types require specific data (e.g., Clutch Report needs close-game data). |

---

## Technical Details

- **Engines**: ReportLab (structured reports) + WeasyPrint (visual reports)
- **Generation**: In-memory — no temporary files on disk
- **Graphics**: Vector-based for crisp printing at any resolution
- **Caching**: Reports cached for 5 minutes (configurable via `CACHE_TIMEOUT`)
- **Styles**: Custom stylesheets ensure consistent branding across all reports

---

## Related

- [Getting Started](../user-guide/getting-started.md) — Set up the application
- [Live Game Tracking](live-game.md) — Generate halftime PDFs
- [Analytics & Reports](advanced-analytics.md) — Understand the metrics in your reports
