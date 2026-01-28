#!/bin/sh
# entrypoint.sh - wrapper to handle migrations before startup

# Run migrations
echo "Applying database migrations..."
flask db upgrade

# Force Admin Credential Sync from Environment
# This ensures that even if Gunicorn swallows logs or app factory behaves oddly,
# the password is STRICTLY enforced from the .env file before the server starts.
echo "Syncing admin credentials..."
python scripts/reset_admin_password.py

# Start Gunicorn
echo "Starting Gunicorn with smart memory monitoring..."
exec gunicorn --config gunicorn_config.py run:app
