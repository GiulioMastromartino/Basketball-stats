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
# -w 1: One worker (sufficient for hobby tier)
# --bind: Listen on the correct port
# --max-requests 30: Restart worker after ~30 reqs to clear memory leaks
# --max-requests-jitter 10: Add randomness to prevent sync restarts
# --access-logfile - : Log access to stdout
# --error-logfile - : Log errors to stderr
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8080 \
     --workers 1 \
     --max-requests 30 \
     --max-requests-jitter 10 \
     --access-logfile - \
     --error-logfile - \
     run:app
