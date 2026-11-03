#!/bin/sh
# entrypoint.sh - wrapper to handle database initialization before startup

# AUTO_MIGRATE gates boot-time schema work. Off in production so the
# one-shot migrator (compose `migrator` service) is the sole schema actor;
# on in dev/test for convenience. When gunicorn runs with preload_app=True,
# the factory executes in the master process and any DB work here leaves a
# pooled connection that every forked worker inherits.
AUTO_MIGRATE="${AUTO_MIGRATE:-true}"
AUTO_MIGRATE_LOWER="$(echo "$AUTO_MIGRATE" | tr '[:upper:]' '[:lower:]')"

if [ "$AUTO_MIGRATE_LOWER" != "false" ] && [ "$AUTO_MIGRATE_LOWER" != "0" ] && [ "$AUTO_MIGRATE_LOWER" != "no" ]; then
    # Initialize database (creates tables from models, seeds data)
    echo "Initializing database..."
    python scripts/init_db.py

    # Promote admin user from ADMIN_EMAIL
    echo "Ensuring admin role for ADMIN_EMAIL..."
    python scripts/promote_admin.py
else
    echo "AUTO_MIGRATE is off — skipping boot-time schema init; the migrator service owns schema changes."
fi

# Start Gunicorn
echo "Starting Gunicorn with smart memory monitoring..."
exec gunicorn --config gunicorn_config.py run:app
