#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Basketball Stats PostgreSQL Smoke Test ==="
cd "$PROJECT_ROOT"

# Ensure services are running
echo "Checking if containers are up..."
if ! docker-compose ps | grep -q "web.*Up"; then
  echo "Starting services..."
  docker-compose up -d db web
else
  echo "Services already running."
fi

# Wait for web readiness endpoint
echo "Waiting for readiness endpoint http://localhost:8080/health/ready ..."
for i in $(seq 1 60); do
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health/ready || true)
  if [ "$status" = "200" ]; then
    echo "App is ready after $i seconds."
    break
  fi
  echo -n "."
  sleep 1
done

if [ "$status" != "200" ]; then
  echo "ERROR: App did not become ready."
  exit 1
fi

# Run individual tests
echo "Running smoke tests..."

tests=(
  "/"
  "/health/live"
  "/health/ready"
  "/players"
  "/game/1"
)

for endpoint in "${tests[@]}"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080$endpoint")
  if [ "$code" -ge 200 ] && [ "$code" -lt 400 ]; then
    echo "[OK] $endpoint -> $code"
  else
    echo "[FAIL] $endpoint -> $code"
    exit 1
  fi
done

echo "All smoke tests passed."
