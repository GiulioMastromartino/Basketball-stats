# API Reference

HoopsLab provides JSON API endpoints for programmatic access to games, players, analytics, and playbook data.

---

## Base URLs

| Environment | URL |
|-------------|-----|
| Local dev | `http://localhost:8080` |
| Production | `https://your-domain.com` |

All API routes that don't start with `/api/` render HTML pages.

---

## Authentication

Most API endpoints require authentication via Flask-Login session cookie.

For programmatic access, use the login endpoint first:

```bash
curl -X POST http://localhost:8080/auth/login \
  -d "username=admin&password=admin123" \
  -c cookies.txt
```

Then include the cookie in subsequent requests:

```bash
curl http://localhost:8080/api/v1/plays -b cookies.txt
```

---

## Game Endpoints

### Game Detail Page

```
GET /game/<game_id>
```

Renders the full game detail page with box score, advanced stats, shot chart, and plays analysis.

### Game Raw Data

```
GET /game/<game_id>/export-raw
```

Returns complete game data as JSON download including all player stats, shot events, and game events.

### Delete Game

```
POST /game/<game_id>/delete
```

Deletes a game and all associated data.

### Create Test Game

```
POST /create-test-game
```

Creates a sample test game with randomized data for development/testing.

---

## Player Endpoints

### Player Detail

```
GET /player/<player_name>
```

Renders player profile with stats cards, scoring breakdown, shooting splits, per-36 estimates, game log, and shot chart.

Query parameters:
- `game_type` — Filter by game type (`Season`, `Friendly`, `Playoff`)

### Player Game Detail

```
GET /player/<player_name>/game-detail
```

Single game performance breakdown for a specific player.

### Player Stats

```
GET /player/<player_name>/stats
```

Full statistical summary for a player across all games.

### Players Listing

```
GET /players
```

Player list with two view modes:
- Default: Card view with 8 key metrics
- `?view=table` — Full data table with 28+ advanced metrics

Query parameters:
- `view` — `card` or `table`
- `game_type` — Filter by game type
- `exclude` — Player name to exclude from listing
- `search` — Search by player name

---

## Team Endpoints

### Team Detail

```
GET /team-detail
```

Aggregated team stats rendered on the player detail template, showing team totals across all games.

### Games List

```
GET /games-list
```

Lists all opponents with record, games played, and average score.

### Opponent Detail

```
GET /teams/<opponent_name>
```

Detailed stats against a specific opponent including game log.

---

## Analytics Endpoints

### Analytics Dashboard

```
GET /analytics
```

Renders the analytics dashboard with team overview, top performers, scoring trends, and player comparison.

### Team Overview (JSON)

```
GET /api/analytics/team_overview
```

Returns JSON with team-wide statistics.

### Multi-Player Comparison (JSON)

```
GET /api/analytics/multi_compare?players=Player1,Player2
```

Compare multiple players side-by-side.

### Player Progression (JSON)

```
GET /api/analytics/player_progression?player=<name>
```

Returns per-game stat progression for a player.

### Consistency Leaderboard (JSON)

```
GET /api/analytics/consistency_leaderboard
```

Players ranked by consistency index (coefficient of variation).

### Shooting Breakdown (JSON)

```
GET /api/analytics/shooting_breakdown
```

Shooting efficiency breakdown by player and zone.

### Role Analysis (JSON)

```
GET /api/analytics/role_analysis
```

Player role classification based on statistical profile.

---

## Playbook Endpoints

### List Plays

```
GET /plays/
```

Renders playbook grid with filter buttons (All, Offense, Defense, Special).

### Play Detail

```
GET /plays/<play_id>
```

View single play with SVG diagram and metadata.

### Create Play

```
POST /plays/add
```

Add a new play to the playbook.

### Edit Play

```
POST /plays/edit/<play_id>
```

Update play metadata.

### Delete Play

```
POST /plays/delete/<play_id>
```

Remove a play from the playbook.

### Clear All Plays

```
POST /plays/clear-all
```

Remove all plays (use with caution).

---

## Play Builder API

### Save Canvas

```
POST /api/v1/plays
```

Save play diagram from the Fabric.js canvas.

### Load Canvas

```
GET /api/v1/plays
```

Load all plays with canvas data.

### Play Types

```
POST /plays/types/add
GET  /plays/types/<type_id>/delete
```

Manage play categories.

---

## Advanced Analytics API

All endpoints under `/api/advanced/` return JSON.

### Player Advanced Stats

```
GET /api/advanced/player/<name>/advanced
GET /api/advanced/player/<name>/usage
GET /api/advanced/player/<name>/pps
GET /api/advanced/player/<name>/shot-chart?game_type=<type>
GET /api/advanced/player/<name>/zone-stats
```

### Clutch Performance

```
GET /api/advanced/clutch/<game_id>
GET /api/advanced/clutch/season
```

### Lineup Analysis

```
GET /api/advanced/lineup/on-off/<player>
GET /api/advanced/lineup/duos
GET /api/advanced/lineup/trios
GET /api/advanced/lineup/rankings
GET /api/advanced/rotation/<game_id>
```

### Shot Analysis

```
GET /api/advanced/shots/chart?player=<name>&game_type=<type>
GET /api/advanced/shots/heatmap?player=<name>
GET /api/advanced/shots/hexbin?player=<name>
GET /api/advanced/shots/by-play/<play_id>
```

### Four Factors

```
GET /api/advanced/four-factors
```

### Play Rankings

```
GET /api/advanced/plays/rankings
```

### Shot Zones

```
GET /api/advanced/zones
```

### Possessions

```
GET /api/advanced/possessions
```

### Team Stats

```
GET /api/advanced/player/<name>/zones
```

---

## PDF Export Endpoints

### Game Reports

```
GET /reports/games/<game_id>/summary.pdf
GET /reports/games/<game_id>/advanced_summary.pdf
GET /reports/games/<game_id>/visual.pdf
GET /reports/games/<game_id>/evolution.pdf
```

### Player Reports

```
GET /reports/player/<name>/report.pdf
GET /reports/player/<name>/scouting.pdf
```

### Team Reports

```
GET /reports/team/report.pdf
```

### Lineup Reports

```
GET /reports/lineup/report.pdf
```

### Season Reports

```
GET /reports/season/trends.pdf
```

### Clutch Reports

```
GET /reports/clutch/report.pdf
```

### Halftime Summary

```
POST /reports/live/halftime-pdf
```

### Download All (ZIP Bundle)

```
GET /reports/download-all
```

Downloads a ZIP containing team report + all player PDFs.

---

## Live Game Endpoints

### Live Game Page

```
GET /live-game
```

Renders the full-screen live tracking interface.

### Plays API (for live game selectors)

```
GET /api/plays
```

Returns JSON list of plays for the play selector dropdown.

### Save Live Game

```
POST /live-game/save
```

Saves the current live game state.

---

## File Upload

```
GET  /upload-game
POST /upload-game
```

Upload game data from CSV, PDF, or JSON files. Accepts multipart form data with a `file` field.

---

## Health Endpoints

```
GET /health/live
GET /health/ready
```

Returns `{"status": "healthy"}` when the application is running. Used by orchestration systems for liveness and readiness probes.

---

## Metrics

```
GET /metrics
```

Prometheus-formatted metrics for monitoring (requires authentication in production).
