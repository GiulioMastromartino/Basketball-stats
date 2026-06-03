#!/usr/bin/env python
"""Development server with relaxed security settings for local testing."""

import os
# Relax security settings for local development
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('SECRET_KEY', 'dev-secret-key-change-in-production')
os.environ.setdefault('WTF_CSRF_ENABLED', 'false')
os.environ.setdefault('SESSION_COOKIE_SECURE', 'false')
os.environ.setdefault('MAIL_SUPPRESS_SEND', 'true')

from web import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
