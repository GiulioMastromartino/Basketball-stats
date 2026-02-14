"""Add missing columns to game_events table

Revision ID: 004_add_game_events_columns
Revises: 003_add_system_settings
Create Date: 2025-02-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004_add_game_events_columns'
down_revision = '003_add_system_settings'
branch_labels = None
depends_on = None


def upgrade():
    # Add missing columns to game_events table
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('quarter', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('time_remaining', sa.String(10), nullable=True))
        batch_op.add_column(sa.Column('score_margin', sa.Integer(), nullable=True))


def downgrade():
    # Remove columns from game_events table
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.drop_column('score_margin')
        batch_op.drop_column('time_remaining')
        batch_op.drop_column('quarter')
