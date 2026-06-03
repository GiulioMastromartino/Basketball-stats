"""add_lineup_segment_id_to_game_events

Revision ID: bc4383c3c1af
Revises: 006_create_lineup_segments
Create Date: 2026-02-20 17:04:41.187082

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bc4383c3c1af'
down_revision = '006_create_lineup_segments'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column exists before adding (idempotent migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('game_events')]
    
    if 'lineup_segment_id' not in columns:
        # Add lineup_segment_id column to game_events table
        op.add_column(
            'game_events',
            sa.Column('lineup_segment_id', sa.Integer(), nullable=True)
        )
        
        # Add foreign key constraint
        op.create_foreign_key(
            'fk_game_events_lineup_segment_id',
            'game_events',
            'lineup_segments',
            ['lineup_segment_id'],
            ['id']
        )


def downgrade():
    # Check if column exists before dropping
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('game_events')]
    
    if 'lineup_segment_id' in columns:
        # Drop foreign key constraint
        op.drop_constraint('fk_game_events_lineup_segment_id', 'game_events', type_='foreignkey')
        
        # Drop column
        op.drop_column('game_events', 'lineup_segment_id')
