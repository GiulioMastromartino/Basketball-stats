"""Add Play Selector tables and columns

Revision ID: 3a1c29f86e5b
Revises: 
Create Date: 2026-01-12 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '3a1c29f86e5b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    # --- 1. Create plays table ---
    if 'plays' not in tables:
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
    else:
        # Check if created_at exists, if not add it (fix for partial states)
        plays_cols = [c['name'] for c in inspector.get_columns('plays')]
        if 'created_at' not in plays_cols:
            with op.batch_alter_table('plays', schema=None) as batch_op:
                batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
                batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))

    # --- 2. Add columns to game_events ---
    game_events_cols = [c['name'] for c in inspector.get_columns('game_events')]
    with op.batch_alter_table('game_events', schema=None) as batch_op:
        if 'shot_attempt' not in game_events_cols:
            batch_op.add_column(sa.Column('shot_attempt', sa.String(length=10), nullable=True))
        if 'play_id' not in game_events_cols:
            batch_op.add_column(sa.Column('play_id', sa.Integer(), nullable=True))
            batch_op.create_index('idx_game_events_play_id', ['play_id'], unique=False)
            batch_op.create_foreign_key('fk_game_events_play_id_plays', 'plays', ['play_id'], ['id'])
        
        # Check index existence before creating
        # (This is harder to check robustly across DBs, so we rely on ignore_if_exists logic 
        # or just assume if column exists, index might too. But robust way is try-except block 
        # or simplified check. For now, we trust the column check above.)

    # --- 3. Add columns to shot_events ---
    shot_events_cols = [c['name'] for c in inspector.get_columns('shot_events')]
    with op.batch_alter_table('shot_events', schema=None) as batch_op:
        if 'play_id' not in shot_events_cols:
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
