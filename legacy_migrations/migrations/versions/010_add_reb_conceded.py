"""add reb_conceded column

Revision ID: 010_add_reb_conceded
Revises: 009_create_lineups
Create Date: 2026-02-20

"""

from alembic import op
import sqlalchemy as sa


revision = "010_add_reb_conceded"
down_revision = "009_create_lineups"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    player_stats_columns = [
        col["name"] for col in inspector.get_columns("player_stats")
    ]
    if "reb_conceded" not in player_stats_columns:
        op.add_column(
            "player_stats",
            sa.Column("reb_conceded", sa.Integer(), nullable=True, server_default="0"),
        )

    player_lineup_stats_columns = [
        col["name"] for col in inspector.get_columns("player_lineup_stats")
    ]
    if "reb_conceded" not in player_lineup_stats_columns:
        op.add_column(
            "player_lineup_stats",
            sa.Column("reb_conceded", sa.Integer(), nullable=True, server_default="0"),
        )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_player_stats_reb_conceded ON player_stats(reb_conceded)"
    )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    player_stats_columns = [
        col["name"] for col in inspector.get_columns("player_stats")
    ]
    if "reb_conceded" in player_stats_columns:
        op.drop_index("idx_player_stats_reb_conceded", table_name="player_stats")
        op.drop_column("player_stats", "reb_conceded")

    player_lineup_stats_columns = [
        col["name"] for col in inspector.get_columns("player_lineup_stats")
    ]
    if "reb_conceded" in player_lineup_stats_columns:
        op.drop_column("player_lineup_stats", "reb_conceded")
