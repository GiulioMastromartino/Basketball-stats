"""Initial migration

Revision ID: 4b2c3d4e5f6g
Revises: 
Create Date: 2026-01-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b2c3d4e5f6g'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- 1. Independent Tables ---
    
    # Users
    op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )

    # Games
    op.create_table('games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('opponent', sa.String(length=100), nullable=False),
        sa.Column('team_score', sa.Integer(), nullable=False),
        sa.Column('opponent_score', sa.Integer(), nullable=False),
        sa.Column('result', sa.String(length=1), nullable=False),
        sa.Column('game_type', sa.String(length=20), nullable=False),
        sa.Column('sort_date', sa.String(length=10), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # PlayTypes
    op.create_table('play_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Plays
    op.create_table('plays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('play_type', sa.String(length=50), nullable=True),
        sa.Column('image_filename', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('canvas_data', sa.JSON(), nullable=True),
        sa.Column('diagram_svg', sa.Text(), nullable=True),
        sa.Column('difficulty', sa.String(length=20), server_default='Medium', nullable=False),
        sa.Column('personnel_required', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # --- 2. Dependent Tables ---

    # PlayerStats (depends on games)
    op.create_table('player_stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(length=100), nullable=False),
        sa.Column('points', sa.Integer(), nullable=True),
        sa.Column('minutes', sa.String(length=10), nullable=True),
        sa.Column('reb', sa.Integer(), nullable=True),
        sa.Column('ast', sa.Integer(), nullable=True),
        sa.Column('fgm', sa.Integer(), nullable=True),
        sa.Column('fga', sa.Integer(), nullable=True),
        sa.Column('fg_percent', sa.Float(), nullable=True),
        sa.Column('tpm', sa.Integer(), nullable=True),
        sa.Column('tpa', sa.Integer(), nullable=True),
        sa.Column('tp_percent', sa.Float(), nullable=True),
        sa.Column('ftm', sa.Integer(), nullable=True),
        sa.Column('fta', sa.Integer(), nullable=True),
        sa.Column('ft_percent', sa.Float(), nullable=True),
        sa.Column('oreb', sa.Integer(), nullable=True),
        sa.Column('dreb', sa.Integer(), nullable=True),
        sa.Column('stl', sa.Integer(), nullable=True),
        sa.Column('blk', sa.Integer(), nullable=True),
        sa.Column('tov', sa.Integer(), nullable=True),
        sa.Column('pf', sa.Integer(), nullable=True),
        sa.Column('plus_minus', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # PlaySequences (depends on plays)
    op.create_table('play_sequences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('play_id', sa.Integer(), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('element_data', sa.JSON(), nullable=True),
        sa.Column('caption', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['play_id'], ['plays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # ShotEvents (depends on games, plays)
    op.create_table('shot_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(length=100), nullable=True),
        sa.Column('shot_type', sa.String(length=10), nullable=True),
        sa.Column('result', sa.String(length=10), nullable=True),
        sa.Column('points', sa.Integer(), nullable=True),
        sa.Column('x_loc', sa.Float(), nullable=True),
        sa.Column('y_loc', sa.Float(), nullable=True),
        sa.Column('quarter', sa.Integer(), nullable=True),
        sa.Column('play_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.ForeignKeyConstraint(['play_id'], ['plays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # GameEvents (depends on games, plays)
    op.create_table('game_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=True),
        sa.Column('player_name', sa.String(length=100), nullable=True),
        sa.Column('detail', sa.String(length=255), nullable=True),
        sa.Column('timestamp', sa.Integer(), nullable=True),
        sa.Column('shot_attempt', sa.String(length=10), nullable=True),
        sa.Column('play_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
        sa.ForeignKeyConstraint(['play_id'], ['plays.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('game_events')
    op.drop_table('shot_events')
    op.drop_table('play_sequences')
    op.drop_table('player_stats')
    op.drop_table('plays')
    op.drop_table('play_types')
    op.drop_table('games')
    op.drop_table('users')
