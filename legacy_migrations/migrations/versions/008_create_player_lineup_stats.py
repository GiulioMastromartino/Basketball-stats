"""create player_lineup_stats table

Revision ID: 008_create_player_lineup_stats
Revises: 007_add_duration_secs
Create Date: 2026-02-23

"""

from alembic import op
import sqlalchemy as sa


revision = "008_create_player_lineup_stats"
down_revision = "007_add_duration_secs"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "player_lineup_stats" not in tables:
        op.create_table(
            "player_lineup_stats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "lineup_segment_id",
                sa.Integer(),
                sa.ForeignKey("lineup_segments.id"),
                nullable=False,
            ),
            sa.Column("player_name", sa.String(length=100), nullable=False),
            sa.Column("points", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("fga", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("fgm", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("tpa", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("tpm", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("fta", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("ftm", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("oreb", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("dreb", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("ast", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("stl", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("blk", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("tov", sa.Integer(), nullable=True, server_default="0"),
        )

    # Index for common join/filter
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_lineup_stats_segment_id ON player_lineup_stats(lineup_segment_id)"
    )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    op.execute("DROP INDEX IF EXISTS idx_player_lineup_stats_segment_id")

    if "player_lineup_stats" in tables:
        op.drop_table("player_lineup_stats")
