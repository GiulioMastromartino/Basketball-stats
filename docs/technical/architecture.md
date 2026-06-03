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
│  │ (8 BPs) │ │ (7 svcs) │ │ (Rust + Python)      │ │
│  └────┬────┘ └────┬─────┘ └──────────┬───────────┘ │
├───────┴───────────┴───────────────────┴────────────┤
│              SQLAlchemy 2.0 / Alembic                │
├─────────────────────────────────────────────────────┤
│         SQLite (dev) / PostgreSQL 16 (prod)          │
└─────────────────────────────────────────────────────┘
```

### Layers

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **Presentation** | Jinja2 + Bootstrap 5.3 | Server-rendered HTML, responsive UI |
| **Application** | Flask 3.1 + 8 Blueprints | Route handling, auth, session, CSRF |
| **Service** | Python services | Business logic, analytics computation |
| **Performance** | Rust (PyO3) | Shot quality, zone analysis, stat formulas |
| **Data** | SQLAlchemy 2.0 + Alembic | ORM, migrations, connection pooling |
| **Storage** | SQLite / PostgreSQL | Persistent data |

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
│   ├── routes/               # Blueprints (auth, main, analytics, etc.)
│   ├── templates/            # Jinja2 templates (~55)
│   └── static/               # CSS, JS, images
│
├── core/                     # Backend logic
│   ├── models.py             # SQLAlchemy ORM models (~25)
│   ├── analytics.py          # Stat calculations
│   ├── charts.py             # Matplotlib chart generation
│   ├── pdf_exports.py        # PDF report generation (ReportLab)
│   ├── csv_processor.py      # CSV game data import
│   ├── parser.py             # PDF game stats parser
│   └── services/             # Service layer (7 services)
│
├── basketball_stats_rust/    # Rust PyO3 module
│   └── src/lib.rs            # Shot quality, zone analysis
│
├── scripts/                  # Utility scripts
├── migrations/               # Alembic database migrations
└── tests/                    # Pytest test suite
```

---

## Blueprint Routes

| Blueprint | Prefix | Routes | Purpose |
|-----------|--------|--------|---------|
| `main_bp` | `/` | 23 | Dashboard, games, players, lineups, live game |
| `auth_bp` | `/auth` | 9 | Login, logout, OTP, user management |
| `analytics_bp` | `/` | 10 | Analytics dashboard + JSON endpoints |
| `plays_bp` | `/` | 13 | Playbook CRUD |
| `reports_bp` | `/reports` | 12 | PDF report generation |
| `api_v1_bp` | `/api/v1` | 2 | Plays API |
| `builder_api_bp` | `/api/v1` | 2 | Play canvas save/load |
| `advanced_api_bp` | `/api/advanced` | 28 | JSON analytics endpoints |
| `health_bp` | `/` | 2 | Health checks |

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
| **OTP** | Time-based one-time passwords |
| **CSRF** | Flask-WTF |
| **Rate Limiting** | Flask-Limiter (200/day, 50/hour) |
| **Session** | Signed cookies, HTTP-only, SameSite=Lax |
| **Multi-tenant** | Organization + Team scoping |

The app supports a `DISABLE_AUTH` mode for single-user/personal deployments where all routes are accessible without login.

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
