# Architecture

Overview of the HoopsLab application architecture, data model, and design decisions.

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Client (Browser)                  │
│  Jinja2 Templates + Bootstrap 5.3 + Fabric.js       │
├─────────────────────────────────────────────────────┤
│                    Flask 3.1                         │
│  ┌─────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ Routes  │ │ Services │ │ Analytics Engine     │ │
│  │(13 BPs) │ │(11 svcs) │ │ (Rust + Python)      │ │
│  └────┬────┘ └────┬─────┘ └──────────┬───────────┘ │
├───────┴───────────┴───────────────────┴────────────┤
│              SQLAlchemy 2.0 (create_all +           │
│              auto-migrate; Alembic chain frozen)     │
├─────────────────────────────────────────────────────┤
│         SQLite (dev) / PostgreSQL 16 (prod)          │
│  + external championships sidecar (SQLite)          │
│  + Evolution API WhatsApp gateway (Docker)          │
└─────────────────────────────────────────────────────┘
```

### Layers

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **Presentation** | Jinja2 + Bootstrap 5.3 | Server-rendered HTML, responsive UI |
| **Application** | Flask 3.1 + 13 Blueprints | Route handling, auth, session, CSRF |
| **Service** | Python services | Business logic, analytics computation |
| **Performance** | Rust (PyO3) | Shot quality, zone analysis, stat formulas |
| **Data** | SQLAlchemy 2.0 | ORM; tables via `create_all`, columns via auto-migrate |
| **Storage** | SQLite / PostgreSQL | Persistent data |
| **Messaging** | Evolution API v2.3.7 (Baileys) | WhatsApp OTP, notifications, halftime shares |

---

## Application Structure

```
Basketball-stats/
├── run.py                    # Entry point (Flask app creation)
├── manage.py                 # Flask CLI (db migrations, commands)
├── config.py                 # Configuration classes (dev/test/prod)
├── quick_start.py            # One-command setup + run
├── requirements.txt          # Production dependencies
├── requirements-local.txt    # Local development dependencies
│
├── web/                      # Flask web application
│   ├── __init__.py           # App factory (extensions, blueprints)
│   ├── decorators.py         # Route decorators (auth, team access)
│   ├── routes/               # Blueprints (13: auth, main, api_v1,
│   │                         #   analytics, plays, training, reports,
│   │                         #   advanced_api, health, live_v2, pdf_export,
│   │                         #   share, coaching)
│   ├── templates/            # Jinja2 templates (~61 files)
│   └── static/               # CSS, JS, images
│
├── core/                     # Backend logic
│   ├── models.py             # SQLAlchemy ORM models (29)
│   ├── analytics.py          # Stat calculations
│   ├── charts.py             # Matplotlib chart generation
│   ├── csv_processor.py      # CSV game data import
│   ├── parser.py             # PDF game stats parser
│   ├── season_plan.py        # Sept–June planner + load flags
│   ├── drill_suggester.py    # Weakest-Four-Factor drill picks
│   ├── play_effectiveness.py # PPP by play × quarter
│   ├── play_suggester.py     # Contextual play ranking
│   ├── nl_queries.py         # Rule-based coaching Q&A
│   ├── dev_goals.py          # Development-goal progress
│   ├── social_cards.py       # 1080×1080 PNG cards (Pillow)
│   ├── comms_templates.py    # Post-game {{merge_tag}} templates
│   ├── sync_diff.py          # Standings/game diffs + cross-checks
│   ├── halftime_share.py     # One-tap share text builder
│   ├── aggregate_cache.py    # 120 s analytics aggregate cache
│   ├── usage_meter.py        # SaaS usage counters (SystemSetting)
│   └── services/             # Service layer (11 services)
│
├── jobs/                     # Cron jobs
│   ├── championship_sync.py  # Daily external-championship sync
│   └── check_sync_health.py  # Freshness probe (exit-code alerting)
│
├── basketball_stats_rust/    # Rust PyO3 module
│   └── src/lib.rs            # Shot quality, zone analysis
│
├── scripts/                  # Utility scripts (deploy.sh, init_db.py, …)
├── migrations/               # Alembic dir (empty; see Migrations below)
├── legacy_migrations/        # Frozen historical chain (read-only)
└── tests/                    # Pytest test suite (860+ tests)
```

---

## Blueprint Routes

| Blueprint | Prefix | Purpose |
|-----------|--------|---------|
| `auth_bp` | `/auth` | Login, logout, OTP, onboarding, user/player admin |
| `main_bp` | `/` | Dashboard, games, players, lineups, live game, seasons/orgs/teams admin |
| `api_v1_bp` | `/api/v1` | Games/plays API, import + webhook, video export, player GDPR |
| `analytics_bp` | `/` | Analytics dashboard, championship + sync-health |
| `plays_bp` | `/` | Playbook CRUD |
| `training_bp` | `/` | Training sessions, segments, attendance, PDFs |
| `reports_bp` | `/reports` | PDF reports + live halftime PDF/share |
| `advanced_api_bp` | `/api/advanced` | JSON analytics endpoints |
| `health_bp` | `/` | `live`, `ready`, `sync` probes |
| `live_v2_bp` | `/api/live-v2` | Tablet console event ingestion |
| `pdf_export_bp` | `/api/pdf` | PDF export API |
| `share_bp` | `/` | Share links, PNG cards, comms previews |
| `coaching_bp` | `/coaching` | Season plan, drills, effectiveness, NL queries, dev goals |

## Migrations

Deliberately boring: tables are created by `db.create_all()` on boot
(`scripts/init_db.py`, tests) and missing columns are backfilled by
`core/db_migrations.add_missing_columns()`. `migrations/versions/` is
empty and the `legacy_migrations/` chain is frozen read-only history —
do not add Alembic revisions unless the project moves off this scheme.

---

## Data Model

### Core Entities

```
Organization ──┐
               │
               ├── Team ──┐
               │          │
               ├── User   ├── Player
                          │
                          ├── Game ── PlayerStat
                          │    │
                          │    ├── ShotEvent
                          │    ├── GameEvent
                          │    └── LineupSegment
                          │
                          ├── Play
                          │    └── PlaySequence
                          │
                          └── Lineup
                               └── PlayerLineupStats
