"""create lineups table

Revision ID: 009_create_lineups
Revises: 007_add_duration_seconds_to_lineup
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa


revision = "009_create_lineups"
down_revision = "007_add_duration_seconds_to_lineup"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    tables = inspector.get_table_names()
    if "lineups" not in tables:
        op.execute("""
            CREATE TABLE lineups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lineup_hash VARCHAR(64) UNIQUE NOT NULL,
                players JSON NOT NULL,
                display_name VARCHAR(100),
                is_starting BOOLEAN DEFAULT 0,

                total_seconds INTEGER DEFAULT 0,
                total_possessions INTEGER DEFAULT 0,
                points_scored INTEGER DEFAULT 0,
                points_allowed INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                segment_count INTEGER DEFAULT 0,

                ortg FLOAT DEFAULT 0,
                drtg FLOAT DEFAULT 0,
                net_rating FLOAT DEFAULT 0,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    columns = [col["name"] for col in inspector.get_columns("lineup_segments")]
    if "lineup_id" not in columns:
        op.add_column(
            "lineup_segments",
            sa.Column("lineup_id", sa.Integer(), nullable=True),
        )

    op.execute("CREATE INDEX IF NOT EXISTS idx_lineups_hash ON lineups(lineup_hash)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lineups_net_rating ON lineups(net_rating)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lineup_segments_lineup_id ON lineup_segments(lineup_id)"
    )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    op.execute("DROP INDEX IF EXISTS idx_lineup_segments_lineup_id")
    op.execute("DROP INDEX IF EXISTS idx_lineups_net_rating")
    op.execute("DROP INDEX IF EXISTS idx_lineups_hash")

    columns = [col["name"] for col in inspector.get_columns("lineup_segments")]
    if "lineup_id" in columns:
        op.drop_column("lineup_segments", "lineup_id")

    tables = inspector.get_table_names()
    if "lineups" in tables:
        op.execute("DROP TABLE lineups")
