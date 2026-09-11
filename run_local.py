#!/usr/bin/env python
"""Development server with relaxed security settings for local testing."""

import os
# Relax security settings for local development
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('SECRET_KEY', 'dev-secret-key-change-in-production')
os.environ.setdefault('WTF_CSRF_ENABLED', 'false')
os.environ.setdefault('SESSION_COOKIE_SECURE', 'false')
os.environ.setdefault('MAIL_SUPPRESS_SEND', 'true')
# No auth in dev: every request acts as a GM (see NoAuthUser).
os.environ.setdefault('DISABLE_AUTH', '1')

from web import create_app
from core.models import db, Organization, Team

app = create_app()


def _ensure_dev_team():
    """Guarantee a default org/team so pages have context on a fresh DB.

    Never seeds into a database that already has organizations (e.g. when
    pointed at the prod DB via DATABASE_URL).
    """
    with app.app_context():
        db.create_all()
        if Organization.query.first() is not None:
            return
        org = Organization(name="Dev Organization", slug="dev-organization")
        if org is None:
            org = Organization(name="Dev Organization", slug="dev-organization")
            db.session.add(org)
            db.session.flush()
        team = Team.query.filter_by(organization_id=org.id).first()
        if team is None:
            team = Team(name="Dev Team", organization_id=org.id, slug="dev-team")
            db.session.add(team)
            db.session.flush()
        db.session.commit()


_ensure_dev_team()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
