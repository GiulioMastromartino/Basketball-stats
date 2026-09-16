"""create training sessions tables + plays.court_type

Revision ID: 016_create_training
Revises: z0n3_c0lumns
Create Date: 2026-09-15

"""

from alembic import op
import sqlalchemy as sa


revision = "016_create_training"
down_revision = "z0n3_c0lumns"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "training_sessions" not in tables:
        op.create_table(
            "training_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("title", sa.String(length=150), nullable=False),
            sa.Column("session_date", sa.String(length=10), nullable=False),
            sa.Column("start_time", sa.String(length=5), nullable=True),
            sa.Column("location", sa.String(length=150), nullable=True),
            sa.Column("focus", sa.String(length=50), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if "training_segments" not in tables:
        op.create_table(
            "training_segments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("title", sa.String(length=150), nullable=False),
            sa.Column("duration_min", sa.Integer(), nullable=True),
            sa.Column("play_id", sa.Integer(), sa.ForeignKey("plays.id", ondelete="SET NULL"), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
        )

    if "training_attendance" not in tables:
        op.create_table(
            "training_attendance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), nullable=False),
            sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="present"),
            sa.UniqueConstraint("session_id", "player_id", name="uq_attendance_session_player"),
        )

    if "plays" in tables:
        columns = [c["name"] for c in inspector.get_columns("plays")]
        if "court_type" not in columns:
            with op.batch_alter_table("plays", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("court_type", sa.String(length=10), nullable=False, server_default="half")
                )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "training_attendance" in tables:
        op.drop_table("training_attendance")
    if "training_segments" in tables:
        op.drop_table("training_segments")
    if "training_sessions" in tables:
        op.drop_table("training_sessions")

    if "plays" in tables:
        columns = [c["name"] for c in inspector.get_columns("plays")]
        if "court_type" in columns:
            with op.batch_alter_table("plays", schema=None) as batch_op:
                batch_op.drop_column("court_type")
