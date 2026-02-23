import click
from flask.cli import with_appcontext
from core.models import User, PlayType, db, bcrypt
import os


@click.command("seed")
@with_appcontext
def seed_command():
    """Seed the database with default data, admin user, and plays."""
    click.echo("Seeding database...")

    # 1. Seed PlayTypes
    if not PlayType.query.first():
        types = ["Offense", "Defense", "Special"]
        for t_name in types:
            db.session.add(PlayType(name=t_name))
        db.session.commit()
        click.echo(f"Seeded PlayTypes: {', '.join(types)}")

    # 2. Seed Admin
    env_email = os.getenv("ADMIN_EMAIL")
    env_user = os.getenv("ADMIN_USERNAME", "admin")
    env_pass = os.getenv("ADMIN_PASSWORD")

    final_email = env_email or "admin@local.com"
    final_pass = env_pass or "admin123"

    user = User.query.filter_by(username=env_user).first()

    if not user:
        click.echo(f"Creating new admin: {env_user}")
        hashed_pw = bcrypt.generate_password_hash(final_pass).decode("utf-8")
        new_admin = User(
            username=env_user,
            email=final_email,
            password_hash=hashed_pw,
            role="admin",
            is_admin=True,
        )
        db.session.add(new_admin)
        db.session.commit()
        click.echo("Admin created successfully.")
    else:
        updates = False
        if env_email and user.email != env_email:
            user.email = env_email
            updates = True
            click.echo(f"Updated admin email to {env_email}")

        if env_pass:
            # Force update hash to ensure match
            user.password_hash = bcrypt.generate_password_hash(env_pass).decode("utf-8")
            updates = True
            click.echo("Updated admin password from environment.")

        if updates:
            db.session.commit()
            click.echo("Admin updated.")
        else:
            click.echo("Admin already up to date.")

    click.echo("Seeding complete.")
