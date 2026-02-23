"""create_lineup_segments

Revision ID: 006_create_lineup_segments
Revises: 005_add_game_event_timeline
Create Date: 2026-02-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006_create_lineup_segments'
down_revision = '005_add_game_event_timeline'
branch_labels = None
depends_on = None


def upgrade():
    # Check if table exists to avoid errors if partially applied
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'lineup_segments' not in tables:
        op.create_table('lineup_segments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('game_id', sa.Integer(), nullable=False),
            sa.Column('start_timestamp', sa.BigInteger(), nullable=False),
            sa.Column('end_timestamp', sa.BigInteger(), nullable=True),
            sa.Column('quarter', sa.Integer(), nullable=True),
            sa.Column('players', sa.JSON(), nullable=False),
            sa.Column('lineup_hash', sa.String(length=64), nullable=False),
            sa.Column('points_scored', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('points_allowed', sa.Integer(), nullable=True, server_default='0'),
            sa.Column('possessions', sa.Integer(), nullable=True, server_default='0'),
            sa.ForeignKeyConstraint(['game_id'], ['games.id'], ),
            sa.PrimaryKeyConstraint('id')
        )


def downgrade():
    op.drop_table('lineup_segments')
