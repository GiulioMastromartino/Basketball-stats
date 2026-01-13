#!/usr/bin/env python3
"""
CLI utility for database operations
"""

import os
import sys
from flask.cli import with_appcontext
import click

from app import app, db
from core.seed_plays import seed_plays


@app.cli.command()
@with_appcontext
def init_db():
    """Initialize the database."""
    db.create_all()
    click.echo("[CLI] Database initialized.")


@app.cli.command()
@with_appcontext
def seed():
    """Seed the database with initial data."""
    seed_plays()
    click.echo("[CLI] Database seeded successfully.")


@app.cli.command()
@with_appcontext
def reset_db():
    """Drop all tables and reinitialize."""
    if click.confirm("Are you sure you want to drop all tables?"):
        db.drop_all()
        click.echo("[CLI] All tables dropped.")
        db.create_all()
        click.echo("[CLI] Database reinitialized.")
        seed_plays()
        click.echo("[CLI] Database seeded.")
    else:
        click.echo("[CLI] Operation cancelled.")


if __name__ == "__main__":
    app.cli()
