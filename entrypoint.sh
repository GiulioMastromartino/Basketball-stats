#!/bin/bash
# entrypoint.sh

# Exit immediately if a command exits with a non-zero status.
set -e

# 1. Apply database migrations
# We use --app run.py explicitly to ensure Flask finds the app instance
echo "Applying database migrations..."
flask --app run.py db upgrade

# 2. Ensure admin user exists (run after migration so tables exist)
echo "Checking for admin user..."
python seed_admin.py

# 3. Start the production server
# Usage: gunicorn -c <config_file> <app_module>
echo "Starting Gunicorn with smart memory monitoring..."
exec gunicorn -c gunicorn_config.py run:app
