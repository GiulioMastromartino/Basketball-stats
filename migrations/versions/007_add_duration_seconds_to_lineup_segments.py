"""add duration_seconds to lineup_segments

Revision ID: 007_add_duration_seconds_to_lineup
Revises: bc4383c3c1af
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa


revision = "007_add_duration_seconds_to_lineup"
down_revision = "bc4383c3c1af"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("lineup_segments")]

    if "duration_seconds" not in columns:
        op.add_column(
            "lineup_segments",
            sa.Column(
                "duration_seconds", sa.Integer(), nullable=True, server_default="0"
            ),
        )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("lineup_segments")]

    if "duration_seconds" in columns:
        op.drop_column("lineup_segments", "duration_seconds")
