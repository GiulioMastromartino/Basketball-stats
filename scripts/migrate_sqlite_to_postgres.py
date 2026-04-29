#!/usr/bin/env python3
"""
Migrate all data from SQLite database (basketball_stats.db) to PostgreSQL
using SQLAlchemy. Preserves primary key IDs to maintain foreign key relationships.

Usage:
    export DATABASE_URL=postgresql://user:pass@host/dbname
    python3 scripts/migrate_sqlite_to_postgres.py

The script is idempotent: if inserts fail due to primary key violations,
it stops and reports the error. Target database should be clean before running.
"""

import os
import sys
import logging
from sqlalchemy import create_engine, MetaData, Table, inspect, text, func
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Config
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_URL = f"sqlite:///{os.path.join(PROJECT_ROOT, 'basketball_stats.db')}"
PG_URL = os.getenv("DATABASE_URL")
if not PG_URL:
    logger.error("DATABASE_URL environment variable not set.")
    sys.exit(1)

# Normalize postgres:// -> postgresql://
if PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(PG_URL)

sqlite_meta = MetaData()
pg_meta = MetaData()

# Reflect tables from both databases
logger.info("Reflecting table structures from SQLite...")
sqlite_meta.reflect(bind=sqlite_engine)
logger.info(f"Found SQLite tables: {list(sqlite_meta.tables.keys())}")

logger.info("Reflecting table structures from PostgreSQL...")
pg_meta.reflect(bind=pg_engine)
logger.info(f"Found PostgreSQL tables: {list(pg_meta.tables.keys())}")


def get_dependency_order(metadata):
    """
    Return table names in topological order so that parent tables
    (those referenced by foreign keys) come before child tables.
    """
    # Build graph: table -> set of tables it references via foreign keys
    deps = {table.name: set() for table in metadata.tables.values()}
    for table in metadata.tables.values():
        for fk in table.foreign_keys:
            referred = fk.column.table.name
            if referred != table.name:
                deps[table.name].add(referred)

    # Kahn's algorithm
    ordered = []
    while deps:
        ready = [name for name, req in deps.items() if not req]
        if not ready:
            logger.error("Circular dependency detected in table dependencies")
            # Break cycle arbitrarily to continue
            # Pick first remaining table by name
            ready = [next(iter(deps.keys()))]

        for name in ready:
            ordered.append(name)
            del deps[name]

        # Remove ready from remaining dependencies
        for name in deps:
            deps[name] -= set(ready)

    return ordered


# Compute order from SQLite metadata (since we care about preserving FK relationships)
ordered_tables = get_dependency_order(sqlite_meta)
logger.info(f"Migration order: {ordered_tables}")

SQLiteSession = sessionmaker(bind=sqlite_engine)
PGSession = sessionmaker(bind=pg_engine)
sqlite_session = SQLiteSession()
pg_session = PGSession()

try:
    for table_name in ordered_tables:
        sqlite_table = sqlite_meta.tables[table_name]

        # Skip tables not present in PostgreSQL target (e.g., if schema differs)
        if table_name not in pg_meta.tables:
            logger.warning(f"Table '{table_name}' not found in PostgreSQL; skipping")
            continue
        pg_table = pg_meta.tables[table_name]

        # Fetch all rows from SQLite
        result = sqlite_session.execute(sqlite_table.select())
        rows = result.fetchall()
        row_count = len(rows)
        if row_count == 0:
            logger.info(f"Table '{table_name}' is empty; skipping")
            continue

        logger.info(f"Migrating '{table_name}': {row_count} rows")

        # Convert rows to dictionaries compatible with PostgreSQL table
        records = []
        for row in rows:
            # Row may be RowProxy (1.x) or Row (2.0); handle both
            if hasattr(row, "_asdict"):
                rec = row._asdict()
            else:
                rec = dict(row)
            # Keep only columns present in target table
            rec = {k: v for k, v in rec.items() if k in pg_table.c}
            records.append(rec)

        # Bulk insert into PostgreSQL preserving IDs
        pg_session.execute(pg_table.insert(), records)
        pg_session.commit()

        # Verification: count rows in PostgreSQL
        pg_count = pg_session.execute(func.count("*").select_from(pg_table)).scalar()

        logger.info(
            f"Migrated '{table_name}': SQLite={row_count}, PostgreSQL={pg_count}"
        )

        if pg_count != row_count:
            logger.warning(
                f"Row count mismatch for '{table_name}': "
                f"expected {row_count}, got {pg_count}"
            )
        else:
            logger.info(f"✓ {table_name} OK")

    # Optional verification summary
    logger.info("\n--- Verification summary ---")
    verification_tables = ["games", "players", "player_stats"]
    for vt in verification_tables:
        if vt not in pg_meta.tables:
            continue
        t = pg_meta.tables[vt]
        cnt = pg_session.execute(func.count("*").select_from(t)).scalar()
        logger.info(f"  {vt}: {cnt} rows")

    logger.info("Migration completed successfully.")

except Exception as e:
    logger.exception(f"Migration failed: {e}")
    pg_session.rollback()
    sys.exit(1)
finally:
    sqlite_session.close()
    pg_session.close()
