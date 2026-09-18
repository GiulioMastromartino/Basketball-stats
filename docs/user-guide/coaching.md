# Coaching Toolkit

Season planning, drill selection, play effectiveness, plain-language answers, and player development goals — all computed from your own game data.

> **Note:** the coaching toolkit is a **JSON API** under `/coaching` (login + team context required, same session cookie as the rest of the app). There is no sidebar page for it yet — query it with `curl`, the examples below, or any HTTP client. Auditors may view; goal mutations are GM/coach-only (`403` for auditors).

---

## Season Plan

September–June calendar with load flags, built from your games-per-month.

```
GET /coaching/season-plan?season_id=ALL
```

- `season_id` — a season id, or `ALL` (default).
- Response: month columns (`core/season_plan.py: build_season_plan`) with game counts and load flags (`load_flag`) so you can spot congested months before they happen.

```bash
curl http://localhost:8080/coaching/season-plan?season_id=ALL -b cookies.txt
```

---

## Drill Suggestions

Picks **3 drills** targeting your weakest Four Factor over recent games.

```
GET /coaching/drill-suggestions?game_type=Season&last_n=5&zone=
```

| Param | Default | Notes |
|-------|---------|-------|
| `game_type` | `Season` | `Season`, `Friendly`, `Playoff`, or `ALL` |
| `last_n` | `5` | 1–20 recent games in scope |
| `zone` | — | Optional zone filter passed to the suggester |

Returns `weakest` factor, human-readable `label`, `drills`, and `games_used`. With no games in scope it returns `"reason": "no games in scope"` and an empty list. Logic lives in `core/drill_suggester.py` over cached Four Factors (`core/aggregate_cache.py`).

```bash
curl "http://localhost:8080/coaching/drill-suggestions?game_type=Season&last_n=5" -b cookies.txt
```

---

## Play Effectiveness

Points per possession by **play × quarter**, with cold-play verdicts.

```
GET /coaching/play-effectiveness?game_type=ALL&season_id=ALL
```

Computed by `core/play_effectiveness.py` from tagged shot events (plays tagged during `/live-v2` tracking or otherwise linked to shots). If you never tag plays, this comes back empty — see [Plays Management](plays.md) and [Live Game Tracking](live-game.md).

```bash
curl "http://localhost:8080/coaching/play-effectiveness?game_type=ALL&season_id=ALL" -b cookies.txt
```

---

## Play Suggestions

Ranks your playbook for the current situation.

```
GET /coaching/play-suggestions?situation=vs+zone&quarter=4&limit=5
```

| Param | Notes |
|-------|-------|
| `situation` | Free text (`vs zone`, `protect lead`, `need stops`, …) — matched against play types/tags in `core/play_suggester.py` |
| `quarter` | Optional integer; non-integers return `400` |
| `limit` | Default `5`, capped at 20 |
| `game_type` | Default `ALL` |

---

## Natural-Language Queries

Rule-based answers over the existing analytics — no new math, just shortcuts.

```
POST /coaching/nl-query
Content-Type: application/json

{"query": "best lineup vs zone", "game_type": "Season"}
```

Response shape: `{"intent", "answer", "data"}`. Unknown queries fall back to a list of supported examples. Supported intents (`core/nl_queries.py`):

| Try asking | Intent |
|------------|--------|
| `best lineup vs zone` | `vs_zone` lineup |
| `best 5 to protect a lead` / clutch / close | `protect_lead` lineup |
| `best lineup vs fast` / transition | `vs_fast` lineup |
| `best lineup to get stops` / defense | `need_stops` lineup |
| `best lineup to score` / need a bucket | `need_score` lineup |
| `who is our top scorer?` | top scorer |
| `how is our shooting?` | shooting |
| `do we have a turnover problem?` | turnovers |
| `how is our rebounding?` | rebounding |
| `how is our recent form?` | recent form |

Missing/empty `query` returns `400`.

---

## Development Goals

Per-player rolling-window goals like "FT% ≥ 75 over the next 5 (games)" with live progress bars computed from `PlayerStat` rows. Games the player missed simply don't count.

```
GET    /coaching/dev-goals
POST   /coaching/dev-goals        {"player_name","metric","target","window"}
DELETE /coaching/dev-goals/<id>
```

| Field | Notes |
|-------|-------|
| `metric` | One of `points`, `reb`, `ast`, `stl`, `blk`, `tov` (lower-is-better), `fg_percent`, `tp_percent`, `ft_percent` (see `METRICS` in `core/dev_goals.py`) |
| `target` | Number (e.g. `75` for 75%) |
| `window` | 1–20 games, default `5` (`DEFAULT_WINDOW`) |

`POST` validates and returns `400` with a human-readable error plus the metric list when invalid. `POST`/`DELETE` are GM/coach-only — auditors get `403`. Progress payloads include current average, games used, and whether the target is met (`core/dev_goals.py: goal_progress`).

```bash
curl http://localhost:8080/coaching/dev-goals -b cookies.txt
curl -X POST http://localhost:8080/coaching/dev-goals \
  -H "Content-Type: application/json" -b cookies.txt \
  -d '{"player_name":"John Doe","metric":"ft_percent","target":75,"window":5}'
```

---

## Related

- [Plays Management](plays.md) — tag plays so effectiveness endpoints have data
- [Live Game Tracking](live-game.md) — where play tagging happens
- [Analytics & Reports](advanced-analytics.md) — the metrics behind the suggestions
- [API Reference](../technical/api.md) — full endpoint reference
