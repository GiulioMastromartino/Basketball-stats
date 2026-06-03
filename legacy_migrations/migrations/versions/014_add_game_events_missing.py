"""Add missing columns to game_events and plays tables

Revision ID: g4m3_3v3nts_m1ss
Revises: s3tt1ngs_upd4t
Create Date: 2026-02-24 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'g4m3_3v3nts_m1ss'
down_revision = 's3tt1ngs_upd4t'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Fix game_events table
    if 'game_events' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('game_events')]
        
        with op.batch_alter_table('game_events', schema=None) as batch_op:
            if 'possession_number' not in columns:
                batch_op.add_column(
                    sa.Column('possession_number', sa.Integer(), nullable=True)
                )
            if 'game_seconds' not in columns:
                batch_op.add_column(
                    sa.Column('game_seconds', sa.Integer(), nullable=True)
                )
            if 'x_loc' not in columns:
                batch_op.add_column(
                    sa.Column('x_loc', sa.Float(), nullable=True)
                )
            if 'y_loc' not in columns:
                batch_op.add_column(
                    sa.Column('y_loc', sa.Float(), nullable=True)
                )
    
    # Fix plays table
    if 'plays' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('plays')]
        
        with op.batch_alter_table('plays', schema=None) as batch_op:
            if 'source' not in columns:
                batch_op.add_column(
                    sa.Column('source', sa.String(length=20), server_default='imported', nullable=True)
                )


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Revert game_events
    if 'game_events' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('game_events')]
        
        with op.batch_alter_table('game_events', schema=None) as batch_op:
            if 'y_loc' in columns:
                batch_op.drop_column('y_loc')
            if 'x_loc' in columns:
                batch_op.drop_column('x_loc')
            if 'game_seconds' in columns:
                batch_op.drop_column('game_seconds')
            if 'possession_number' in columns:
                batch_op.drop_column('possession_number')
    
    # Revert plays
    if 'plays' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('plays')]
        
        with op.batch_alter_table('plays', schema=None) as batch_op:
            if 'source' in columns:
                batch_op.drop_column('source')
