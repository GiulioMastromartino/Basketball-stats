#!/bin/sh
# entrypoint.sh - wrapper to handle database initialization before startup

# Initialize database (creates tables from models, seeds data)
echo "Initializing database..."
python scripts/init_db.py

# Promote admin user from ADMIN_EMAIL
echo "Ensuring admin role for ADMIN_EMAIL..."
python scripts/promote_admin.py

# Start Gunicorn
echo "Starting Gunicorn with smart memory monitoring..."
exec gunicorn --config gunicorn_config.py run:app
