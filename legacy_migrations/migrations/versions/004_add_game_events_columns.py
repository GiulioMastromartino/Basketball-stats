"""Add missing columns to game_events table

Revision ID: 004_add_game_events_columns
Revises: 003_add_system_settings
Create Date: 2025-02-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '004_add_game_events_columns'
down_revision = '003_add_system_settings'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('game_events')]

    # Add missing columns to game_events table (only if they don't exist)
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        if 'quarter' not in columns:
            batch_op.add_column(sa.Column('quarter', sa.Integer(), nullable=True))
        if 'time_remaining' not in columns:
            batch_op.add_column(sa.Column('time_remaining', sa.String(length=10), nullable=True))
        if 'score_margin' not in columns:
            batch_op.add_column(sa.Column('score_margin', sa.Integer(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('game_events')]

    # Remove columns from game_events table
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        if 'score_margin' in columns:
            batch_op.drop_column('score_margin')
        if 'time_remaining' in columns:
            batch_op.drop_column('time_remaining')
        if 'quarter' in columns:
            batch_op.drop_column('quarter')
