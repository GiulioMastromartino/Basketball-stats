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
POST /api/v1/plays/api/save-canvas
```

Save play diagram from the Fabric.js canvas.

### Load Canvas

```
GET /api/v1/plays/api/load-canvas/<play_id>
```

Load a single play with canvas data, plus frame snapshots:

```
POST /api/v1/plays/api/<play_id>/frame-snapshots
```

Play listing for builder/live selectors:

```
GET /api/v1/plays
GET /api/v1/plays/types
GET /api/plays            (legacy live-game selector, main blueprint)
```

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

### Halftime One-Tap Share

```
POST /reports/live/halftime-share
```

Same live payload as `halftime-pdf`, plus `group_id` (a `WhatsAppGroup`
id scoped to the session team) or `phone`. Sends the staff WhatsApp
summary via the Evolution API gateway; with neither destination it
returns the text for manual copy (`{"sent": false, ...}`). Optional
`pdf_base64` + `pdf_filename` forwards the rendered halftime PDF as a
document attachment (`pdf_sent: true/false`). Auditors get `403`.
Used by the **HT SHARE** button in the `/live-v2` console.

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

Returns JSON list of plays for the play selector dropdown (legacy live-game page; v2 console uses `/api/v1/plays`).

### Save Live Game

```
POST /live-game/save
```

Saves the current live game state.

### Tablet Console v2

```
GET /live-v2
```

The current game-day console (score strip, roster rails, tap-to-log
half-court, action pad, 50-step undo, substitution sheet, **HT SHARE**
one-tap halftime button). Per-event sync (idempotent, resync + shot-precise undo):

```
POST /api/live-v2/events
```

Legacy page (`GET /live-game`, `POST /live-game/save`) is still available.

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
GET /health/live    → {"status": "alive", ...}
GET /health/ready   → {"status": "ready", ...} (503 when DB is down)
GET /health/sync    → {"status": "ok"|"stale", "whatsapp": "open"|..., ...}
```

`GET /health/sync` is the monitor-friendly probe: `200` with
`{"status": "ok"}` when every tracked championship is fresh, `503` with
`{"status": "stale"}` otherwise. The `whatsapp` field reports the Evolution
API instance state (`open`/`connecting`/`close`/`unknown`) and is
informational only. Per-championship detail (login required) lives at
`/analytics/championship/sync-health`.

---

## Metrics

```
GET /metrics
```

Prometheus-formatted metrics for monitoring (requires authentication in production).

---

## Coaching API (`/coaching`)

Read-only JSON for season planning, drill selection, play effectiveness,
natural-language queries, and development goals. Auditors may view; goal
mutations are GM/coach-only (`403` for auditors).

```
GET  /coaching/season-plan?season_id=ALL
GET  /coaching/drill-suggestions?game_type=Season&last_n=5&zone=
GET  /coaching/play-effectiveness?game_type=ALL&season_id=ALL
POST /coaching/nl-query                  {"query": "best lineup vs zone"}
GET  /coaching/play-suggestions?situation=vs+zone&quarter=4&limit=5
GET  /coaching/dev-goals
POST /coaching/dev-goals                 {"player_name","metric","target","window"}
DELETE /coaching/dev-goals/<id>
```

Supported NL intents: lineup by context (`vs_zone`, `vs_fast`,
`protect_lead`, `need_stops`, `need_score`), top scorer, shooting,
turnovers, rebounding, recent form. Supported goal metrics: `points`,
`reb`, `ast`, `stl`, `blk`, `tov` (lower-is-better), `fg_percent`,
`tp_percent`, `ft_percent`.

---

## Sharing & Social Cards

Expiring, revocable public links (no login to view; JSON only):

```
POST   /share                       {"target_type": "game"|"player", "target_id", "expires_in_days"}
GET    /s/<token>
DELETE /share/<id>
```

1080×1080 PNG cards rendered server-side with Pillow:

```
GET /share/cards/game/<game_id>      final-score card
GET /share/cards/player/<player_id>  "Player of the game" card (best scoring game)
```

Post-game comms templates with `{{merge_tags}}`:

```
POST /share/comms-preview            {"template": "postgame_whatsapp"|"postgame_email_subject"|"postgame_email_body"|"parent_digest", "game_id"}
```

---

## Video Export (Veo/Pixellot tie-in)

Timestamped event log for syncing clips in external video tools. No video
is hosted here.

```
GET /api/v1/games/<game_id>/video-export?format=json   (default)
GET /api/v1/games/<game_id>/video-export?format=csv
```

Rows carry `quarter`, `game_seconds`, `timestamp`, `type`, `player`,
`points`, `x`/`y`, ordered by quarter then clock.

---

## Stat-Crew Import Webhook

Push a single game as JSON (nested `IMPORT_JSON` or flat `LIVE` shape):

```
POST /api/v1/games/import            {"game": {...}, "player_stats": [...]}
```

Returns `201` with `game_id`; `409` when `sort_date` + `opponent` already
exist for the team; `403` for auditors. Optional `?season=<id>`.

---

## Championship Sync Health

```
GET /analytics/championship/sync-health?ext=<id>
```

Per-championship sidecar health (freshness vs the 26 h threshold, game/
standings counts, last runs, recent errors) plus: standings diff (bundled
snapshot vs live sidecar), game score-correction diff, internal-vs-external
score cross-check, and roster cross-check (roster vs box-score names).
See also `GET /health/sync` for the monitor-friendly probe.

---

## Player GDPR (GM-only)

```
GET    /api/v1/players/<id>/export    profile + every box-score row
DELETE /api/v1/players/<id>           erase player + their stat rows (audited)
```

Both return `403` for non-GMs (including auditors) and `404` for players
outside the session team.
