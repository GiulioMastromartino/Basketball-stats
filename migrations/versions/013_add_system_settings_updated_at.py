"""Add updated_at to system_settings table

Revision ID: 013_add_system_settings_updated_at
Revises: 012_add_games_schema_version
Create Date: 2026-02-24 13:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = '013_add_system_settings_updated_at'
down_revision = '012_add_games_schema_version'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Check if system_settings table exists and column is missing
    if 'system_settings' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('system_settings')]
        
        if 'updated_at' not in columns:
            with op.batch_alter_table('system_settings', schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column('updated_at', sa.DateTime(), nullable=True)
                )


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    if 'system_settings' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('system_settings')]
        
        if 'updated_at' in columns:
            with op.batch_alter_table('system_settings', schema=None) as batch_op:
                batch_op.drop_column('updated_at')
