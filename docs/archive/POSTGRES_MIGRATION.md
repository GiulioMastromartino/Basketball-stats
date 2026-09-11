# SQLite → PostgreSQL Migration Guide

This document explains how to migrate existing data from the SQLite development database to a fresh PostgreSQL instance.

## Overview

The app ships with a `basketball_stats.db` SQLite file for local development. When moving to PostgreSQL (staging/production), you need to transfer all existing data.

The provided migration script `scripts/migrate_sqlite_to_postgres.py` performs a full copy while preserving primary key values to maintain referential integrity.

## Prerequisites

- A PostgreSQL database created (empty) and accessible via `DATABASE_URL`.
- All Alembic migrations have been applied to the target DB (so schema exists).
- Python dependencies installed (same as in requirements.txt).
- The SQLite database file exists at project root: `basketball_stats.db`.

## Step-by-Step

1. **Ensure target DB is empty or matches schema**
   ```bash
   # If using Docker Compose:
   ./scripts/pg_bootstrap.sh
   ```
   This will create and migrate the DB from scratch.

2. **Run the migration script**
   ```bash
   DATABASE_URL=postgresql://user:pass@localhost/basketball_stats python scripts/migrate_sqlite_to_postgres.py
   ```
   Adjust the URL to match your PostgreSQL instance.

   The script will:
   - Reflect the SQLite source schema.
   - Reflect the PostgreSQL target schema.
   - Determine a safe insertion order based on foreign key dependencies.
   - Copy each table, preserving row counts.
   - Log progress and any mismatches.

3. **Verify data integrity**
   - Access the app and confirm players, games, stats appear.
   - Compare row counts between SQLite and PostgreSQL for key tables:
     ```bash
     sqlite3 basketball_stats.db "SELECT COUNT(*) FROM player_stat;"
     # Then via psql: SELECT COUNT(*) FROM player_stat;
     ```
   - Spot-check a few game detail pages.

4. **Switch application to PostgreSQL**
   - Set `DATABASE_URL` in your environment.
   - Restart the app.

## Important Notes

- The migration is **one-way**. The script does not handle incremental updates. For future data sync, consider logical replication.
- If the script fails partway, the target DB may be partially populated. Drop and recreate the DB, then re-run.
- Primary key IDs are preserved, so any external references that rely on numeric IDs remain valid.
- Some SQLite-specific types (e.g., booleans as integers) will be automatically converted by SQLAlchemy to appropriate PostgreSQL booleans.
- If you have added custom columns after initial schema creation, ensure both schemas are in sync before running.

## Troubleshooting

- **Foreign key constraint violations**: The table order might be incorrect if your model defines circular dependencies. You may need to manually adjust insertion order or temporarily disable constraints in PostgreSQL (not recommended).
- **Data type errors**: You may need to coerce specific columns (e.g., `datetime` with timezone). Check logs.
- **Missing tables**: The script only migrates tables that exist in both source and target. Extend the script to ignore system tables.

## Post-Migration

After successful migration, back up the PostgreSQL database regularly. Keep the SQLite file as a fallback until you are confident in the new setup.