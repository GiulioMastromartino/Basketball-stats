# PostgreSQL Bootstrapping Guide

This document describes how to verify that the Basketball Stats app can start with a fresh PostgreSQL database and apply all migrations from scratch.

## Prerequisites

- Docker and Docker Compose installed.
- No existing PostgreSQL instance on port 5432 (or adjust `.env`).

## Bootstrap Steps

1. **Start PostgreSQL and apply migrations**

   ```bash
   ./scripts/pg_bootstrap.sh
   ```

   This script:
   - Starts the `db` service via Docker Compose.
   - Waits for PostgreSQL to become ready.
   - Executes `flask db upgrade` inside the web container to apply all migrations.

2. **Run smoke tests**

   ```bash
   ./scripts/pg_smoke_test.sh
   ```

   This script:
   - Ensures both `db` and `web` containers are running.
   - Waits for `/health/ready` endpoint to return 200.
   - Checks key endpoints (`/`, `/players`, `/health/live`) for success status codes.

3. **Access the app**

   Open browser: http://localhost:8080

   Use the seeded test data (if any) or create a new game.

## What is validated

- A new PostgreSQL container can be started with defined credentials.
- The app can connect to PostgreSQL using `DATABASE_URL` environment variable.
- Flask-Migrate/Alembic can create all tables from migrations without errors.
- Health endpoints report ready only when database connectivity is established.
- Main routes render without server errors.

## Troubleshooting

- If `pg_bootstrap.sh` fails with database connection errors, ensure port 5432 is free.
- Check logs: `docker-compose logs db` and `docker-compose logs web`.
- Verify environment variables in the `web` service match those in `docker-compose.yml`.

## Notes for CI Integration

The same steps can be reproduced in CI by:

1. Starting a PostgreSQL service container.
2. Running `flask db upgrade`.
3. Executing the smoke tests against the service.