```

### Key Models

| Model | Fields | Purpose |
|-------|--------|---------|
| **Organization** | name, slug | Multi-tenant top-level entity |
| **Team** | name, slug, organization_id | Per-organization team |
| **User** | username, email, role, WorkOS SSO | Authentication & authorization |
| **Player** | name, email, active, team_id | Roster management |
| **Game** | date, opponent, team_score, opponent_score, result, game_type | Game records |
| **PlayerStat** | points, minutes, rebounds, assists, shooting splits, plus_minus | Per-game player stats |
| **Play** | name, description, play_type, diagram_svg, canvas_data | Playbook entries |
| **ShotEvent** | shot_type, result, points, x_loc, y_loc, zone, quarter, play_id | Shot tracking |
| **GameEvent** | event_type, player_name, timestamp, quarter, score_margin | Full event log |
| **LineupSegment** | players (JSON), lineup_hash, points_scored, points_allowed, possessions | 5-player on-floor tracking |
| **Lineup** | players (JSON), display_name, ortg, drtg, net_rating | Multi-game lineup aggregation |
| **Possession** | team_possession, quarter, points, play_id | Distinct possession tracking |
| **ShotZone** | zone_name, zone_type, expected_value, boundaries | Expected values by zone |

---

## Analytics Pipeline

```
Game Data (CSV/PDF/JSON)
        │
        ▼
    Import & Parse
        │
        ▼
    Calculate Base Stats
    (PTS, REB, AST, FG%, etc.)
        │
        ▼
    Advanced Metrics
    (TS%, eFG%, USG%, PPS, Game Score)
        │
        ├──▶ Shot Quality (Rust)
        │       Expected values by zone
        │       Shot Quality Delta
        │
        ├──▶ Lineup Analysis
        │       On/Off splits
        │       Duo/Trio compatibility
        │       Net Rating
        │
        ├──▶ Clutch Analysis
        │       Score within 5, under 5 min
        │
        └──▶ Four Factors
                EFG%, TOV%, OREB%, FTA Rate
```

---

## Auth & Security

| Feature | Implementation |
|---------|----------------|
| **Password Auth** | Flask-Bcrypt |
| **SSO** | WorkOS (Google, Microsoft, GitHub) |
| **OTP 2FA** | 6-digit email/WhatsApp codes, required for managers (GM) at login |
| **Auditor role** | Read-only: may view admin pages, blocked from all mutations |
| **CSRF** | Flask-WTF |
| **Rate Limiting** | Flask-Limiter (200/day, 50/hour) |
| **Session** | Signed cookies, HTTP-only, SameSite=Lax |
| **Multi-tenant** | Organization + Team scoping |

The app supports a `DISABLE_AUTH` mode for single-user/personal deployments where all routes are accessible without login.

---

## WhatsApp Notifications (Evolution API)

Outbound WhatsApp (login OTPs, game notifications, halftime shares) is a
thin adapter, `core/services/whatsapp_service.py`, over a self-hosted
Evolution API v2.3.7 sidecar (Baileys provider) in compose. Dispatch stays
in `core/services/notification_service.py` (per-user channel preference:
email / WhatsApp / group / all). Key properties:

- Same function signatures as before — routes never touch HTTP directly.
- Sends return `201 → True`; failures log and return `False`, never raise.
- Unconfigured/unpaired gateway degrades silently (OTP falls back to email).
- Media supported: the halftime PDF can go as a document attachment.
- Instance state is exposed at `GET /health/sync` (`whatsapp` field) and
  checked by `scripts/deploy.sh`.

Runbook: `docs/archive/evolution-integration-plan.md`.

---

## PDF Generation

Two engines are used:

### ReportLab (Primary)
- Programmatic PDF construction
- Vector graphics for charts and tables
- Used for: game reports, player reports, team reports

### WeasyPrint (HTML → PDF)
- Renders Jinja2 templates to PDF
- Used for: visual game reports, advanced reports

---

## Rust Module (PyO3)

The `basketball_stats_rust` package provides compiled performance-critical functions:

- **Shot Quality** — Expected value calculation by court zone
- **Zone Analysis** — Shot distribution and efficiency by zone
- **Stat Formulas** — Optimized computation of advanced metrics

Built with `maturin` and included as a wheel in the Docker image.
