#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== Basketball Stats PostgreSQL Bootstrap ==="
echo "Project root: $PROJECT_ROOT"

# Start Postgres container
echo "Starting PostgreSQL container..."
cd "$PROJECT_ROOT"
docker-compose up -d db

echo "Waiting for PostgreSQL to become ready..."
# Wait up to 60 seconds for pg_isready
for i in $(seq 1 60); do
  if docker-compose exec -T db pg_isready -U basketball_user > /dev/null 2>&1; then
    echo "PostgreSQL is ready after $i seconds."
    break
  fi
  echo -n "."
  sleep 1
done

if ! docker-compose exec -T db pg_isready -U basketball_user > /dev/null 2>&1; then
  echo "ERROR: PostgreSQL did not become ready in time."
  exit 1
fi

# Run Flask migrations inside the web container
echo "Applying database migrations..."
docker-compose exec -T web flask db upgrade

echo "Bootstrap complete. Database 'basketball_stats' is ready."
echo "You can now start the app with: docker-compose up web"
