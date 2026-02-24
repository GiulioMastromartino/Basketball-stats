#!/bin/sh
# entrypoint.sh - wrapper to handle migrations before startup

# Run migrations
echo "Applying database migrations..."
flask db upgrade

# Promote admin user from ADMIN_EMAIL
echo "Ensuring admin role for ADMIN_EMAIL..."
python scripts/promote_admin.py

# Start Gunicorn
echo "Starting Gunicorn with smart memory monitoring..."
exec gunicorn --config gunicorn_config.py run:app
