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

# 3. Start the stack
docker-compose up -d
```

This starts:

| Service | Purpose |
|---------|---------|
| `db` | PostgreSQL 16 with persistent volume |
| `web` | Flask app via Gunicorn on port 8080 |
| `cloudflared` | Optional Cloudflare Tunnel for public HTTPS access |

### Environment Variables

Set these in `.env` or in `docker-compose.override.yml`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | — | Flask session signing key (generate a random string) |
| `DATABASE_URL` | No | SQLite | `postgresql://user:pass@db/basketball_stats` |
| `FLASK_ENV` | No | `development` | Set to `production` for production |
| `DISABLE_AUTH` | No | `false` | `true` for single-user/personal deployments |
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

1. Go to **Apps** → **Discover Apps** → **Custom App**
2. **Application Name**: `basketball-stats`
3. **Image**: `your-registry/basketball-stats:latest`
4. **Environment Variables**:
   - `DATABASE_URL`: `sqlite:////app/data/basketball_stats.db`
   - `SECRET_KEY`: (generate a random string)
   - `FLASK_ENV`: `production`
5. **Storage**: Map persistent host paths:
   - `/mnt/pool/app-data` → `/app/instance` (database)
   - `/mnt/pool/games` → `/app/Games` (CSV import)
   - `/mnt/pool/output` → `/app/Output` (generated files)
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

## Monitoring

Built-in Prometheus metrics at `/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `flask_http_request_total` | Counter | Total requests by method/endpoint |
| `flask_http_request_duration_seconds` | Histogram | Request duration |
| `flask_http_exceptions_total` | Counter | Exception count by type |

Health check endpoints:
- `GET /health/live` — Liveness probe
- `GET /health/ready` — Readiness probe

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
