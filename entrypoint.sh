#!/bin/bash
# entrypoint.sh

# Exit immediately if a command exits with a non-zero status.
set -e

# 1. Apply database migrations
echo "Applying database migrations..."
flask db upgrade

# 2. Start the production server
# -w 1: One worker (sufficient for hobby tier)
# --bind: Listen on the correct port
# --access-logfile - : Log access to stdout
# --error-logfile - : Log errors to stderr
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8080 \
     --workers 1 \
     --access-logfile - \
     --error-logfile - \
     run:app
