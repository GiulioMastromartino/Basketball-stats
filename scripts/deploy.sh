#!/bin/bash
# Production deploy script — called by Jenkins pipeline.
# Requires: docker, docker-compose, Docker socket mounted.
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-/backups}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

echo "=========================================="
echo "  Basketball Stats — Production Deploy"
echo "  Started: $(date)"
echo "=========================================="

# ── 1. Load production secrets ──────────────────────────────────────────
if [ -f /app/.env.prod ]; then
    set -a
    source /app/.env.prod
    set +a
    echo "[OK] Loaded .env.prod"
else
    echo "[WARN] /app/.env.prod not mounted — falling back to repo .env.prod (placeholders)"
fi

# ── 2. Backup database ──────────────────────────────────────────────────
echo ""
echo "[STEP] Backing up PostgreSQL database..."
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/pre_deploy_${TIMESTAMP}.sql"

if docker exec basketball_stats_db pg_dump -U "${DB_USER}" "${DB_NAME}" > "$BACKUP_FILE" 2>/dev/null; then
    echo "[OK] Backup saved: $BACKUP_FILE ($(wc -c < "$BACKUP_FILE") bytes)"
else
    echo "[WARN] Database backup failed — continuing anyway"
fi

# ── 3. Build & deploy ───────────────────────────────────────────────────
echo ""
echo "[STEP] Building images..."
docker-compose -f "$COMPOSE_FILE" build

echo ""
echo "[STEP] Deploying services..."
docker-compose -f "$COMPOSE_FILE" up -d

# ── 4. Wait for health ──────────────────────────────────────────────────
echo ""
echo "[STEP] Waiting for services to stabilise..."
sleep 15

echo ""
echo "[STEP] Service status:"
docker-compose -f "$COMPOSE_FILE" ps

# Check all 3 web replicas + nginx are running
RUNNING_COUNT=$(docker-compose -f "$COMPOSE_FILE" ps --services --filter "status=running" 2>/dev/null | wc -l)
echo "  Running services: $RUNNING_COUNT"

if [ "$RUNNING_COUNT" -lt 3 ]; then
    echo ""
    echo "[WARN] Not all services are running. Check docker-compose ps above."
    echo "       To roll back:"
    echo "         docker-compose -f $COMPOSE_FILE down"
    echo "         docker-compose -f $COMPOSE_FILE up -d"
fi

# ── 5. Cleanup ──────────────────────────────────────────────────────────
echo ""
echo "[STEP] Cleaning up old Docker images..."
docker system prune -f --filter "until=24h" 2>/dev/null || true

echo ""
echo "=========================================="
echo "  Deploy completed: $(date)"
echo "=========================================="
