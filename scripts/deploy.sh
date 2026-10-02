#!/bin/bash
# Production deploy script — called by Jenkins pipeline.
# Requires: docker, docker-compose, Docker socket mounted.
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${BACKUP_DIR:-/var/jenkins_home/backups}"
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

DB_CONTAINER="$(docker ps --format '{{.Names}}' | grep db | head -1)"
if docker exec "$DB_CONTAINER" pg_dump -U "${DB_USER}" "${DB_NAME}" > "$BACKUP_FILE" 2>/dev/null; then
    echo "[OK] Backup saved: $BACKUP_FILE ($(wc -c < "$BACKUP_FILE") bytes)"
else
    echo "[WARN] Database backup failed — continuing anyway"
fi

# ── 3. Build & deploy ───────────────────────────────────────────────────
echo ""
# Jenkins builds the image once in its own stage and passes SKIP_BUILD=1.
# Without this guard deploy.sh rebuilds the same image a second time.
if [ "${SKIP_BUILD:-0}" = "1" ]; then
    echo "[STEP] Skipping build (SKIP_BUILD=1) — using image from pipeline"
else
    echo "[STEP] Building images..."
    docker-compose -f "$COMPOSE_FILE" build web-1
fi

echo ""
echo "[STEP] Deploying services..."
docker-compose -f "$COMPOSE_FILE" up -d

# ── 3b. Check Evolution WhatsApp instance status ─────────────────────────
echo ""
echo "[CHECK] Evolution WhatsApp instance status..."
SESSION_CHECK=$(docker-compose -f "$COMPOSE_FILE" exec -T evolution \
  wget -qO- --header="apikey: ${EVOLUTION_API_KEY:-unset}" \
  http://localhost:8080/instance/connectionState/basketball-bot 2>/dev/null || true)
SESSION_STATUS=$(echo "$SESSION_CHECK" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get('instance') or {}).get('state', 'UNKNOWN'))
except Exception:
    print('UNKNOWN')
" 2>&1 || echo "UNKNOWN")

if [ "$SESSION_STATUS" = "open" ]; then
    echo "[OK] Evolution WhatsApp instance is connected."
elif [ "$SESSION_STATUS" = "connecting" ]; then
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  ⚠ EVOLUTION NEEDS QR CODE PAIRING                           ║"
    echo "║  WhatsApp notifications will be unavailable until paired.   ║"
    echo "║                                                             ║"
    echo "║  Follow Part 1.3 in evolution-integration-plan.md:          ║"
    echo "║  1. Temporarily expose port 8081 on evolution service       ║"
    echo "║  2. Run pairing commands from your Mac                      ║"
    echo "║  3. Redeploy (this script) to verify                       ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
else
    echo "[INFO] Evolution instance status: $SESSION_STATUS"
    echo "[INFO] Run pairing when ready (see evolution-integration-plan.md Part 1.3)"
fi

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
echo "[STEP] Cleaning up old Docker objects (build cache preserved)..."
# `docker system prune` deletes the BuildKit build cache as well as images.
# Any cache older than the filter window goes, so the next build recompiles
# the Rust extension from scratch — the 3-minute vs 20-minute swing. Prune
# containers and dangling images instead, and cap the build cache with an
# explicit storage budget rather than deleting it.
docker container prune -f --filter "until=24h" >/dev/null 2>&1 || true
docker image prune -f --filter "until=24h" >/dev/null 2>&1 || true
docker builder prune -f --keep-storage "${BUILDKEEP_STORAGE:-10GB}" 2>&1 | tail -2 || true

echo ""
echo "[INFO] Docker disk usage after cleanup:"
docker system df 2>/dev/null || true

echo ""
echo "=========================================="
echo "  Deploy completed: $(date)"
echo "=========================================="
