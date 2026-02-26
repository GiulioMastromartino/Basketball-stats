"""create lineups table

Revision ID: 009_create_lineups
Revises: 008_create_player_lineup_stats
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa


revision = "009_create_lineups"
down_revision = "008_create_player_lineup_stats"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    tables = inspector.get_table_names()

    # Create lineups table (portable DDL: Postgres + SQLite)
    if "lineups" not in tables:
        op.create_table(
            "lineups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("lineup_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("players", sa.JSON(), nullable=False),
            sa.Column("display_name", sa.String(length=100), nullable=True),
            sa.Column("is_starting", sa.Boolean(), nullable=True, server_default=sa.text("false")),

            sa.Column("total_seconds", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("total_possessions", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("points_scored", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("points_allowed", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("games_played", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("segment_count", sa.Integer(), nullable=True, server_default="0"),

            sa.Column("ortg", sa.Float(), nullable=True, server_default="0"),
            sa.Column("drtg", sa.Float(), nullable=True, server_default="0"),
            sa.Column("net_rating", sa.Float(), nullable=True, server_default="0"),

            sa.Column("fgm", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("fga", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("tpm", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("tpa", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("ftm", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("fta", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("oreb", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("dreb", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("ast", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("stl", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("blk", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("tov", sa.Integer(), nullable=True, server_default="0"),

            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "last_updated",
                sa.DateTime(),
                nullable=True,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )

    # Add lineup_id to lineup_segments
    if "lineup_segments" in tables:
        columns = [col["name"] for col in inspector.get_columns("lineup_segments")]
        if "lineup_id" not in columns:
            op.add_column(
                "lineup_segments",
                sa.Column("lineup_id", sa.Integer(), nullable=True),
            )

    # Helpful indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_lineups_hash ON lineups(lineup_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_lineups_net_rating ON lineups(net_rating)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_lineup_segments_lineup_id ON lineup_segments(lineup_id)"
    )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    op.execute("DROP INDEX IF EXISTS idx_lineup_segments_lineup_id")
    op.execute("DROP INDEX IF EXISTS idx_lineups_net_rating")
    op.execute("DROP INDEX IF EXISTS idx_lineups_hash")

    if "lineup_segments" in tables:
        columns = [col["name"] for col in inspector.get_columns("lineup_segments")]
        if "lineup_id" in columns:
            op.drop_column("lineup_segments", "lineup_id")

    if "lineups" in tables:
        op.drop_table("lineups")
