# Deployment

Guide for deploying HoopsLab to production environments.

---

## Options Overview

| Method | Best For | Difficulty |
|--------|----------|------------|
| Docker Compose | Servers, NAS, single-machine | Easy |
| Docker + Registry | Kubernetes, multi-host | Medium |
| Manual | VPS, custom setup | Medium |

---

## Docker Compose Deployment

### Prerequisites

- Docker & Docker Compose installed
- Git

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats

# 2. Configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Start the stack (dev compose: db, web, scraper, cloudflared)
docker-compose up -d
```

The dev stack runs the app via `entrypoint.sh` (Gunicorn) against PostgreSQL, plus the championship-sync sidecar and an optional Cloudflare tunnel.

### Production stack (`docker-compose.prod.yml`)

Production deploys via Jenkins (`Jenkinsfile`) calling
`scripts/deploy.sh`, which builds, brings up the stack, and verifies the
WhatsApp instance state. Deploys read `.env.prod` (see `.env.prod.example`).

The prod stack (all behind the `backend` network; `nginx` serves `:8080`) starts:

| Service | Purpose |
|---------|---------|
| `db` | PostgreSQL 16 with persistent volume |
| `redis` | Rate-limit storage + cache |
| `migrator` | One-shot DB bootstrap, then exits |
| `web-1/2/3` | Flask app via Gunicorn on port 8080 (nginx upstream) |
| `nginx` | Reverse proxy / TLS termination |
| `evolution` | WhatsApp gateway (Evolution API v2.3.7, Baileys) |
| `scraper` | External championship sync sidecar |
| `prometheus` / `grafana` | Metrics + dashboards (alerts in `prometheus/alerts.yml`) |
| `loki` / `promtail` | Log aggregation |

### Environment Variables

Set these in `.env` (dev) or `.env.prod` (production):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Flask session signing key (generate a random string) |
| `DATABASE_URL` | No | SQLite | `postgresql://user:pass@db/basketball_stats` |
| `FLASK_ENV` | No | `development` | Set to `production` for production |
| `DISABLE_AUTH` | No | `false` | `true` for single-user/personal deployments |
| `EVOLUTION_API_URL` | For WhatsApp | — | `http://evolution:8080` in prod compose |
| `EVOLUTION_API_KEY` | For WhatsApp | — | Global API key (random string, shared with the sidecar) |
| `EVOLUTION_INSTANCE` | No | `basketball-bot` | WhatsApp instance name |
| `CLOUDFLARE_TUNNEL_TOKEN` | No | — | For Cloudflare Tunnel public access |

---

## Building & Publishing the Image

```bash
# Build the multi-stage image (Rust + Python)
docker build -t your-registry/basketball-stats:latest .

# Push to registry
docker push your-registry/basketball-stats:latest
```

The multi-stage build:
1. **Stage 1 (Rust Builder)** — Compiles the Rust analytics module via PyO3/maturin
2. **Stage 2 (Final)** — Installs Python deps + the compiled Rust wheel

---

## TrueNAS Scale Deployment

Single-container SQLite path (Custom App):

1. Go to **Apps** → **Discover Apps** → **Custom App**
2. **Application Name**: `basketball-stats`
3. **Image**: `your-registry/basketball-stats:latest`
4. **Environment Variables**:
    - `DATABASE_URL`: `sqlite:////app/data/basketball_stats.db`
    - `SECRET_KEY`: (generate a random string)
    - `FLASK_ENV`: `production`
5. **Storage**: Map persistent host paths (note: `/app/instance` is created by the Dockerfile but unused — the app reads `DATABASE_URL`, `GAMES_DIR`, `OUTPUT_DIR`, `UPLOAD_FOLDER`):
    - `/mnt/pool/app-data` → `/app/data` (SQLite file when `DATABASE_URL` points there)
    - `/mnt/pool/games` → `/app/Games` (CSV import)
    - `/mnt/pool/output` → `/app/Output` (generated files)
    - `/mnt/pool/uploads` → `/app/uploads` (upload staging)
