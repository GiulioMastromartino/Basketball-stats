"""Add Play Selector tables and columns

Revision ID: 3a1c29f86e5b
Revises: 
Create Date: 2026-01-12 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a1c29f86e5b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create plays table
    op.create_table('plays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('play_type', sa.String(length=50), nullable=True, server_default='Offense'),
        sa.Column('image_filename', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('plays', schema=None) as batch_op:
        batch_op.create_index('idx_plays_type', ['play_type'], unique=False)

    # Add columns to game_events
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shot_attempt', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('play_id', sa.Integer(), nullable=True))
        batch_op.create_index('idx_game_events_play_id', ['play_id'], unique=False)
        batch_op.create_index('idx_game_events_type', ['event_type'], unique=False)
        batch_op.create_foreign_key('fk_game_events_play_id_plays', 'plays', ['play_id'], ['id'])

    # Add columns to shot_events
    with op.batch_alter_table('shot_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('play_id', sa.Integer(), nullable=True))
        batch_op.create_index('idx_shot_events_play_id', ['play_id'], unique=False)
        batch_op.create_foreign_key('fk_shot_events_play_id_plays', 'plays', ['play_id'], ['id'])


def downgrade():
    # Remove columns from shot_events
    with op.batch_alter_table('shot_events', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shot_events_play_id_plays', type_='foreignkey')
        batch_op.drop_index('idx_shot_events_play_id')
        batch_op.drop_column('play_id')

    # Remove columns from game_events
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        batch_op.drop_constraint('fk_game_events_play_id_plays', type_='foreignkey')
        batch_op.drop_index('idx_game_events_type')
        batch_op.drop_index('idx_game_events_play_id')
        batch_op.drop_column('play_id')
        batch_op.drop_column('shot_attempt')

    # Drop plays table
    with op.batch_alter_table('plays', schema=None) as batch_op:
        batch_op.drop_index('idx_plays_type')
    op.drop_table('plays')
