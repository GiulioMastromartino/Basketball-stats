#!/usr/bin/env python3
"""
CLI entry point for database management
Run with: python3 manage.py [command]
"""
import os
from flask.cli import FlaskGroup
from web import create_app

# Create app with proper environment
env = os.getenv("FLASK_ENV", "development")
app = create_app(env)

# Create CLI group
cli = FlaskGroup(create_app=lambda: app)

if __name__ == "__main__":
    cli()