6. **Networking**: Container port `8080` → Node port `9080`

---

## Manual VPS Deployment

### 1. Setup

```bash
git clone https://github.com/GiulioMastromartino/Basketball-stats.git
cd Basketball-stats

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Database

```bash
# PostgreSQL setup
createdb basketball_stats
export DATABASE_URL="postgresql://user:pass@localhost/basketball_stats"
```

### 3. Initialize

```bash
python scripts/init_db.py
python scripts/promote_admin.py
```

### 4. Run with Gunicorn

```bash
gunicorn --config gunicorn_config.py run:app
```

Or use the entrypoint script:

```bash
./entrypoint.sh
```

### 5. Reverse Proxy (Nginx Example)

```nginx
server {
    listen 80;
    server_name stats.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Configuration Reference

### Config Classes (`config.py`)

| Class | Environment |
|-------|-------------|
| `DevelopmentConfig` | Local dev (debug on, SQLite, relaxed security) |
| `TestingConfig` | Automated tests (in-memory DB, CSRF disabled) |
| `ProductionConfig` | Production (debug off, HTTPS, strict CSRF) |

### Key Production Settings

| Setting | Recommendation |
|---------|---------------|
| `SECRET_KEY` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `SESSION_COOKIE_SECURE` | `True` (requires HTTPS) |
| `WTF_CSRF_SSL_STRICT` | `False` if behind TLS-terminating proxy |
| `DATABASE_URL` | PostgreSQL for production |

---

## WhatsApp Gateway (Evolution API)

WhatsApp delivery (OTP codes, game notifications, halftime shares) goes
through a self-hosted `evoapicloud/evolution-api:v2.3.7` sidecar
(Baileys provider) — free, no per-message fees. Full runbook:
`docs/archive/evolution-integration-plan.md`.

One-time setup after first deploy:

```bash
# 1. Deploy the Prisma schema into the shared Postgres
docker compose -f docker-compose.prod.yml exec evolution npm run db:deploy

# 2. Create the instance (temporarily publish the port via SSH tunnel,
#    never publicly) and scan the QR with the CLUB number
curl -X POST http://localhost:8081/instance/create \
  -H "apikey: $EVOLUTION_API_KEY" -H "Content-Type: application/json" \
  -d '{"instanceName":"basketball-bot","qrcode":true,"integration":"WHATSAPP-BAILEYS"}'

# 3. Verify, then remove the temporary port mapping and redeploy
curl -H "apikey: $EVOLUTION_API_KEY" \
  http://localhost:8081/instance/connectionState/basketball-bot
# → {"instance":{"instanceName":"basketball-bot","state":"open"}}
```

Without a configured/paired instance the app runs normally — WhatsApp
sends log a warning and return `false` (OTP falls back to email when no
phone is on file). `scripts/deploy.sh` checks the instance state on
every deploy.

## Monitoring

Built-in Prometheus metrics at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `flask_http_request_total` | Counter | Total requests by method/endpoint |
| `flask_http_request_duration_seconds` | Histogram | Request duration |
| `flask_http_exceptions_total` | Counter | Exception count by type |

Health check endpoints:
- `GET /health/live` — Liveness probe
- `GET /health/ready` — Readiness probe (DB connectivity)
- `GET /health/sync` — Sync + WhatsApp probe (`200 ok` / `503 stale`;
  includes Evolution instance state)

Alert rules live in `prometheus/alerts.yml` (instance down, 5xx rate,
PDF p95 latency); the sync dashboard is
`grafana/dashboards/sync-health.json`. Championship freshness can also be
checked from cron and wired to failure alerting:

```bash
python -m jobs.championship_sync --once
python -m jobs.check_sync_health   # exit 1 when stale/erroring, 2 when sidecar unreadable
```

---

## Rollback

```bash
# 1. Revert to previous image
docker-compose down
docker-compose up -d

# 2. Restore database from backup
# (backup your database regularly!)

# 3. Verify
docker-compose logs web
```
