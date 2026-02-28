"""Add zone columns to game_events and shot_events tables for schema 3.0

Revision ID: z0n3_c0lumns
Revises: g4m3_3v3nts_m1ss
Create Date: 2026-02-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = 'z0n3_c0lumns'
down_revision = 'g4m3_3v3nts_m1ss'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Add zone to game_events table
    if 'game_events' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('game_events')]
        
        with op.batch_alter_table('game_events', schema=None) as batch_op:
            if 'zone' not in columns:
                batch_op.add_column(
                    sa.Column('zone', sa.String(length=50), nullable=True)
                )
    
    # Add zone to shot_events table
    if 'shot_events' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('shot_events')]
        
        with op.batch_alter_table('shot_events', schema=None) as batch_op:
            if 'zone' not in columns:
                batch_op.add_column(
                    sa.Column('zone', sa.String(length=50), nullable=True)
                )


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Remove zone from game_events
    if 'game_events' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('game_events')]
        
        with op.batch_alter_table('game_events', schema=None) as batch_op:
            if 'zone' in columns:
                batch_op.drop_column('zone')
    
    # Remove zone from shot_events
    if 'shot_events' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('shot_events')]
        
        with op.batch_alter_table('shot_events', schema=None) as batch_op:
            if 'zone' in columns:
                batch_op.drop_column('zone')
