#!/bin/sh
# entrypoint.sh - wrapper to handle migrations before startup

# Run migrations
echo "Applying database migrations..."
flask db upgrade

# Seed Admin & Data (using our new safe logic)
# This will run the logic inside core/__init__.py or we could call a script
# For now, just starting the app triggers the seed in __init__.py

# Start Gunicorn
echo "Starting Gunicorn with smart memory monitoring..."
exec gunicorn --config gunicorn_config.py run:app
