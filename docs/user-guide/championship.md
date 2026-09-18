# External Championships

Follow your league alongside your own games: a bundled standings snapshot plus a daily-synced sidecar cache, with health checks and one-click promotion of fixtures into your planner.

Click **Championship** in the sidebar (`/analytics/championship`). Login + team context required; auditors may view.

---

## Two Sources

| Source (`?source=`) | What it is |
|---------------------|------------|
| `internal` (default) | Standings/record computed from **your DB games** (`Draft` games excluded), with per-opponent W/L and points for/against |
| `playbasket` | External league data: a **bundled snapshot** (`data/playbasket_dr4_2025_26.json` — DR4 Lombardia 2025/26, Girone M) overlaid with the **live sidecar cache**, refreshed by the daily sync |

On the Playbasket view you can filter by team (`?team=`) and switch between tracked championships (`?ext=<id>`).

---

## Promoting Fixtures (GM/coach only)

External fixtures can be promoted into your DB as `Draft` games (planning placeholders — they stay out of the internal standings until played). The page marks already-promoted rows so you can't double-import.

```
POST /api/advanced/external/games/<ext_game_id>/promote
```

Scoreless fixtures are rejected (`400`) so they never become 0–0 losses. Auditors get `403`.

---

## Sync Health

Per-championship freshness and cross-checks (read-only, auditors may view):

```
GET /analytics/championship/sync-health?ext=<id>
```

- **Freshness** — each championship is `stale` when its last check is older than `STALE_AFTER_HOURS = 26` (`core/sync_diff.py`).
- **Standings diff** — bundled snapshot vs live sidecar.
- **Score cross-check** — game score corrections, internal vs external.
- **Roster cross-check** — roster names vs box-score names.

Monitor-friendly probe (no login wall for your uptime checker semantics — `200 ok` / `503 stale`):

```
GET /health/sync
```

The `whatsapp` field reports Evolution instance state (`open`/`connecting`/`close`/`unknown`, informational only). The sync dashboard JSON behind Grafana is `grafana/dashboards/sync-health.json`; alert rules live in `prometheus/alerts.yml`.

---

## How the Sync Runs

- **Storage**: separate sidecar SQLite, default `data/external_cache.db`, overridable via `EXT_CACHE_PATH` (`core/external_store.py`). Never mixed with your main DB.
- **Adapters**: `jobs/adapters/` (`playbasket_html`, `fip_api`).
- **Schedule**: daily cron in prod (the `scraper` service runs `python -m jobs.championship_sync --daemon`); manually:

```bash
python -m jobs.championship_sync --once
python -m jobs.check_sync_health   # exit 0 fresh, 1 stale/erroring, 2 sidecar unreadable
```

Wire `check_sync_health` after the sync in cron/Jenkins for failure alerting — see [Deployment](../technical/deployment.md).

---

## Related

- [Analytics & Reports](advanced-analytics.md) — internal metrics the standings build on
- [Deployment](../technical/deployment.md) — scraper service, monitoring, WhatsApp gateway
- [API Reference](../technical/api.md) — endpoint reference
