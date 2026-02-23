"""Add timeline fields to game_events table

Revision ID: 005_add_game_event_timeline_fields
Revises: 004_add_game_events_columns
Create Date: 2026-02-17

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "005_add_game_event_timeline_fields"
down_revision = "004_add_game_events_columns"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("game_events")]

    with op.batch_alter_table("game_events", schema=None) as batch_op:
        if "possession_number" not in columns:
            batch_op.add_column(
                sa.Column("possession_number", sa.Integer(), nullable=True)
            )
        if "game_seconds" not in columns:
            batch_op.add_column(sa.Column("game_seconds", sa.Integer(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("game_events")]

    with op.batch_alter_table("game_events", schema=None) as batch_op:
        if "game_seconds" in columns:
            batch_op.drop_column("game_seconds")
        if "possession_number" in columns:
            batch_op.drop_column("possession_number")
